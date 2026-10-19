"""Confirmed model POST; read-only preflight/history; existing Human Review staging."""

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import Field

from math_research.agent.source_digest import review, store
from math_research.agent.source_digest.context import build_context
from math_research.agent.source_digest.models import (
    DigestRun,
    DigestSettings,
    Locator,
    SourceDigestContext,
    Strict,
)
from math_research.agent.source_digest.runtime import execute
from math_research.memory.sources import source_papers


class Preflight(Strict):
    context: SourceDigestContext
    context_sha256: str
    settings: DigestSettings


class Start(Strict):
    settings: DigestSettings
    context_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    confirmed: Literal[True]


class LocationInput(Strict):
    locator: Locator
    supporting_span: str = Field(min_length=1, max_length=350)
    confirmed: Literal[True]


def install_source_digest_routes(app: FastAPI, ot_dir: Path, write_header: Callable) -> Callable:
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="source-digest")
    jobs: dict[str, Future[DigestRun]] = {}
    lock = threading.Lock()

    def source_scope(pid: str, source_id: str) -> None:
        if not any(p.id == source_id for p in source_papers(ot_dir, pid)):
            raise HTTPException(404, "Source not found in this Problem.")

    def scoped_run(pid: str, digest_id: str) -> DigestRun:
        run = store.read_run(ot_dir, digest_id)
        if run.problem_id != pid:
            raise HTTPException(404, "Digest not found in this Problem.")
        return run

    def view(run: DigestRun) -> DigestRun:
        run.source_changed = not review.source_current(ot_dir, run)
        if run.status == "RUNNING" and (run.digest_id not in jobs or jobs[run.digest_id].done()):
            run.status, run.error = (
                "FAILED",
                "Executor no longer attached; explicitly start a new digest.",
            )
        if run.digest:
            run.digest.proposals = review.proposals(ot_dir, run)
        return run

    @app.get("/api/problems/{pid}/sources/{source_id}/digest-context")
    def preflight(pid: str, source_id: str) -> Preflight:
        context = build_context(ot_dir, pid, source_id)
        return Preflight(
            context=context, context_sha256=store.context_sha(context), settings=DigestSettings()
        )

    @app.post(
        "/api/problems/{pid}/sources/{source_id}/digest", dependencies=[Depends(write_header)]
    )
    def start(pid: str, source_id: str, request: Start) -> DigestRun:
        context = build_context(ot_dir, pid, source_id)
        if store.context_sha(context) != request.context_sha256:
            raise HTTPException(409, "Source/context changed; inspect and confirm fresh preflight.")
        with lock:
            if any(not future.done() for future in jobs.values()):
                raise HTTPException(409, "A source digest is already running.")
            run = store.prepare(ot_dir, context, request.settings)
            jobs[run.digest_id] = executor.submit(execute, ot_dir, run)
        return run

    @app.get("/api/problems/{pid}/sources/{source_id}/digests")
    def history(pid: str, source_id: str) -> list[DigestRun]:
        source_scope(pid, source_id)
        with lock:
            return [view(run) for run in store.list_runs(ot_dir, pid, source_id)]

    @app.get("/api/problems/{pid}/source-digests/{digest_id}")
    def poll(pid: str, digest_id: str) -> DigestRun:
        with lock:
            return view(scoped_run(pid, digest_id))

    @app.get("/api/problems/{pid}/source-digests/{digest_id}/proposals")
    def proposals(pid: str, digest_id: str) -> list:
        return review.proposals(ot_dir, scoped_run(pid, digest_id))

    @app.post(
        "/api/problems/{pid}/source-digests/{digest_id}/proposals/{proposal_id}/review",
        dependencies=[Depends(write_header)],
    )
    def stage(pid: str, digest_id: str, proposal_id: str) -> dict[str, str]:
        return review.stage_for_review(ot_dir, scoped_run(pid, digest_id), proposal_id)

    @app.post(
        "/api/problems/{pid}/source-digests/{digest_id}/proposals/{proposal_id}/location",
        dependencies=[Depends(write_header)],
    )
    def location(pid: str, digest_id: str, proposal_id: str, request: LocationInput) -> dict:
        review.confirm_location(
            ot_dir,
            scoped_run(pid, digest_id),
            proposal_id,
            request.locator,
            request.supporting_span,
        )
        return {"provenance_status": "VALID"}

    return lambda: executor.shutdown(wait=False, cancel_futures=True)
