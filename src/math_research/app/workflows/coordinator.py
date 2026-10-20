"""Research Coordinator: bounded intent -> allowlisted service -> public response.

No AgentLoop, shell, Python, arbitrary filesystem, authority writer or chat memory.
Facts always come from structured research services, not conversation/model text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from math_research.agent.model import ModelConfigurationRequired, get_role_provider
from math_research.agent.progress import ResearchRunProgress, read_progress
from math_research.agent.providers.base import BaseProvider
from math_research.agent.runtime import read_run, run_directory
from math_research.agent.session import SessionMessage
from math_research.agent.state import AgentRequest, AgentRun
from math_research.app.workflows.actions import load_research_defaults
from math_research.app.workflows.portfolio import research_portfolio, saved_progress
from math_research.core.errors import ResearchError
from math_research.ledger.handoff import current_research_state
from math_research.ledger.records import store
from math_research.ledger.target import ResearchTarget
from math_research.retrieval.recall import ResearchRecall

ToolName = Literal[
    "list_problems",
    "get_problem_state",
    "get_recent_research",
    "get_unresolved_targets",
    "get_research_portfolio",
    "search_research_memory",
    "get_run_progress",
    "list_research_runs",
    "start_research",
    "open_episode_import",
    "stop_research",
    "resume_research",
]
COORDINATOR_TOOLS = get_args(ToolName)  # only high-level services; never executable payloads
MUTATIONS = {"start_research", "stop_research", "resume_research"}


class CoordinatorAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: ToolName
    problem_ref: str | None = Field(default=None, max_length=300)
    target_ref: str | None = Field(default=None, max_length=128)
    run_ref: str | None = Field(default=None, max_length=128)
    query: str = Field(default="", max_length=2000)
    active_only: bool = False


class CoordinatorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(default="", max_length=2000)
    action: CoordinatorAction | None = None
    selected_problem_id: str | None = Field(default=None, max_length=128)
    selected_object_id: str | None = Field(default=None, max_length=128)
    active_run_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def has_request(self) -> CoordinatorRequest:
        if not self.message.strip() and self.action is None:
            raise ValueError("Provide a message or a typed action")
        return self


class ResolvedRefs(BaseModel):
    problem_id: str | None = None
    target_id: str | None = None
    run_id: str | None = None


class ExecutedAction(BaseModel):
    name: ToolName
    refs: ResolvedRefs
    reused: bool = False


class CoordinatorResponse(BaseModel):
    kind: Literal[
        "QUERY_RESULT", "ACTION_RESULT", "MODEL_RESPONSE", "CONFIG_REQUIRED", "AMBIGUOUS", "ERROR"
    ]
    message: str
    resolved_refs: ResolvedRefs = Field(default_factory=ResolvedRefs)
    actions_executed: list[ExecutedAction] = Field(default_factory=list)
    run_id: str | None = None
    structured_payload: dict = Field(default_factory=dict)
    model_used: bool = False
    model_role: Literal["coordinator", "research"] | None = None
    error_code: str | None = None
    choices: list[ResolvedRefs] = Field(default_factory=list)
    pending_action: CoordinatorAction | None = None


@dataclass
class ResearchRunActions:
    """Same closures/executor/locks as existing API routes, not another run engine."""

    start: Callable[[str, AgentRequest], AgentRun]
    stop: Callable[[str, str], dict]
    resume: Callable[[str, str], AgentRun]
    poll: Callable[[str, str], AgentRun]


class ResolutionError(ResearchError):
    def __init__(self, code: str, message: str, choices: list[ResolvedRefs] | None = None):
        self.code, self.choices = code, choices or []
        super().__init__(message)


def deterministic_action(message: str) -> CoordinatorAction | None:
    """Full matches only; exact commands remain available without a model."""
    text = message.strip().rstrip("。")
    simple = {
        "/import": "open_episode_import",
        "我要导入一份 Research Episode": "open_episode_import",
        "导入 Episode": "open_episode_import",
        "/problems": "list_problems",
        "全部问题概览": "get_research_portfolio",
        "/portfolio": "get_research_portfolio",
        "/recent": "get_recent_research",
        "最近研究进展": "get_recent_research",
        "/unresolved": "get_unresolved_targets",
        "未解决问题": "get_unresolved_targets",
        "/runs": "list_research_runs",
        "当前运行任务": "list_research_runs",
        "开始研究": "start_research",
        "继续研究": "start_research",
        "停止这个研究": "stop_research",
        "停止当前研究": "stop_research",
        "停止这个 run": "stop_research",
        "停止这个run": "stop_research",
        "停止研究": "stop_research",
        "恢复中断研究": "resume_research",
        "研究状态": "get_problem_state",
        "刚才那个研究还在跑吗？": "get_run_progress",
        "刚才那个研究还在跑吗": "get_run_progress",
    }
    if text in simple:
        return CoordinatorAction(
            name=cast(ToolName, simple[text]), active_only=text == "当前运行任务"
        )
    command = re.fullmatch(r"/(start|stop|resume|progress|state|runs|recall)\s+(.+)", text, re.I)
    if command:
        name, ref = command.group(1).lower(), command.group(2).strip()
        if name in {"stop", "resume", "progress"}:
            return CoordinatorAction(
                name=cast(
                    ToolName,
                    {
                        "stop": "stop_research",
                        "resume": "resume_research",
                        "progress": "get_run_progress",
                    }[name],
                ),
                run_ref=ref,
            )
        if name == "recall":
            return CoordinatorAction(name="search_research_memory", query=ref)
        return CoordinatorAction(
            name=cast(
                ToolName,
                {
                    "start": "start_research",
                    "state": "get_problem_state",
                    "runs": "list_research_runs",
                }[name],
            ),
            target_ref=ref if ref.upper().startswith(("CLAIM-", "GAP-")) else None,
            problem_ref=None if ref.upper().startswith(("CLAIM-", "GAP-")) else ref,
        )
    start = re.fullmatch(r"(?:继续|开始研究|启动研究)\s*(.+)", text)
    if start:
        ref = start.group(1).strip()
        return CoordinatorAction(
            name="start_research",
            target_ref=ref if ref.upper().startswith(("CLAIM-", "GAP-")) else None,
            problem_ref=None if ref.upper().startswith(("CLAIM-", "GAP-")) else ref,
        )
    stop = re.fullmatch(r"(?:停止|stop)\s*(AGENT-[A-Za-z0-9]+)", text, re.I)
    if stop:
        return CoordinatorAction(name="stop_research", run_ref=stop.group(1).upper())
    state = re.fullmatch(r"(?:查看\s*(.+)|(.+?)\s*(?:的进度|现在推进到哪了[？?]?))", text)
    if state:
        return CoordinatorAction(
            name="get_problem_state", problem_ref=state.group(1) or state.group(2)
        )
    return None


def _blocked(message: str) -> bool:
    return bool(
        re.search(
            r"shell|powershell|执行命令|运行\s*python|直接.*(?:接受|accept)|Human\s*Accept|"
            r"(?:删除|覆盖|修改.*(?:truth|authority|Claim|Problem Record)|"
            r"自动.*审核)",
            message,
            re.I,
        )
    )


class Coordinator:
    def __init__(self, ot_dir: Path, runs: ResearchRunActions):
        self.ot_dir, self.runs = ot_dir, runs

    def problem(self, ref: str | None, selected: str | None = None) -> str:
        problems = store.list_dossiers(self.ot_dir)
        value = (ref or selected or "").strip()
        if match := re.fullmatch(r"P(\d+)", value, re.I):
            value = f"PROBLEM-{int(match.group(1)):04d}"
        matches = [p for p in problems if p.id.casefold() == value.casefold()]
        if not matches and not re.fullmatch(r"PROBLEM-\d+", value, re.I):
            matches = [p for p in problems if p.title == value]
        if not value:
            matches = problems
        if len(matches) == 1:
            return matches[0].id
        if not matches:
            raise ResolutionError("PROBLEM_NOT_FOUND", "未找到匹配的 Problem。")
        raise ResolutionError(
            "AMBIGUOUS", "请选择一个 Problem。", [ResolvedRefs(problem_id=p.id) for p in matches]
        )

    def target(self, action: CoordinatorAction, request: CoordinatorRequest) -> tuple[str, str]:
        # An explicit target is resolved globally unless an explicit Problem scopes it.
        ref = action.target_ref
        if ref:
            rows = research_portfolio(self.ot_dir)
            candidates = [
                (p.problem_id, t.target_id)
                for p in rows
                for t in p.unresolved_targets
                if t.target_id.upper() == ref.upper()
            ]
            if action.problem_ref:
                pid = self.problem(action.problem_ref)
                candidates = [c for c in candidates if c[0] == pid]
            elif len(candidates) > 1 and request.selected_problem_id:
                candidates = [c for c in candidates if c[0] == request.selected_problem_id]
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                raise ResolutionError(
                    "AMBIGUOUS",
                    "请选择目标所属 Problem。",
                    [ResolvedRefs(problem_id=p, target_id=t) for p, t in candidates],
                )
            raise ResolutionError("TARGET_NOT_RESEARCHABLE", "未找到可继续的 Claim / Gap。")
        pid = self.problem(action.problem_ref, request.selected_problem_id)
        row = research_portfolio(self.ot_dir, pid)[0]
        ids = {t.target_id for t in row.unresolved_targets}
        tid = (None if action.problem_ref else request.selected_object_id) or row.primary_target_id
        if tid in ids:
            return pid, str(tid)
        if tid:
            raise ResolutionError("TARGET_NOT_RESEARCHABLE", "该目标当前不在可继续研究列表中。")
        if len(ids) == 1:
            return pid, next(iter(ids))
        if not ids:
            raise ResolutionError("TARGET_NOT_RESEARCHABLE", "没有可继续的 Claim / Gap。")
        raise ResolutionError(
            "AMBIGUOUS",
            "请选择一个未解决的 Claim / Gap。",
            [ResolvedRefs(problem_id=pid, target_id=t) for t in sorted(ids)],
        )

    def query_scope(
        self,
        action: CoordinatorAction,
        request: CoordinatorRequest,
    ) -> tuple[str, str | None]:
        """Queries can inspect closed targets too; mutation eligibility is separate."""
        ref = action.target_ref
        if ref:
            from math_research.ledger.episodes import list_candidates

            owners = [
                p.id
                for p in store.list_dossiers(self.ot_dir)
                if (
                    store.get_claim(self.ot_dir, p.id, ref.upper())
                    or any(c.object_id == ref.upper() for c in list_candidates(self.ot_dir, p.id))
                )
            ]
            if action.problem_ref:
                selected = self.problem(action.problem_ref)
                owners = [pid for pid in owners if pid == selected]
            elif len(owners) > 1 and request.selected_problem_id:
                owners = [pid for pid in owners if pid == request.selected_problem_id]
            if len(owners) != 1:
                raise ResolutionError(
                    "AMBIGUOUS" if owners else "TARGET_NOT_FOUND",
                    "请选择目标所属 Problem。" if owners else "未找到目标。",
                    [ResolvedRefs(problem_id=pid, target_id=ref.upper()) for pid in owners],
                )
            return owners[0], ref.upper()
        pid = self.problem(action.problem_ref, request.selected_problem_id)
        problem = store.require_dossier(self.ot_dir, pid)
        selected_target = None if action.problem_ref else request.selected_object_id
        if selected_target and not store.get_claim(self.ot_dir, pid, selected_target):
            selected_target = None
        return pid, selected_target or problem.primary_claim_id

    def run(self, action: CoordinatorAction, request: CoordinatorRequest) -> ResearchRunProgress:
        ref = action.run_ref or request.active_run_id
        progress = saved_progress(self.ot_dir)
        if ref:
            matches = [p for p in progress if p.run_id == ref.upper()]
        else:
            pid = self.problem(action.problem_ref) if action.problem_ref else None
            matches = [
                p for p in progress if p.status == "running" and (not pid or p.problem_id == pid)
            ]
            if action.name == "resume_research":
                pid = self.problem(action.problem_ref, request.selected_problem_id)
                matches = [
                    p
                    for p in progress
                    if p.problem_id == pid and self.runs.poll(pid, p.run_id).resume_available
                ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            raise ResolutionError("RUN_NOT_FOUND", "没有唯一的当前运行任务；请指定 run ID。")
        raise ResolutionError(
            "AMBIGUOUS",
            "存在多个可能的 run，请选择。",
            [
                ResolvedRefs(problem_id=p.problem_id, target_id=p.target_id, run_id=p.run_id)
                for p in matches
            ],
        )

    def dispatch(
        self, action: CoordinatorAction, request: CoordinatorRequest
    ) -> CoordinatorResponse:
        refs = ResolvedRefs()
        pid: str | None
        query_target: str | None = None
        payload: dict = {}
        executed: list[ExecutedAction] = []
        if action.name == "open_episode_import":
            pid = self.problem(action.problem_ref, request.selected_problem_id)
            return CoordinatorResponse(
                kind="ACTION_RESULT",
                message="已打开 Import Research Episode。请粘贴或上传后预览并确认。",
                resolved_refs=ResolvedRefs(problem_id=pid),
                structured_payload={"open_task": "IMPORT_DECOMPOSE_EPISODE"},
            )
        if action.name in {"get_run_progress", "stop_research", "resume_research"}:
            progress = self.run(action, request)
            refs = ResolvedRefs(
                problem_id=progress.problem_id, target_id=progress.target_id, run_id=progress.run_id
            )
            if action.name == "stop_research":
                result = self.runs.stop(progress.problem_id, progress.run_id)
                payload["stop_requested"] = result["stop_requested"]
            elif action.name == "resume_research":
                self.runs.resume(progress.problem_id, progress.run_id)
            if action.name in MUTATIONS:
                executed.append(ExecutedAction(name=action.name, refs=refs))
            payload["progress"] = read_progress(
                run_directory(self.ot_dir, progress.run_id), read_run(self.ot_dir, progress.run_id)
            ).model_dump(mode="json")
        elif action.name == "start_research":
            pid, tid = self.target(action, request)
            active = [
                p
                for p in saved_progress(self.ot_dir)
                if p.status == "running" and p.problem_id == pid and p.target_id == tid
            ]
            reused = bool(active)
            actual_action: ToolName = action.name
            if active:
                run = self.runs.poll(pid, active[0].run_id)
                if run.resume_available:
                    run = self.runs.resume(pid, run.run_id)
                    actual_action = "resume_research"
            else:
                settings = load_research_defaults(self.ot_dir).research
                run = self.runs.start(
                    pid,
                    AgentRequest.model_validate(
                        {
                            **settings,
                            "target": {"kind": "claim", "problem_id": pid, "node_id": tid},
                        }
                    ),
                )
            refs = ResolvedRefs(problem_id=pid, target_id=tid, run_id=run.run_id)
            executed.append(ExecutedAction(name=actual_action, refs=refs, reused=reused))
            payload["progress"] = read_progress(run_directory(self.ot_dir, run.run_id)).model_dump(
                mode="json"
            )
        elif action.name == "list_research_runs":
            pid = self.problem(action.problem_ref) if action.problem_ref else None
            payload["runs"] = [
                p.model_dump(mode="json")
                for p in saved_progress(self.ot_dir)
                if (not pid or p.problem_id == pid)
                and (not action.active_only or p.status == "running")
            ]
        elif action.name == "search_research_memory":
            pid = self.problem(action.problem_ref, request.selected_problem_id)
            found = ResearchRecall(self.ot_dir, pid).find_files(query=action.query, limit=12)
            refs.problem_id = pid
            payload["query"] = action.query
            payload["memory"] = [
                {
                    "id": f.artifact_id,
                    "kind": f.kind,
                    "title": f.title,
                    "problem_id": f.problem_id,
                    "authority": f.state.authority,
                    "research_state": f.state.research_state,
                    "review": f.state.review,
                    "verification": f.state.verification,
                }
                for f in found.files
            ]
        else:
            pid = None
            if action.name == "get_problem_state":
                pid, query_target = self.query_scope(action, request)
            rows = research_portfolio(self.ot_dir, pid)
            if action.name == "get_recent_research":
                rows.sort(
                    key=lambda p: (
                        p.last_research_activity.isoformat() if p.last_research_activity else ""
                    ),
                    reverse=True,
                )
            payload["portfolio"] = [p.model_dump(mode="json") for p in rows]
            if action.name == "get_unresolved_targets":
                payload["targets"] = [
                    t.model_dump(mode="json") for p in rows for t in p.unresolved_targets
                ]
            if pid:
                refs.problem_id = pid
                refs.target_id = query_target
                refs.run_id = rows[0].latest_run_id
                if refs.run_id:
                    payload["progress"] = read_progress(
                        run_directory(self.ot_dir, refs.run_id)
                    ).model_dump(mode="json")
                if refs.target_id:
                    state = current_research_state(
                        self.ot_dir,
                        ResearchTarget(
                            kind="claim",
                            problem_id=pid,
                            node_id=refs.target_id,
                        ),
                    )
                    payload["public_handoff"] = {
                        "target_id": refs.target_id,
                        "research_status": state.research_status,
                        "episode_id": state.latest_handoff_episode_id,
                        "active_routes": state.active_routes,
                        "active_obstacles": state.active_obstacles,
                        "next_directions": state.next_directions,
                        "authority": "PROVISIONAL / source-reported",
                    }
        return CoordinatorResponse(
            kind="ACTION_RESULT" if executed else "QUERY_RESULT",
            message=render_facts(payload),
            resolved_refs=refs,
            run_id=refs.run_id,
            structured_payload=payload,
            actions_executed=executed,
        )

    def respond(self, request: CoordinatorRequest) -> CoordinatorResponse:
        provider: BaseProvider | None = None
        action: CoordinatorAction | None = None
        used = False
        try:
            if _blocked(request.message):
                return CoordinatorResponse(
                    kind="ERROR",
                    error_code="CONFIRMATION_REQUIRED",
                    message=(
                        "此操作不属于 Coordinator 白名单。删除/覆盖与 Human Review "
                        "权威修改请使用原有确认工作流。"
                    ),
                )
            action = request.action or deterministic_action(request.message)
            if action is None:
                provider = get_role_provider(self.ot_dir, model_role="coordinator")
                used = True
                # One semantic resolution and at most one synthesis; never an AgentLoop.
                plan = model_json(
                    provider,
                    [
                        SessionMessage(
                            role="system",
                            content=(
                                "Resolve a high-level Coordinator action; no mathematics. "
                                "No shell, Python, filesystem or authority edits. "
                                "Never expose private reasoning. "
                                "Worthwhile-work queries mean unresolved targets/portfolio. "
                                "Mutations require an explicit execution request. "
                                "Return JSON matching this schema: "
                                + json.dumps(CoordinatorAction.model_json_schema())
                            ),
                        ),
                        SessionMessage(
                            role="user",
                            content=json.dumps(
                                {
                                    "request": request.model_dump(),
                                    "problems": [
                                        {"problem_id": p.id, "title": p.title}
                                        for p in store.list_dossiers(self.ot_dir)
                                    ],
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    ],
                    CoordinatorAction,
                )
                action = plan
                if action.name in MUTATIONS and not requested_mutation(
                    request.message, action.name
                ):
                    raise ResolutionError(
                        "ACTION_NOT_AUTHORIZED", "本次请求未明确要求执行研究动作。"
                    )
            response = self.dispatch(action, request)
            if provider is not None and action.name not in MUTATIONS:
                close_provider(provider)
                provider = get_role_provider(self.ot_dir, model_role="coordinator")
                synthesis = model_json(
                    provider,
                    [
                        SessionMessage(
                            role="system",
                            content=(
                                "Summarize supplied structured facts. No research or proofs. "
                                "COMPLETED is operational, never mathematical truth. "
                                "Distinguish target, provisional candidates and Human Review. "
                                'Do not output private reasoning. Return JSON {"summary": string}.'
                            ),
                        ),
                        SessionMessage(
                            role="user",
                            content=json.dumps(
                                {
                                    "question": request.message,
                                    "facts": response.structured_payload,
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    ],
                    CoordinatorSynthesis,
                )
                if unsupported_truth_claim(synthesis.summary):
                    raise ResolutionError(
                        "MODEL_OUTPUT_INVALID", "Coordinator 总结包含未经支持的数学权威断言。"
                    )
                response.message = synthesis.summary + "\n\n" + response.message
                response.kind = "MODEL_RESPONSE"
            response.model_used, response.model_role = used, "coordinator" if used else None
            return response
        except ModelConfigurationRequired as exc:
            role: Literal["research", "coordinator"] = (
                "research" if str(exc) == "research" else "coordinator"
            )
            return CoordinatorResponse(
                kind="CONFIG_REQUIRED",
                error_code="MODEL_CONFIGURATION_REQUIRED",
                model_role=role,
                message=f"{role} model is not configured. Settings → Models",
            )
        except ResolutionError as exc:
            return CoordinatorResponse(
                kind="AMBIGUOUS" if exc.code == "AMBIGUOUS" else "ERROR",
                error_code=exc.code,
                message=str(exc),
                choices=exc.choices,
                pending_action=action,
                model_used=used,
                model_role="coordinator" if used else None,
            )
        except (ValidationError, ValueError):
            return CoordinatorResponse(
                kind="ERROR",
                error_code="MODEL_OUTPUT_INVALID",
                message="Coordinator 输出不符合公开 schema；未执行未验证的动作。",
                model_used=used,
                model_role="coordinator" if used else None,
            )
        except Exception:  # bounded transport errors never expose raw provider prose/reasoning
            return CoordinatorResponse(
                kind="ERROR",
                error_code="MODEL_UNAVAILABLE" if used else "ACTION_FAILED",
                message="Coordinator 请求暂时无法完成，请重试或使用确定性命令。",
                model_used=used,
                model_role="coordinator" if used else None,
            )
        finally:
            close_provider(provider)


class CoordinatorSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=5000)


def requested_mutation(message: str, action: str) -> bool:
    if re.search(r"不要|别|勿|don't|do not|是否|哪些|[？?]", message, re.I):
        return False
    verbs = {
        "start_research": r"开始|继续|启动|start\b|continue\b",
        "stop_research": r"停止|停下|stop\b",
        "resume_research": r"恢复|resume\b",
    }
    return bool(re.match(r"^(?:请|帮我)?(?:" + verbs[action] + r")", message, re.I))


def unsupported_truth_claim(summary: str) -> bool:
    for match in re.finditer(
        r"已(?:经)?(?:证明|解决)|\b(?:proved|solved|verified)\b", summary, re.I
    ):
        prefix = summary[max(0, match.start() - 40) : match.start()]
        if not re.search(r"(?:not(?: independently)?|never|un)\s*$", prefix, re.I):
            return True
    return False


def close_provider(provider: BaseProvider | None) -> None:
    close = getattr(provider, "close", None)
    if close:
        try:
            close()
        except Exception:
            pass  # Cleanup cannot replace a typed response with private error prose.


def model_json(provider: BaseProvider, messages: list[SessionMessage], schema):  # noqa: ANN001
    if sum(len(m.content) for m in messages) > 64000:
        raise ResolutionError("CONTEXT_LIMIT", "结构化上下文过大，请缩小到单个 Problem 查询。")
    response = provider.generate(messages, tools=None)
    if (
        response.kind != "message"
        or response.truncated
        or re.search(r"<think|<analysis|private_reasoning|chain.of.thought", response.content, re.I)
    ):
        raise ResolutionError("MODEL_OUTPUT_INVALID", "Coordinator 返回了不允许的输出。")
    return schema.model_validate_json(response.content)


def render_facts(payload: dict) -> str:
    lines = []
    for row in payload.get("portfolio", []):
        state = row["target_state"] or {}
        lines.append(
            f"{row['problem_id']} · {row['title']}\n"
            f"Target: {row['research_state'] or 'unknown'} / {state.get('authority', 'unknown')} / "
            f"verification {state.get('verification', 'unknown')}\n"
            f"Run: {row['latest_run_status'] or 'none'} / {row['latest_run_stop_reason'] or '—'}; "
            f"open gaps {row['open_gap_count']}; "
            f"candidate results {row['candidate_result_count']}; "
            f"Human Review {row['human_review_summary']}"
        )
    if "progress" in payload:
        p = payload["progress"]
        lines.append(
            f"{p['problem_id']} / {p['target_id']} / {p['run_id']}\n"
            f"Run: {p['status']} / {p['stop_reason'] or '—'}"
        )
    if "runs" in payload:
        lines.extend(
            f"{p['run_id']} · {p['problem_id']} / {p['target_id']} · "
            f"{p['status']} / {p['stop_reason'] or '—'}"
            for p in payload["runs"]
        )
    if "targets" in payload:
        lines.extend(
            f"{t['problem_id']} / {t['target_id']} · {t['title']} · {t['state']['authority']}"
            for t in payload["targets"]
        )
    if "memory" in payload:
        lines.extend(
            f"{f['id']} · {f['title']} · {f['authority']} / {f['research_state']}"
            for f in payload["memory"]
        )
    if handoff := payload.get("public_handoff"):
        lines.append(
            f"Public handoff · {handoff['target_id']} / {handoff['research_status']} · "
            "PROVISIONAL / source-reported\n"
            + "\n".join(
                f"{key}: " + "; ".join(handoff[key])
                for key in ("active_obstacles", "active_routes", "next_directions")
            )
        )
    return ("\n\n".join(lines) or "没有匹配的结构化研究记录。") + (
        "\n\n运行结束不等于数学问题已证明。"
        "Candidate / provisional 与 Human Review、独立验证分别记录。"
    )
