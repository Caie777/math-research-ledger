"""Explicit start/poll/stop/audit transport; never starts work on page load."""

from __future__ import annotations

import hashlib
import os
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict

from math_research.agent.progress import ResearchRunProgress, read_progress, update_progress
from math_research.agent.runtime import (
    dry_run,
    execute_run,
    prepare_run,
    read_run,
    recovery_status,
    resume_run,
    run_directory,
)
from math_research.agent.state import AgentRequest, AgentRun
from math_research.agent.tools import run_path
from math_research.ledger.handoff import current_research_state
from math_research.ledger.target import ResearchTarget


class RunMetadata(BaseModel):
    """Allowlisted supervision view: no request text, results, paths or error prose."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    problem_id: str
    target_id: str
    status: str
    started_at: str
    ended_at: str | None
    stop_reason: str | None
    error_type: str | None
    executor_attached: bool | None
    resume_available: bool
    attempt: int
    steps: int
    model_calls: int
    checkpointed: bool
    last_checkpoint_step: int
    uncheckpointed_public_events: int


def run_metadata(run: AgentRun) -> RunMetadata:
    return RunMetadata(
        run_id=run.run_id,
        problem_id=run.request.target.problem_id,
        target_id=run.request.target.node_id,
        status=run.status,
        started_at=run.started_at.isoformat(),
        ended_at=run.ended_at.isoformat() if run.ended_at else None,
        stop_reason=run.stop_reason,
        error_type=(
            run.stop_reason if run.stop_reason in {"MODEL_FAILURE", "TOOL_FAILURE"} else "RUN_ERROR"
        )
        if run.error
        else None,
        executor_attached=run.executor_attached,
        resume_available=run.resume_available,
        attempt=run.attempt,
        steps=run.steps,
        model_calls=run.model_calls,
        checkpointed=bool(run.latest_checkpoint or run.checkpoint_path),
        last_checkpoint_step=run.last_checkpoint_step,
        uncheckpointed_public_events=run.uncheckpointed_public_events,
    )


def workspace_identity(state_dir: Path) -> str:
    """Opaque local process identity; does not read workspace content."""
    return hashlib.sha256(os.path.normcase(str(state_dir.resolve())).encode()).hexdigest()


def install_agent_routes(app: FastAPI, ot_dir: Path, write_header: Callable) -> Callable[[], None]:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-agent")
    jobs: dict[str, Future[AgentRun]] = {}
    stops: dict[str, threading.Event] = {}
    lock = threading.RLock()

    def scoped(problem_id: str, run_id: str) -> AgentRun:
        if not (run_directory(ot_dir, run_id) / "run.json").is_file():
            raise HTTPException(404, "Run not found.")
        run = read_run(ot_dir, run_id)
        if run.request.target.problem_id != problem_id:
            raise HTTPException(404, "Run not found in this Problem.")
        return run

    @app.post("/api/problems/{problem_id}/research-runs/dry-run")
    def inspect(problem_id: str, request: AgentRequest) -> dict:
        if request.target.problem_id != problem_id:
            raise HTTPException(400, "Target scope mismatch.")
        return dry_run(ot_dir, request)

    @app.post("/api/problems/{problem_id}/research-runs", dependencies=[Depends(write_header)])
    def start(
        problem_id: str,
        request: AgentRequest,
        metadata_only: bool = False,
        configured: bool = False,
        run_id: str | None = None,
        entry: Literal["operator", "web"] = "operator",
    ) -> AgentRun | RunMetadata:
        if configured:
            from math_research.app.workflows.actions import load_research_defaults

            defaults = load_research_defaults(ot_dir).research
            overrides = request.model_dump(mode="json", exclude_unset=True)
            overrides["budget"] = {**defaults["budget"], **overrides.get("budget", {})}
            request = AgentRequest.model_validate({**defaults, **overrides})
        if request.target.problem_id != problem_id:
            raise HTTPException(400, "Target scope mismatch.")
        provider = None
        if entry == "web":
            from math_research.agent.model import ModelConfigurationRequired
            from math_research.app.model_settings import resolve_role, role_provider

            try:
                role, _ = resolve_role(ot_dir, "research")
                provider = role_provider(ot_dir, "research")
            except ModelConfigurationRequired:
                raise ModelConfigurationRequired("research") from None
            request = request.model_copy(
                update={
                    "provider": role.provider,
                    "model": role.model,
                    "effort": role.reasoning_effort,
                }
            )
        with lock:
            # Optional caller-reserved native ID makes a lost start response retry-safe.
            if run_id and (run_directory(ot_dir, run_id) / "run.json").is_file():
                existing = scoped(problem_id, run_id)
                if existing.request.target != request.target:
                    raise HTTPException(409, "Run ID already belongs to a different target.")
                return poll(problem_id, run_id, metadata_only)
            if any(not future.done() for future in jobs.values()):
                raise HTTPException(
                    409, "A research run is already active. Stop or finish it first."
                )
            run = prepare_run(ot_dir, request, run_id=run_id)
            if entry == "web":
                (run_directory(ot_dir, run.run_id) / "web-entry").touch()
            stops[run.run_id] = threading.Event()
            kwargs: dict[str, Any] = {"provider": provider} if provider is not None else {}
            jobs[run.run_id] = executor.submit(
                execute_run, ot_dir, run, cancel=stops[run.run_id], **kwargs
            )
        return run_metadata(run) if metadata_only else run

    @app.get("/api/problems/{problem_id}/research-runs/state")
    def state(problem_id: str, target_id: str, include_provisional: bool = True) -> dict:
        return current_research_state(
            ot_dir,
            ResearchTarget(kind="claim", problem_id=problem_id, node_id=target_id),
            include_provisional=include_provisional,
        ).model_dump(mode="json")

    @app.get("/api/problems/{problem_id}/research-runs/{run_id}")
    def poll(problem_id: str, run_id: str, metadata_only: bool = False) -> AgentRun | RunMetadata:
        with lock:
            run = scoped(problem_id, run_id)
            future = jobs.get(run_id)
            attached = future is not None and not future.done()
            if future is not None and not attached:
                # Completion may have occurred after the first persisted snapshot.
                run = scoped(problem_id, run_id)
        view = recovery_status(ot_dir, run)
        view.executor_attached = attached
        if attached:
            view.resume_available = False
            view.resume_unavailable_reason = "Run is still active."
            view.status = "running"
        return run_metadata(view) if metadata_only else view

    @app.get("/api/problems/{problem_id}/research-runs")
    def runs(problem_id: str, metadata_only: bool = False) -> list[AgentRun | RunMetadata]:
        # Persisted runs rebuild UI continuity; polling applies the existing recovery view.
        from math_research.ledger.records import store

        store.require_dossier(ot_dir, problem_id)
        result: list[AgentRun | RunMetadata] = []
        for path in (ot_dir / "research_runs").glob("*/run.json"):
            run = read_run(ot_dir, path.parent.name)
            if run.request.target.problem_id == problem_id:
                result.append(poll(problem_id, run.run_id, metadata_only))
        return sorted(
            result,
            key=lambda r: r.started_at if isinstance(r, RunMetadata) else r.started_at.isoformat(),
            reverse=True,
        )

    @app.get("/api/problems/{problem_id}/research-runs/{run_id}/events")
    def events(problem_id: str, run_id: str) -> list[dict]:
        import json

        scoped(problem_id, run_id)
        path = run_directory(ot_dir, run_id) / "events.jsonl"
        selected = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue  # A partially appended last line is picked up next poll.
                if event.get("event") in {
                    "run_started",
                    "milestone_saved",
                    "research_reflection",
                    "checkpoint",
                    "checkpoint_unavailable",
                    "run_finished",
                    "run_initialization_failed",
                    "run_resumed",
                }:
                    selected.append(event)
        return selected[-30:]

    @app.get("/api/problems/{problem_id}/research-runs/{run_id}/progress")
    def progress(problem_id: str, run_id: str) -> ResearchRunProgress:
        run = scoped(problem_id, run_id)
        return read_progress(run_directory(ot_dir, run_id), run)

    @app.post(
        "/api/problems/{problem_id}/research-runs/{run_id}/resume",
        dependencies=[Depends(write_header)],
    )
    def resume(problem_id: str, run_id: str, metadata_only: bool = False) -> AgentRun | RunMetadata:
        with lock:
            run = scoped(problem_id, run_id)
            if any(not future.done() for future in jobs.values()):
                raise HTTPException(409, "A research run is already active.")
            view = recovery_status(ot_dir, run)
            if not view.resume_available:
                raise HTTPException(409, view.resume_unavailable_reason)
            stops[run_id] = threading.Event()
            kwargs = {}
            # API runs recover credentials locally, never from their persisted request.
            if (run_directory(ot_dir, run_id) / "web-entry").exists():
                from math_research.app.model_settings import resolve_role, role_provider

                role, _ = resolve_role(ot_dir, "research")
                if (role.provider, role.model, role.reasoning_effort) != (
                    run.request.provider,
                    run.request.model,
                    run.request.effort,
                ):
                    raise HTTPException(409, "Restore the original Research role before resuming.")
                kwargs["provider"] = role_provider(ot_dir, "research")
            jobs[run_id] = executor.submit(
                resume_run, ot_dir, run_id, cancel=stops[run_id], **kwargs
            )
            resumed = view.model_copy(
                update={
                    "status": "running",
                    "stop_reason": None,
                    "executor_attached": True,
                    "resume_available": False,
                    "current_action": "recovery",
                }
            )
            return run_metadata(resumed) if metadata_only else resumed

    @app.post(
        "/api/problems/{problem_id}/research-runs/{run_id}/stop",
        dependencies=[Depends(write_header)],
    )
    def stop(problem_id: str, run_id: str) -> dict:
        run = scoped(problem_id, run_id)
        if run.status == "running" and run_id not in stops:
            raise HTTPException(
                409,
                "Run is no longer attached to this API process. "
                "Audit retained; no automatic resume.",
            )
        if run_id in stops:
            stops[run_id].set()
            update_progress(run_directory(ot_dir, run_id), stop_requested=True)
        active = run_id in jobs and not jobs[run_id].done()
        return {"run_id": run_id, "stop_requested": run.status == "running" or active}

    @app.get("/api/problems/{problem_id}/research-runs/{run_id}/audit")
    def audit(problem_id: str, run_id: str) -> Response:
        scoped(problem_id, run_id)
        path = run_directory(ot_dir, run_id) / "events.jsonl"
        return Response(
            path.read_bytes() if path.exists() else b"", media_type="application/x-ndjson"
        )

    @app.get("/api/problems/{problem_id}/research-runs/{run_id}/artifact")
    def artifact(problem_id: str, run_id: str, path: str) -> FileResponse:
        scoped(problem_id, run_id)
        folder = run_directory(ot_dir, run_id)
        selected = run_path(folder, path)
        if (
            selected.relative_to(folder).parts[0] not in {"artifacts", "work", "checkpoint"}
            or not selected.is_file()
        ):
            raise HTTPException(404, "Research artifact not found.")
        return FileResponse(selected, media_type="application/octet-stream", filename=selected.name)

    def shutdown() -> None:
        for event in stops.values():
            event.set()
        executor.shutdown(wait=False, cancel_futures=True)

    from math_research.app.api.coordinator import install_coordinator_routes
    from math_research.app.workflows.coordinator import ResearchRunActions

    install_coordinator_routes(
        app,
        ot_dir,
        write_header,
        ResearchRunActions(
            start=lambda pid, request: cast(AgentRun, start(pid, request, entry="web")),
            stop=stop,
            resume=lambda pid, rid: cast(AgentRun, resume(pid, rid)),
            poll=lambda pid, rid: cast(AgentRun, poll(pid, rid)),
        ),
    )
    return shutdown
