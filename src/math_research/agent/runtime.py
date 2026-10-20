"""Single-target bounded adapter to AgentLoop, native Codex and Episode staging.

No controller and no background resume. A run is started explicitly by CLI/API.
All loop-owned logs are in the run directory; canonical memory is read-only.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import RootModel

from math_research.agent.checkpoint import (
    PublicCheckpoint,
    lease_available,
    read_snapshot,
    run_lease,
)
from math_research.agent.checkpoint import write_snapshot as atomic_write_text
from math_research.agent.codex import CodexToolProvider, McpPolicyRejection
from math_research.agent.control.events import RunEvent, ToolExecuted
from math_research.agent.control.models import ToolOutcome
from math_research.agent.control.policies.anti_loop import ToolFailureTracker
from math_research.agent.loop import AgentLoop
from math_research.agent.policy import (
    COMPLETION_STATES,
    CONTINUE_AFTER_MILESTONE,
    MAX_CONSECUTIVE_TOOL_FAILURES,
    REFLECTION_EVERY,
    REFLECTION_REMINDER,
    assess_finalization,
    continuation_instruction,
)
from math_research.agent.progress import Phase, update_progress
from math_research.agent.providers.base import BaseProvider, ProviderResponse
from math_research.agent.providers.registry import get_provider
from math_research.agent.session import SessionMessage, read_messages
from math_research.agent.state import AgentRequest, AgentRun, ResearchStop, StopReason
from math_research.agent.tooling.base import Tool, ToolCall, ToolResult
from math_research.agent.tooling.registry import ToolRegistry
from math_research.agent.tools import (
    DEFAULT_PYTHON_TIMEOUT,
    MAX_COMPUTE_TIMEOUT,
    PREVIEW_CHARS,
    ResearchTools,
    run_path,
)
from math_research.core.config import load_config
from math_research.core.errors import ResearchError
from math_research.core.jsonl import append_jsonl
from math_research.ledger.assets import publish_asset_manifest
from math_research.ledger.decomposition import has_numbered_headings
from math_research.ledger.episodes import archive_episode, extract_candidates
from math_research.ledger.handoff import ensure_handoff
from math_research.ledger.records.write_boundary import automated_research
from math_research.retrieval.context import ResearchContextBuilder, estimate_tokens


def run_directory(ot_dir: Path, run_id: str) -> Path:
    if not re.fullmatch(r"AGENT-[0-9A-F]{16}", run_id):
        raise ResearchError("Invalid research run ID.")
    base = ot_dir.resolve() / "research_runs"
    path = (base / run_id).resolve()
    if not path.is_relative_to(base) or base.resolve() != base:
        raise ResearchError("Research run directory must not redirect outside workspace.")
    return path


def read_run(ot_dir: Path, run_id: str) -> AgentRun:
    try:
        return AgentRun.model_validate_json(
            read_snapshot(run_directory(ot_dir, run_id) / "run.json")
        )
    except FileNotFoundError as exc:
        raise ResearchError("Research run not found.") from exc


def prepare_run(ot_dir: Path, request: AgentRequest, run_id: str | None = None) -> AgentRun:
    if request.target.kind != "claim":
        raise ResearchError("V0 accepts one canonical Claim/Gap target.")
    # Validates scope/target and mandatory material before creating a run.
    bundle = ResearchContextBuilder(ot_dir).build(
        request.target,
        token_budget=request.context_tokens,
        include_provisional=request.include_provisional,
        thread_id=request.thread_id,
        query=request.task,
        explore=True,
    )
    if not bundle.complete:
        raise ResearchError("Context budget cannot fit mandatory target material.")
    run = AgentRun(
        run_id=run_id or "AGENT-" + uuid4().hex[:16].upper(),
        request=request,
        context_version=bundle.source_version,
    )
    directory = run_directory(ot_dir, run.run_id)
    directory.mkdir(parents=True, exist_ok=False)
    for name in ("work", "artifacts", "checkpoint", "loop"):
        (directory / name).mkdir()
    atomic_write_text(
        directory / "context.json", bundle.model_dump_json(indent=2), encoding="utf-8"
    )
    atomic_write_text(directory / "run.json", run.model_dump_json(indent=2), encoding="utf-8")
    update_progress(directory, run, phase="initializing")
    return run


def dry_run(ot_dir: Path, request: AgentRequest) -> dict:
    """Pure inspection: no workspace/run writes, provider calls, or quota usage."""
    import tempfile

    bundle = ResearchContextBuilder(ot_dir).build(
        request.target,
        token_budget=request.context_tokens,
        include_provisional=request.include_provisional,
        thread_id=request.thread_id,
        query=request.task,
        explore=True,
    )
    with tempfile.TemporaryDirectory() as tmp:
        tools = ResearchTools(ot_dir, Path(tmp), request)
        return {
            "target": request.target.model_dump(),
            "context_version": bundle.source_version,
            "context_complete": bundle.complete,
            "context_estimate": bundle.token_estimate,
            "budget": request.budget.model_dump(),
            "tools": tools.registry.names(),
            "availability": tools.availability,
            "model_called": False,
            "checkpoint_every_effective_steps": request.checkpoint_every_effective_steps,
            "continuation_instruction": continuation_instruction(request.task),
            "context_tokens": request.context_tokens,
            "include_provisional": request.include_provisional,
            "model": request.model,
            "effort": request.effort,
        }


def recovery_status(ot_dir: Path, run: AgentRun) -> AgentRun:
    folder = run_directory(ot_dir, run.run_id)
    reason = None
    if not lease_available(folder):
        reason = "Run is still active."
    elif run.stop_reason in {"COMPLETED", "BUDGET_EXHAUSTED"}:
        reason = "Run completed or stopped at its original budget."
    elif (
        run.model_calls >= run.request.budget.max_model_calls
        or run.steps >= run.request.budget.max_agent_steps
        or run.active_seconds + run.pending_wall_seconds >= run.request.budget.max_wall_time - 1
    ):
        reason = "Original run budget exhausted; resume does not reset it."
    view = run.model_copy(deep=True)
    view.resume_available, view.resume_unavailable_reason = reason is None, reason
    checkpoint = PublicCheckpoint(folder, view, repair=False)
    checkpoint.refresh()
    return view


def resume_run(
    ot_dir: Path,
    run_id: str,
    *,
    cancel: threading.Event | None = None,
    provider: BaseProvider | None = None,
) -> AgentRun:
    return execute_run(
        ot_dir, read_run(ot_dir, run_id), cancel=cancel, provider=provider, resuming=True
    )


class _RunTools(Tool):
    def __init__(self, tool: Tool, runtime: _Runtime):
        self.tool, self.runtime = tool, runtime
        self.name, self.description, self.input_schema = (
            tool.name,
            tool.description,
            tool.input_schema,
        )

    def run(self, call: ToolCall) -> ToolResult:
        r = self.runtime
        reason = r.tool_limit(self.name)
        if reason:
            r.reason = reason
            return self.fail(call, reason)
        r.run.tool_calls += 1
        if self.name in {"search_web", "search_arxiv", "fetch_paper"}:
            r.run.web_calls += 1
        if self.name == "python":
            r.run.python_calls += 1
        r.run.current_action = self.name
        reserve = 35
        if self.name == "python":
            requested = call.args.get("timeout_seconds", DEFAULT_PYTHON_TIMEOUT)
            reserve = (
                min(MAX_COMPUTE_TIMEOUT, requested) + 20
                if type(requested) is int and requested > 0
                else DEFAULT_PYTHON_TIMEOUT + 20
            )
        r.run.pending_wall_seconds = min(reserve, max(0, r.research_deadline - time.monotonic()))
        r.event("tool_call", name=self.name, call_id=call.id, args=call.args)
        r.persist()
        try:
            result = self.tool.run(call)
            if not isinstance(result, ToolResult) or result.tool_call_id != call.id:
                raise TypeError("Tool result violates the tool-call contract.")
        except Exception as exc:  # noqa: BLE001 — operational tool failure must checkpoint
            result = self.fail(
                call, str(exc)[:PREVIEW_CHARS], error_class=type(exc).__name__, fatal=True
            )
        finally:
            r.run.pending_wall_seconds = 0
        # Bound every observation, even a connector or injected tool returning too much.
        if len(result.content) > PREVIEW_CHARS + 2000:
            result.content = json.dumps(
                r.tools.bounded(result.content, "observation"), ensure_ascii=False
            )
        if not result.ok:
            detail = {
                "tool": self.name,
                "error": result.metadata.get("error", result.content[:PREVIEW_CHARS]),
                "error_class": result.metadata.get("error_class", "ToolError"),
                "recoverable": not result.metadata.get("fatal", False),
                **{
                    k: result.metadata[k]
                    for k in ("exit_code", "http_status", "attempts", "timeout_seconds")
                    if k in result.metadata
                },
            }
            if result.metadata.get("error") == "execution_timeout":
                detail["message"] = result.content[:PREVIEW_CHARS]
            result.content = json.dumps(detail, ensure_ascii=False)
            if result.metadata.get("fatal"):
                r.reason = "TOOL_FAILURE"
                r.run.error = result.content[:PREVIEW_CHARS]
        r.observations.append({"tool": self.name, "ok": result.ok, "content": result.content})
        r.event(
            "tool_observation",
            name=self.name,
            call_id=call.id,
            ok=result.ok,
            content=result.content,
            failure_metadata=result.metadata if not result.ok else None,
        )
        try:
            content = json.loads(result.content)
            if isinstance(content, dict):
                content.pop("artifact", None)
        except ValueError:
            content = result.content
        signature = hashlib.sha256(
            json.dumps([self.name, call.args, content], sort_keys=True).encode()
        ).hexdigest()
        r.seen.add(signature)
        r.progress.publish("tool_observation:" + self.name, result.content)
        r.persist()
        return result


class _MeteredProvider(BaseProvider):
    def __init__(self, runtime: _Runtime):
        self.runtime = runtime
        self.name = runtime.provider.name
        self.model_name = runtime.provider.model_name

    def generate(
        self, messages: list[SessionMessage], tools: list[dict] | None = None
    ) -> ProviderResponse:
        r = self.runtime
        if r.run.model_calls:
            r.no_progress = r.no_progress + 1 if len(r.seen) == r.last_progress else 0
            if r.no_progress >= r.request.budget.no_progress_steps:
                r.reason = "NO_PROGRESS"
        r.last_progress = len(r.seen)
        reason = r.limit()
        if reason:
            raise ResearchStop(reason)
        if (
            r.run.research_decisions > 0
            and r.run.research_decisions % REFLECTION_EVERY == 0
            and r.run.last_reflection_decision != r.run.research_decisions
        ):
            messages = [
                *messages,
                SessionMessage(
                    role="user",
                    content=REFLECTION_REMINDER,
                    metadata={"research_reflection": True},
                ),
            ]
            r.run.last_reflection_decision = r.run.research_decisions
            r.event(
                "research_reflection",
                decision=r.run.research_decisions,
                reminder=REFLECTION_REMINDER,
            )
        payload = json.dumps([m.model_dump(mode="json") for m in messages], ensure_ascii=False)
        if estimate_tokens(payload + json.dumps(tools)) > r.request.budget.max_context_tokens:
            raise ResearchStop("BUDGET_EXHAUSTED")
        r.run.steps += 1
        r.run.model_calls += 1
        r.run.research_decisions += 1
        r.run.current_action = "model"
        r.config.model.timeout_seconds = max(
            1, min(300, int(r.research_deadline - time.monotonic()))
        )
        r.run.pending_wall_seconds = r.config.model.timeout_seconds
        r.persist()
        try:
            response = r.provider.generate(messages, tools)
        except McpPolicyRejection as exc:
            r.mcp_outcome(exc.metadata, False)
            # Retry is a new metered native turn in the SAME thread. No history replay,
            # MCP arguments/results or extra uncounted inference requests are introduced.
            return self.generate(messages, tools)
        finally:
            r.run.pending_wall_seconds = 0
        if response.content:
            r.progress.publish("public_model_result", response.content)
        if response.usage:
            for key, value in response.usage.model_dump().items():
                r.run.usage[key] = r.run.usage.get(key, 0) + value
        r.run.usage["actual_model"] = response.model or r.provider.model_name
        r.event(
            "model_response",
            kind=response.kind,
            model=response.model,
            usage=response.usage.model_dump() if response.usage else None,
        )
        r.persist()
        if response.truncated:
            # A numbered prefix is still an incomplete transport result. Preserve
            # its public diagnostic above, but never execute partial tools or
            # finalize the draft as a completed mathematical Episode.
            r.run.error = "Model output was truncated; checkpoint retained."
            r.event("truncated_model_output", error=r.run.error)
            raise ResearchStop("MODEL_FAILURE")
        # AgentLoop validates schemas before invoking the wrapped tool. Keep an
        # invalid finalization enum fatal rather than letting legacy chat retry
        # silently complete this research session without a valid declaration.
        for call in response.iter_tool_calls():
            if (
                call.tool_name == "emit_research_episode"
                and "completion_state" in call.tool_args
                and call.tool_args["completion_state"] not in COMPLETION_STATES
            ):
                r.event("invalid_finalization", error="Invalid completion_state.")
                r.reason = "TOOL_FAILURE"
                raise ResearchStop("TOOL_FAILURE")
        return response


class _Runtime:
    def __init__(
        self, ot_dir: Path, run: AgentRun, cancel: threading.Event, provider: BaseProvider | None
    ):
        self.ot_dir, self.run, self.cancel = ot_dir, run, cancel
        self.request = run.request
        self.directory = run_directory(ot_dir, run.run_id)
        self.started = time.monotonic()
        self.previous_active = run.active_seconds
        self.progress = PublicCheckpoint(self.directory, run)
        self.recovery_input = ""
        if run.attempt:
            self.recovery_input = self.progress.recover()
        reserve = min(
            self.request.budget.checkpoint_seconds, max(1, self.request.budget.max_wall_time // 4)
        )
        self.deadline = self.started + max(
            0, self.request.budget.max_wall_time - run.active_seconds
        )
        self.research_deadline = self.deadline - min(
            reserve, max(0, (self.deadline - self.started) / 4)
        )
        self.reason: StopReason | None = None
        self.observations: list[dict] = []
        self.seen: set[str] = set()
        self.no_progress = 0
        self.last_progress = 0
        self.failure_tracker = ToolFailureTracker()
        self.failure_tracker.consecutive_failures = run.consecutive_tool_failures
        self.tools = ResearchTools(ot_dir, self.directory, self.request)
        self.tools.deadline = self.research_deadline
        self.run.availability = self.tools.availability
        config = load_config(ot_dir / "config.yaml")
        config.ui.notifications_enabled = False
        config.agent.mode = "normal"
        config.permissions.mode = "trusted"
        config.agent.max_wall_seconds = self.request.budget.max_wall_time
        config.model.verify_tool_calling = False
        config.model.max_retries = 0
        config.model.timeout_seconds = min(300, self.request.budget.max_wall_time)
        if provider is not None:
            # Injected API transports must share the runtime's decreasing timeout,
            # just like providers constructed below. Private credentials stay in memory.
            supplied = getattr(provider, "config", None)
            if supplied is not None:
                timeout = min(config.model.timeout_seconds, supplied.model.timeout_seconds)
                config.model = supplied.model
                config.model.timeout_seconds = timeout
                config._api_key = supplied._api_key
                provider.config = config  # type: ignore[attr-defined]
            self.provider = provider
        elif self.request.provider == "codex":
            self.provider = CodexToolProvider(
                self.request.model,
                self.request.effort,
                deadline=self.research_deadline,
                should_stop=cancel.is_set,
                allowed_mcp_tools=self.tools.registry.mcp_identities(),
            )
        else:
            config.model.provider = self.request.provider
            if self.request.model:
                config.model.name = self.request.model
            if self.request.effort:
                config.model.reasoning_effort = self.request.effort  # type: ignore[assignment]
            self.provider = get_provider(config)
        self.config = config
        self.loop_directory = (
            self.directory / "loop"
            if not run.attempt
            else self.directory / f"loop-resume-{run.attempt:04d}"
        )
        self.loop_directory.mkdir(exist_ok=True)
        if isinstance(self.provider, CodexToolProvider):
            self.provider.on_public = lambda text: self.progress.publish(
                "public_model_result", text
            )
            self.provider.on_diagnostic = self.native_diagnostic
            self.provider.on_mcp_outcome = self.mcp_outcome
        prompt = (Path(__file__).with_name("research_episode.md")).read_text("utf-8")
        self.system = (
            "你是受预算与权限约束的单目标 Research Agent，使用结构化工具自主研究。\n"
            + prompt
            + (
                "\n中间 RESULT、lemma、局部 PROOF 应用 save_notes / save_experiment_result 保存，"
                "由周期 checkpoint 覆盖，然后继续当前 Explore Session。"
                "emit_research_episode 或直接返回最终 Episode V4 是最终交接，"
                "只有目标实质解决、路线耗尽或继续会话边际价值明显很低时才主动使用；"
                "若目标未解决且还有明确值得执行的下一步，保存进展并继续。"
                "用户 Stop、硬预算或故障仍优先停止并尽可能保留部分 Episode。"
                "最终数学正文后须有独立 CURRENT RESEARCH HANDOFF。"
                "禁止 Human Accept、直接 commit Problem Record、替用户验证定理或创建其他 Agent。"
                "CANONICAL、MODEL_CONFIRMED、PROVISIONAL、source-reported "
                "与 verification 权威不同；"
                "PROVISIONAL 不是定理真值，有限计算只是 Evidence。"
                "按需读取有界 artifact 片段；禁止输出或持久化 private chain-of-thought。"
                "预算内保留最终 checkpoint 调用。通过公开结果或 save_notes 记录新增结果/候选引理、"
                "实验、反例、已排除路线及原因、未解决障碍、当前路线、artifact 路径和下一动作。"
                "不要从头重复 recovery state 已明确排除的路线。"
            )
        )

    def event(self, event_type: str, **fields: object) -> None:
        try:
            append_jsonl(
                self.directory / "events.jsonl",
                RootModel[dict](
                    {"at": datetime.now(UTC).isoformat(), "event": event_type, **fields}
                ),
            )
            if event_type in {
                "run_started",
                "run_finished",
                "checkpoint_unavailable",
                "research_reflection",
            }:
                update_progress(self.directory, self.run)
        except (OSError, ValueError) as exc:
            self.reason = "TOOL_FAILURE"
            self.run.error = f"Runtime event storage failed: {type(exc).__name__}"
            raise

    def native_diagnostic(self, metadata: dict) -> None:
        # A separate metadata-only ledger can be inspected without opening events.jsonl,
        # which also contains public mathematical observations.
        append_jsonl(
            self.directory / "protocol_diagnostics.jsonl",
            RootModel[dict](
                {
                    "at": datetime.now(UTC).isoformat(),
                    "event": "codex_mcp_policy"
                    if metadata.get("item_type") == "mcpToolCall"
                    else "codex_native_item_rejected",
                    "run_id": self.run.run_id,
                    "attempt": self.run.attempt,
                    **metadata,
                }
            ),
        )

    def mcp_outcome(self, metadata: dict, ok: bool) -> None:
        reason = self.tool_limit("mcp")
        if reason:
            raise ResearchStop(reason)
        self.run.tool_calls += 1
        identity = {"server": metadata["server"], "tool": metadata["tool"]}
        signature = json.dumps(identity, sort_keys=True)
        content = (
            "MCP tool completed."
            if ok
            else str(McpPolicyRejection(metadata))
            if not metadata["allowed"]
            else "MCP tool failed; use an allowed research tool or revise the route."
        )
        if ok:
            self.failure_tracker.note_success(signature)
        else:
            self.failure_tracker.note_failure("mcp", signature, content)
        self.emit(
            ToolExecuted(
                step=self.run.steps,
                session_id=self.run.run_id,
                outcome=ToolOutcome(
                    name="mcp", args=identity, ok=ok, content=content, call_id=metadata["item_id"]
                ),
            )
        )
        self.observations.append({"tool": "mcp", "ok": ok, "content": content})
        self.seen.add(hashlib.sha256((signature + metadata["item_id"]).encode()).hexdigest())
        self.persist()
        if self.reason:
            raise ResearchStop(self.reason)

    def emit(self, event: RunEvent) -> None:
        """Reuse the loop's tracker, including argument/gate failures before dispatch."""
        if not isinstance(event, ToolExecuted):
            return
        if event.outcome.ok:
            self.failure_tracker.consecutive_failures = 0
        self.run.consecutive_tool_failures = self.failure_tracker.consecutive_failures
        if self.run.consecutive_tool_failures >= MAX_CONSECUTIVE_TOOL_FAILURES and not self.reason:
            self.reason = "TOOL_FAILURE"
            self.run.error = event.outcome.content[:PREVIEW_CHARS]
        try:
            self.persist()
        except (OSError, ValueError):
            self.reason = "TOOL_FAILURE"  # Persistence failure must never become recoverable.
            raise

    def persist(self, *, phase: Phase | None = None) -> None:
        try:
            self.run.active_seconds = self.previous_active + time.monotonic() - self.started
            self.progress.refresh()
            self.run.artifacts = sorted(
                p.relative_to(self.directory).as_posix()
                for p in (self.directory / "artifacts").iterdir()
                if p.is_file()
            )
            atomic_write_text(
                self.directory / "run.json", self.run.model_dump_json(indent=2), encoding="utf-8"
            )
            update_progress(self.directory, self.run, phase=phase)
        except (OSError, ValueError) as exc:
            self.reason = "TOOL_FAILURE"
            self.run.error = f"Runtime persistence failed: {type(exc).__name__}"
            raise

    def limit(self) -> StopReason | None:
        if self.cancel.is_set():
            return "USER_STOP"
        if self.reason:
            return self.reason
        b = self.request.budget
        if (
            time.monotonic() >= self.research_deadline
            or self.run.model_calls >= b.max_model_calls - 1
            or self.run.steps >= b.max_agent_steps - 1
        ):
            return "BUDGET_EXHAUSTED"
        if self.tools.emitted:
            return "COMPLETED"
        return None

    def tool_limit(self, name: str) -> StopReason | None:
        b = self.request.budget
        if self.cancel.is_set():
            return "USER_STOP"
        if self.reason:
            return self.reason
        if time.monotonic() >= self.research_deadline or self.run.tool_calls >= b.max_tool_calls:
            return "BUDGET_EXHAUSTED"
        # Reuse connector timeouts; do not begin a request that cannot fit the reserve.
        web_seconds = {"search_web": 30, "search_arxiv": 30, "fetch_paper": 20}.get(name, 0)
        if web_seconds and self.research_deadline - time.monotonic() < web_seconds:
            return "BUDGET_EXHAUSTED"
        if (
            name in {"search_web", "search_arxiv", "fetch_paper"}
            and self.run.web_calls >= b.max_web_calls
        ):
            return "BUDGET_EXHAUSTED"
        if name == "python" and self.run.python_calls >= b.max_python_calls:
            return "BUDGET_EXHAUSTED"
        return None

    def messages(self) -> list[SessionMessage]:
        from math_research.retrieval.context import ResearchContextBundle

        bundle = ResearchContextBundle.model_validate_json(
            (self.directory / "context.json").read_text("utf-8")
        )
        return [
            SessionMessage(role="system", content=self.system),
            SessionMessage(
                role="user",
                content=bundle.markdown
                + "\nTool availability:\n"
                + json.dumps(self.run.availability, ensure_ascii=False)
                + (
                    "\nRecovery state (already absorbed uncovered tail):\n" + self.recovery_input
                    if self.recovery_input
                    else ""
                ),
            ),
        ] + read_messages(self.loop_directory)

    def close_provider(self) -> None:
        if isinstance(self.provider, CodexToolProvider):
            self.run.usage["codex_version"] = self.provider.version
            self.run.usage["native_usage"] = self.provider.usage
            if self.provider.rpc is not None:
                # Keep the interrupted research turn as well as the checkpoint turn.
                self.run.usage.setdefault("native_sessions", []).append(
                    {
                        "thread_id": self.provider.thread_id,
                        "model": self.provider.model_name,
                        "usage": dict(self.provider.usage),
                    }
                )
            self.provider.close()

    def save_milestone(self, markdown: str, reason: str, next_action: str) -> str:
        saved = self.tools.bounded(markdown, "milestone")
        saved.update(reason=reason, next_action=next_action, status="MILESTONE_SAVED")
        self.event("milestone_saved", **saved)
        self.progress.publish("public_milestone", json.dumps(saved, ensure_ascii=False))
        self.seen.add(hashlib.sha256(markdown.encode()).hexdigest())
        self.persist()
        return (
            CONTINUE_AFTER_MILESTONE
            + f"\n公开阶段进展：{saved['artifact']}\n下一步：{next_action}\n"
        )

    def checkpoint(self) -> str:
        update_progress(self.directory, self.run, phase="checkpointing")
        if self.tools.emitted:
            return self.tools.emitted
        # Checkpoint uses only public observations and a bounded context; no tools.
        self.close_provider()
        if (
            self.run.model_calls < self.request.budget.max_model_calls
            and self.run.steps < self.request.budget.max_agent_steps
            and time.monotonic() < self.deadline
            and self.run.stop_reason != "MODEL_FAILURE"
        ):
            if isinstance(self.provider, CodexToolProvider):
                self.provider = CodexToolProvider(
                    self.request.model,
                    self.request.effort,
                    deadline=self.deadline,
                    should_stop=lambda: False,
                )
                self.provider.on_diagnostic = self.native_diagnostic
            payload = json.dumps(
                {
                    "stop": self.run.stop_reason,
                    "target": self.request.target.model_dump(),
                    "task": self.request.task,
                    "observations": self.observations,
                    "recovery_state": self.recovery_input,
                },
                ensure_ascii=False,
            )
            cap = max(
                0, self.request.budget.max_context_tokens - estimate_tokens(self.system) - 200
            )
            checkpoint_messages = [
                SessionMessage(role="system", content=self.system),
                SessionMessage(
                    role="user",
                    content="本次研究已因所示 stop 停止，现在必须生成部分交接 Episode V4。"
                    "即使目标未解决或仍有下一步，也不要恢复研究；如实记录，不虚构缺失结果。\n"
                    + payload[:cap],
                ),
            ]
            # Include serialization overhead and UTF-8 content in the same context gate.
            while (
                estimate_tokens(
                    json.dumps(
                        [m.model_dump(mode="json") for m in checkpoint_messages], ensure_ascii=False
                    )
                    + "[]"
                )
                > self.request.budget.max_context_tokens
            ):
                content = checkpoint_messages[1].content
                if len(content) < 200:
                    self.event(
                        "checkpoint_unavailable",
                        error="Context budget cannot fit checkpoint instructions",
                    )
                    break
                checkpoint_messages[1].content = content[: len(content) // 2]
            else:
                return self.model_checkpoint(checkpoint_messages) or self.fallback_checkpoint()
        return self.fallback_checkpoint()

    def model_checkpoint(self, checkpoint_messages: list[SessionMessage]) -> str | None:
        self.config.model.timeout_seconds = max(1, min(300, int(self.deadline - time.monotonic())))
        try:
            self.run.model_calls += 1
            self.run.steps += 1
            self.run.pending_wall_seconds = self.config.model.timeout_seconds
            self.persist(phase="checkpointing")
            response = self.provider.generate(checkpoint_messages, tools=[])
            if response.content:
                self.progress.publish("public_model_result", response.content)
            if response.usage:
                for key, value in response.usage.model_dump().items():
                    self.run.usage[key] = self.run.usage.get(key, 0) + value
            self.event("checkpoint_response", kind=response.kind, model=response.model)
            self.persist(phase="checkpointing")
            if response.truncated:
                self.event("checkpoint_unavailable", error="Checkpoint model output was truncated.")
                return None
            if response.kind == "message" and has_numbered_headings(response.content):
                return response.content
        except Exception as exc:  # noqa: BLE001 — retain fallback Episode and artifacts
            self.event("checkpoint_unavailable", error=str(exc)[:PREVIEW_CHARS])
        finally:
            self.run.pending_wall_seconds = 0
            self.close_provider()
        return None

    def fallback_checkpoint(self) -> str:
        # Honest Episode fallback; operational failure is not a fabricated mathematical result.
        artifacts = "\n".join(self.run.artifacts)
        return (
            f"# Research checkpoint {self.run.run_id}\n\n## FAILED-ATTEMPT-1\n\n"
            f"**Target**\n\ntarget: {self.request.target.node_id}\n\n**Reason**\n\n"
            f"Run stopped: {self.run.stop_reason}. Target remains unresolved by this run. "
            "No theorem verified.\n\n**Research artifacts**\n\n"
            f"{artifacts or 'No completed artifacts.'}\n"
        )


@automated_research
def execute_run(
    ot_dir: Path,
    run: AgentRun,
    *,
    cancel: threading.Event | None = None,
    provider: BaseProvider | None = None,
    resuming: bool = False,
) -> AgentRun:
    folder = run_directory(ot_dir, run.run_id)
    with run_lease(folder):
        if resuming:
            current = read_run(ot_dir, run.run_id)
            if current.attempt != run.attempt:
                raise ResearchError("Run changed since resume was requested.")
            # Lease is owned here; assess all other eligibility without probing it.
            if current.stop_reason in {"COMPLETED", "BUDGET_EXHAUSTED"}:
                raise ResearchError("Completed or budget-stopped runs cannot be resumed.")
            current.active_seconds += current.pending_wall_seconds
            current.pending_wall_seconds = 0
            budget = current.request.budget
            if (
                current.steps >= budget.max_agent_steps
                or current.model_calls >= budget.max_model_calls
                or current.active_seconds >= budget.max_wall_time - 1
            ):
                raise ResearchError("Original run budget exhausted; resume does not reset it.")
            bundle = ResearchContextBuilder(ot_dir).build(
                current.request.target,
                token_budget=current.request.context_tokens,
                include_provisional=current.request.include_provisional,
                thread_id=current.request.thread_id,
                query=current.request.task,
                explore=True,
            )
            if not bundle.complete:
                raise ResearchError("Current target context cannot fit the original budget.")
            current.attempt += 1
            current.status, current.stop_reason, current.error, current.ended_at = (
                "running",
                None,
                None,
                None,
            )
            current.current_action = "recovery"
            current.context_version = bundle.source_version
            if current.episode_id:
                current.episode_history.append(current.episode_id)
            current.episode_id, current.candidate_ids, current.checkpoint_path = None, [], None
            atomic_write_text(
                folder / f"context-before-resume-{current.attempt:04d}.json",
                (folder / "context.json").read_text("utf-8"),
                encoding="utf-8",
            )
            atomic_write_text(
                folder / "context.json", bundle.model_dump_json(indent=2), encoding="utf-8"
            )
            atomic_write_text(
                folder / "run.json", current.model_dump_json(indent=2), encoding="utf-8"
            )
            run = current
            update_progress(folder, run, phase="loading_context", resumed=True)
        return _execute_run_locked(ot_dir, run, cancel=cancel, provider=provider)


def _execute_run_locked(
    ot_dir: Path, run: AgentRun, *, cancel: threading.Event | None, provider: BaseProvider | None
) -> AgentRun:
    if run.status != "running":
        raise ResearchError("Finished runs are immutable; start a new explicit run.")
    try:
        runtime = _Runtime(ot_dir, run, cancel or threading.Event(), provider)
    except (ResearchError, ValueError) as exc:
        run.status, run.stop_reason, run.error = "finished", "MODEL_FAILURE", str(exc)
        run.ended_at = datetime.now(UTC)
        folder = run_directory(ot_dir, run.run_id)
        path = folder / "checkpoint" / "episode.md"
        atomic_write_text(
            path,
            f"## FAILED-ATTEMPT-1\n\n**Target**\n\ntarget: "
            f"{run.request.target.node_id}\n\n**Reason**\n\n"
            "Research provider initialization failed. No mathematical result obtained.\n" + "\n",
            encoding="utf-8",
        )
        run.checkpoint_path = "checkpoint/episode.md"
        atomic_write_text(
            path,
            ensure_handoff(path.read_text("utf-8"), run.request.target.node_id, run.stop_reason)
            + PublicCheckpoint(folder, run).final_coverage(),
            encoding="utf-8",
        )
        archived = archive_episode(
            ot_dir,
            run.request.target.problem_id,
            path,
            provenance=f"automated Research Agent {run.run_id}; initialization failure",
        )
        run.episode_id = archived.episode_id
        run.candidate_ids = [c.candidate_id for c in extract_candidates(ot_dir, archived)]
        # Operational retention only: no Human Accept, canonical write or verifier.
        # Polling/readers never build or publish manifests for historical runs.
        try:
            publish_asset_manifest(folder)
        except (ResearchError, ValueError, OSError) as asset_error:
            run.error = f"{run.error}; asset staging: {asset_error}"[:PREVIEW_CHARS]
        append_jsonl(
            folder / "events.jsonl",
            RootModel[dict]({"event": "run_initialization_failed", "error": run.error}),
        )
        atomic_write_text(
            run_directory(ot_dir, run.run_id) / "run.json",
            run.model_dump_json(indent=2),
            encoding="utf-8",
        )
        update_progress(folder, run)
        return run
    runtime.event(
        "run_started",
        request=run.request.model_dump(mode="json"),
        context_version=run.context_version,
    )
    registry = ToolRegistry()
    for tool in runtime.tools.registry.tools():
        registry.register(_RunTools(tool, runtime))
    loop = AgentLoop(
        runtime.directory / "work",
        runtime.loop_directory,
        _MeteredProvider(runtime),
        registry,
        runtime.config,
        max_steps=run.request.budget.max_agent_steps,
        session_id=run.run_id,
        should_stop=lambda: bool(
            runtime.reason or runtime.cancel.is_set() or runtime.tools.emitted
        ),
        isolate_history=True,
        message_builder=runtime.messages,
        failure_tracker=runtime.failure_tracker,
        event_sink=runtime,
    )
    result = ""
    try:
        instruction = continuation_instruction(run.request.task)
        while True:
            result = loop.run(instruction)
            if runtime.reason or runtime.cancel.is_set() or runtime.tools.emitted:
                break
            if not has_numbered_headings(result):
                break
            decision = assess_finalization(runtime.ot_dir, run.request.target, result)
            if not decision.continue_research:
                break
            instruction = runtime.save_milestone(result, decision.reason, decision.next_action)
        run.stop_reason = runtime.reason or (
            "USER_STOP" if runtime.cancel.is_set() else "COMPLETED"
        )
    except ResearchStop as exc:
        run.stop_reason = exc.reason
    except InterruptedError:
        run.stop_reason = "USER_STOP"
    except KeyboardInterrupt:
        runtime.cancel.set()
        run.stop_reason = "USER_STOP"
    except TimeoutError as exc:
        run.stop_reason = "BUDGET_EXHAUSTED"
        run.error = str(exc)[:PREVIEW_CHARS]
    except Exception as exc:  # noqa: BLE001 — all operational failures leave a checkpoint
        run.stop_reason = runtime.reason or (
            "BUDGET_EXHAUSTED" if time.monotonic() >= runtime.research_deadline else "MODEL_FAILURE"
        )
        run.error = str(exc)[:PREVIEW_CHARS]
    finally:
        runtime.close_provider()
    runtime.persist()
    update_progress(runtime.directory, run, phase="finalizing")
    episode = (
        result
        if has_numbered_headings(result) and run.stop_reason == "COMPLETED"
        else runtime.checkpoint()
    )
    # Coverage is sealed before staging; rolling state is an operational appendix,
    # never parsed as a new mathematical memory format or accepted Claim.
    episode = ensure_handoff(episode, run.request.target.node_id, run.stop_reason)
    episode += runtime.progress.final_coverage()
    update_progress(runtime.directory, run, phase="finalizing")
    if (
        run.stop_reason == "COMPLETED"
        and not has_numbered_headings(result)
        and not runtime.tools.emitted
    ):
        run.stop_reason = "MODEL_FAILURE"
        run.error = "Model returned no Episode V4; checkpoint retained."
    if run.attempt:
        atomic_write_text(
            runtime.directory / "checkpoint" / f"episode-attempt-{run.attempt:04d}.md",
            episode,
            encoding="utf-8",
        )
    path = run_path(runtime.directory, "checkpoint/episode.md")
    atomic_write_text(path, episode, encoding="utf-8")
    run.checkpoint_path = "checkpoint/episode.md"
    try:
        # One mathematical exit: archive verbatim and deterministic Proposal extraction.
        archived = archive_episode(
            ot_dir,
            run.request.target.problem_id,
            path,
            provenance=f"automated Research Agent {run.run_id}; "
            f"provider={run.request.provider}; model={run.request.model}; "
            f"effort={run.request.effort}; Human Review pending",
            thread_ids=[run.request.thread_id] if run.request.thread_id else [],
        )
        run.episode_id = archived.episode_id
        run.candidate_ids = [c.candidate_id for c in extract_candidates(ot_dir, archived)]
        # Publish operational byte references after the new Episode is archived.
        # This never accepts candidates or promotes a mathematical claim.
        publish_asset_manifest(runtime.directory)
    except (ResearchError, ValueError, OSError) as exc:
        run.error = f"Episode/asset staging: {exc}"[:PREVIEW_CHARS]
        if run.stop_reason == "COMPLETED":
            run.stop_reason = "MODEL_FAILURE"
    run.status = "finished"
    run.current_action = "finished"
    run.ended_at = datetime.now(UTC)
    runtime.event("run_finished", stop_reason=run.stop_reason, episode_id=run.episode_id)
    runtime.persist()
    return run
