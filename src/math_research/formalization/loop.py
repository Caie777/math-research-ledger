"""Persistent, bounded executor decision → edit → compiler feedback loop."""

from __future__ import annotations

import json
import time
from uuid import uuid4

from pydantic import ValidationError

from math_research.agent.session import SessionMessage
from math_research.agent.usage import UsageRecord, cost_known, estimate_cost
from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.retrieval.context import estimate_tokens

from .agent import SYSTEM_PROMPT, FormalBudget, FormalDecision, FormalRunState
from .executors import CodexFormalExecutor, DecisionExecutor, ExecutorIsolationError
from .freeze import hash_bytes
from .tools import FormalTools
from .workspace import WRITABLE, append_event

TOOL_CONTRACT = {
    "list_formal_workspace": {},
    "read_formal_file": {"path": "relative", "start": 1, "lines": 160},
    "write_proof_file": {"path": "relative", "content": "complete UTF-8 source"},
    "run_lean_build": {"path": "optional allowed Lean source; omit for project build"},
    "check_target": {},
    "read_build_diagnostics": {},
    "search_mathlib": {"query": "literal text", "limit": 15},
    "read_mathlib_source": {"path": "relative to Mathlib/", "start": 1, "lines": 100},
    "FINISH": {},
}


class FormalizationLoop:
    def __init__(
        self,
        provider: DecisionExecutor,
        tools: FormalTools,
        informal_target: str,
        *,
        budget: FormalBudget | None = None,
    ):
        if provider.name == "mock" or (
            provider.name == "codex" and not isinstance(provider, CodexFormalExecutor)
        ):
            raise ValueError("A native executor must be fresh and decision-only")
        self.provider, self.tools, self.informal = provider, tools, informal_target
        path = tools.run_dir / "run-state.json"
        self.state = (
            FormalRunState.model_validate_json(path.read_bytes())
            if path.exists()
            else (FormalRunState(run_id=uuid4().hex, budget=budget or FormalBudget()))
        )
        self.tools.persist(self.state)
        if isinstance(provider, CodexFormalExecutor):
            provider.event_sink = lambda event: append_event(
                tools.run_dir / "native-events.jsonl", event
            )
        evidence = tools.run_dir / "executor-state.json"
        if evidence.exists() and isinstance(provider, CodexFormalExecutor):
            provider.restore_audit(json.loads(evidence.read_text("utf-8")))

    def _context(self) -> dict:
        workspace = self.tools.workspace
        frozen = workspace.frozen
        snippets = {}
        remaining = 40000
        for path in sorted(workspace.proof_hashes()):
            if remaining <= 0:
                break
            content = workspace.read_formal_file(path, lines=200)[:remaining]
            snippets[path] = content
            remaining -= len(content)
        return {
            "target": self.tools.declaration,
            "lean_toolchain": frozen.lean_toolchain,
            "mathlib_ref": frozen.mathlib_ref,
            "mathlib_commit": frozen.mathlib_commit,
            "module": self.tools.module,
            "frozen_statement": workspace.read_formal_file(frozen.statement.path, lines=200),
            "local_definitions": {
                s.path: workspace.read_formal_file(s.path, lines=200)
                for s in frozen.local_definitions
            },
            "informal_source": self.informal,
            "writable_regions": WRITABLE,
            "workspace_files": workspace.list_formal_workspace(),
            "current_sources": snippets,
            "sources_may_be_windowed": True,
            "diagnostics": [
                {**d.model_dump(), "message": d.message[:1000], "context": d.context[:1200]}
                for d in self.state.diagnostics[:6]
            ],
            "diagnostics_omitted": max(0, len(self.state.diagnostics) - 6),
            "successful_build_declarations_advisory": self.state.successful_helper_facts,
            "last_build_ok": self.state.last_build_ok,
            "last_action": self.state.last_action,
            "last_observation": self.state.last_observation,
            "budget": self.state.budget.model_dump(),
            "used": {
                k: getattr(self.state, k)
                for k in [
                    "model_calls",
                    "build_count",
                    "target_checks",
                    "input_tokens",
                    "output_tokens",
                ]
            },
            "reflection": "No progress detected. Change approach using diagnostics or stop."
            if self.state.reflection_pending
            else None,
            "tool_arguments": TOOL_CONTRACT,
            "decision_schema": FormalDecision.model_json_schema(),
        }

    def step(self) -> None:
        state, tools = self.state, self.tools
        if state.stop_reason:
            return
        tools.workspace.integrity()
        if state.pending_operation:
            # Resume never replays an uncertain external operation or resets counters.
            state.last_observation = {
                "interrupted_operation": state.pending_operation,
                "note": "Reserved budget retained; prior response may be missing",
            }
            state.pending_operation = None
        if (
            state.model_calls >= state.budget.model_calls
            or (state.input_tokens or 0) + (state.output_tokens or 0) >= state.budget.total_tokens
        ):
            state.stop_reason = "BUDGET_EXHAUSTED"
            tools.persist(state)
            return
        content = json.dumps(self._context(), ensure_ascii=False)
        messages = [
            SessionMessage(role="system", content=SYSTEM_PROMPT),
            SessionMessage(role="user", content=content),
        ]
        estimate = estimate_tokens(SYSTEM_PROMPT + content)
        if (
            estimate > state.budget.max_context_tokens
            or (state.input_tokens or 0) + (state.output_tokens or 0) + estimate + 8192
            > state.budget.total_tokens
        ):
            state.stop_reason = "BUDGET_EXHAUSTED"
            tools.persist(state)
            return
        state.model_calls += 1
        state.pending_operation = "model"
        state.reflection_pending = False
        tools.persist(state)
        atomic_write_text(
            tools.run_dir / f"prompt-{state.model_calls:03}.json",
            json.dumps([m.model_dump(mode="json") for m in messages], ensure_ascii=False),
        )
        started = time.monotonic()
        try:
            response = self.provider.generate(messages, tools=None)
        except Exception as exc:
            # SDK error prose may contain credentials; persist only a generic failure.
            state.stop_reason = (
                exc.code if isinstance(exc, ExecutorIsolationError) else "MODEL_FAILURE"
            )
            if self.provider.name == "codex":
                state.input_tokens = state.output_tokens = None
            state.usage_missing_calls += 1
            state.pending_operation = None
            append_event(
                tools.run_dir / "agent-events.jsonl",
                {
                    "event": "model_failure",
                    "call": state.model_calls,
                    "provider": self.provider.name,
                },
            )
            tools.persist(state)
            self._persist_executor()
            return
        state.pending_operation = None
        actual = response.model or self.provider.model_name or "unknown"
        state.actual_models.append(actual)
        native = self.provider.name == "codex"
        estimated = response.usage is None and not native
        prompt_tokens = (
            response.usage.prompt_tokens if response.usage else None if native else estimate
        )
        completion_tokens = (
            response.usage.completion_tokens
            if response.usage
            else None
            if native
            else estimate_tokens(response.content)
        )
        state.input_tokens = (
            state.input_tokens + prompt_tokens
            if state.input_tokens is not None and prompt_tokens is not None
            else None
        )
        state.output_tokens = (
            state.output_tokens + completion_tokens
            if state.output_tokens is not None and completion_tokens is not None
            else None
        )
        if response.usage is None:
            state.usage_missing_calls += 1
        state.tokens_estimated |= estimated
        usage = UsageRecord(
            session_id=state.run_id,
            provider=self.provider.name,
            model=actual,
            prompt_tokens=prompt_tokens or 0,
            completion_tokens=completion_tokens or 0,
            thinking_tokens=response.usage.thinking_tokens if response.usage else 0,
            latency_ms=int((time.monotonic() - started) * 1000),
            cost_usd=estimate_cost(
                self.provider.name, actual, prompt_tokens or 0, completion_tokens or 0
            ),
            cost_known=cost_known(self.provider.name, actual),
            tokens_estimated=estimated,
        )
        usage_record = usage.model_dump(mode="json")
        if native:
            usage_record.update(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=None,
                cost_known=False,
                cost_estimated=False,
            )
        append_event(tools.run_dir / "usage.jsonl", usage_record)
        self._persist_executor()
        append_event(
            tools.run_dir / "agent-events.jsonl",
            {
                "event": "model_response",
                "call": state.model_calls,
                "model": actual,
                "content": response.content[:64000],
                "truncated": response.truncated,
            },
        )
        tools.persist(state)

        if response.truncated or len(response.content.encode()) > 64000:
            state.stop_reason = "MODEL_FAILURE"
            tools.persist(state)
            return
        try:
            decision = FormalDecision.model_validate_json(response.content)
        except (ValueError, ValidationError):
            state.malformed_responses += 1
            state.last_observation = {"error": "Malformed decision JSON; use the provided schema"}
            if state.malformed_responses >= 2:
                state.stop_reason = "MODEL_FAILURE"
            tools.persist(state)
            return
        state.last_action = decision.summary
        old_events = len(state.no_progress_events)
        observations = []
        for action in decision.actions:
            signature = hash_bytes(json.dumps(action.model_dump(), sort_keys=True).encode())
            state.repeated_actions = (
                state.repeated_actions + 1 if signature == state.last_action_signature else 1
            )
            state.last_action_signature = signature
            if state.repeated_actions >= 3:
                state.no_progress_events.append("LOOPING_ACTION")
            try:
                state.last_observation = tools.execute(action.tool, action.arguments, state)
            except (ValueError, OSError, TypeError) as exc:
                # Validation messages are controlled by file/tool capabilities, not SDK diagnostics.
                state.last_observation = {"error": str(exc)[:1200]}
                if "FROZEN_SOURCE_DRIFT" in str(exc):
                    state.stop_reason = "TOOL_FAILURE"
            append_event(
                tools.run_dir / "agent-events.jsonl",
                {
                    "event": "tool_action",
                    "tool": action.tool,
                    "arguments": action.arguments,
                    "observation": state.last_observation,
                },
            )
            observations.append({"tool": action.tool, "result": state.last_observation})
            if state.stop_reason:
                break
        if len(observations) > 1:
            state.last_observation = {"actions": observations}
        if len(state.no_progress_events) > old_events and not state.stop_reason:
            if state.reflection_used:
                state.stop_reason = "NO_PROGRESS"
            else:
                state.reflection_used = state.reflection_pending = True
        tools.persist(state)

    def _persist_executor(self) -> None:
        snapshot = getattr(self.provider, "snapshot", None)
        if snapshot:
            data = snapshot()
            native_usage = data.get("native_usage", [])
            cached = [u.get("cached_tokens") for u in native_usage]
            self.state.cached_tokens = (
                sum(cached) if cached and all(isinstance(v, int) for v in cached) else None
            )
            atomic_write_text(
                self.tools.run_dir / "executor-state.json", json.dumps(data, indent=2)
            )

    def run(self) -> FormalRunState:
        with file_lock(self.tools.run_dir / "execution", stale_after=86400):
            while not self.state.stop_reason:
                try:
                    self.step()
                except (OSError, ValueError):
                    self.state.stop_reason = "TOOL_FAILURE"
                    self.tools.persist(self.state)
        atomic_write_text(
            self.tools.run_dir / "run-summary.json", self.state.model_dump_json(indent=2)
        )
        atomic_write_text(
            self.tools.run_dir / "usage.json",
            json.dumps(
                {
                    "provider": self.provider.name,
                    "configured_model": self.provider.model_name,
                    "actual_models": self.state.actual_models,
                    "model_calls": self.state.model_calls,
                    "input_tokens": self.state.input_tokens,
                    "output_tokens": self.state.output_tokens,
                    "tokens_estimated": self.state.tokens_estimated,
                    "cached_tokens": self.state.cached_tokens,
                    "cached_tokens_note": "Not exposed by the existing provider abstraction",
                    "usage_missing_calls": self.state.usage_missing_calls,
                },
                indent=2,
            ),
        )
        return self.state
