"""Explicit model POST and read-only advisory preflight/history/poll routes."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from pydantic import Field

from math_research.agent.critique import store
from math_research.agent.critique.context import build_critique_context
from math_research.agent.critique.models import (
    CritiqueBundle,
    CritiqueRun,
    CritiqueSettings,
    StrictModel,
)
from math_research.agent.critique.runtime import execute
from math_research.app.workflows.actions import load_research_defaults


class CritiquePreflight(StrictModel):
    bundle: CritiqueBundle
    bundle_sha256: str
    settings: CritiqueSettings


class CritiqueStart(StrictModel):
    settings: CritiqueSettings
    bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def install_critique_routes(
    app: FastAPI, ot_dir: Path, write_header: Callable
) -> Callable[[], None]:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="independent-critique")
    jobs: dict[str, Future[CritiqueRun]] = {}
    lock = threading.Lock()

    def view(critique_id: str) -> CritiqueRun:
        run = store.read_run(ot_dir, critique_id)
        if run.status == "RUNNING" and (critique_id not in jobs or jobs[critique_id].done()):
            # Lost process is an advisory failure. GET never rewrites an artifact or resumes it.
            run.status = "FAILED"
            run.error = "Critique executor is no longer attached; start a new independent critique."
        return run

    @app.get("/api/problems/{problem_id}/records/{record_id}/critique-context")
    def preflight(problem_id: str, record_id: str) -> CritiquePreflight:
        bundle = build_critique_context(ot_dir, problem_id, record_id)
        return CritiquePreflight(
            bundle=bundle,
            bundle_sha256=hashlib.sha256(bundle.model_dump_json(indent=2).encode()).hexdigest(),
            settings=load_research_defaults(ot_dir).critique,
        )

    @app.post(
        "/api/problems/{problem_id}/records/{record_id}/critique",
        dependencies=[Depends(write_header)],
    )
    def start(problem_id: str, record_id: str, request: CritiqueStart) -> CritiqueRun:
        bundle = build_critique_context(ot_dir, problem_id, record_id)
        digest = hashlib.sha256(bundle.model_dump_json(indent=2).encode()).hexdigest()
        if digest != request.bundle_sha256:
            raise HTTPException(
                409, "Critique context changed; inspect and confirm the fresh bundle."
            )
        with lock:
            if any(not job.done() for job in jobs.values()):
                raise HTTPException(409, "An independent critique is already running.")
            run = store.prepare(ot_dir, bundle, request.settings)
            jobs[run.critique_id] = executor.submit(execute, ot_dir, run)
        return run

    @app.get("/api/problems/{problem_id}/records/{record_id}/critiques")
    def history(problem_id: str, record_id: str) -> list[CritiqueRun]:
        build_critique_context(ot_dir, problem_id, record_id)
        with lock:
            return [view(run.critique_id) for run in store.history(ot_dir, problem_id, record_id)]

    @app.get("/api/problems/{problem_id}/critiques/{critique_id}")
    def poll(problem_id: str, critique_id: str) -> CritiqueRun:
        with lock:
            run = view(critique_id)
        if run.problem_id != problem_id:
            raise HTTPException(404, "Critique not found in this Problem.")
        return run

    return lambda: executor.shutdown(wait=False, cancel_futures=True)
