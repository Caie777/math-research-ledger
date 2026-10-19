"""Append-only advisory artifacts, outside canonical ledgers and retrieval indexing."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

from math_research.agent.critique.models import (
    CritiqueBundle,
    CritiqueReport,
    CritiqueRun,
    CritiqueSettings,
    TargetType,
)
from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError


def directory(ot_dir: Path, critique_id: str) -> Path:
    if not re.fullmatch(r"CRITIQUE-[A-F0-9]{16}", critique_id):
        raise ResearchError("Invalid critique ID.")
    base = ot_dir.resolve() / "critiques"
    path = base / critique_id
    if base.resolve() != base or path.resolve() != path:
        raise ResearchError("Critique storage must not redirect outside its advisory directory.")
    return path


def prepare(ot_dir: Path, bundle: CritiqueBundle, settings: CritiqueSettings) -> CritiqueRun:
    raw = bundle.model_dump_json(indent=2)
    run = CritiqueRun(
        critique_id="CRITIQUE-" + uuid4().hex[:16].upper(),
        problem_id=bundle.problem_id,
        target_id=bundle.target.record_id,
        target_type=cast(TargetType, bundle.target.record_type),
        created_at=datetime.now(UTC),
        settings=settings,
        bundle_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        session_id="CRITIC-" + uuid4().hex.upper(),
        continuation_target_id=bundle.continuation_target_id,
    )
    path = directory(ot_dir, run.critique_id)
    path.mkdir(parents=True, exist_ok=False)
    atomic_write_text(path / "bundle.json", raw)
    atomic_write_text(path / "request.json", run.model_dump_json(indent=2))
    return run


def read_run(ot_dir: Path, critique_id: str) -> CritiqueRun:
    path = directory(ot_dir, critique_id)
    try:
        run = CritiqueRun.model_validate_json((path / "request.json").read_text("utf-8"))
        if run.critique_id != critique_id:
            raise ResearchError("Critique identity mismatch.")
        if (path / "report.json").is_file():
            report = CritiqueReport.model_validate_json((path / "report.json").read_text("utf-8"))
            if report.critique_id != critique_id or report.target_id != run.target_id:
                raise ResearchError("Critique report identity mismatch.")
            run.status, run.report = "COMPLETED", report
        elif (path / "failure.txt").is_file():
            run.status, run.error = "FAILED", (path / "failure.txt").read_text("utf-8")
        return run
    except FileNotFoundError as exc:
        raise ResearchError("Critique not found.") from exc


def read_bundle(ot_dir: Path, run: CritiqueRun) -> CritiqueBundle:
    raw = (directory(ot_dir, run.critique_id) / "bundle.json").read_text("utf-8")
    if hashlib.sha256(raw.encode()).hexdigest() != run.bundle_sha256:
        raise ResearchError("Critique bundle integrity check failed.")
    return CritiqueBundle.model_validate_json(raw)


def finish(
    ot_dir: Path,
    run: CritiqueRun,
    *,
    report: CritiqueReport | None = None,
    error: str | None = None,
) -> CritiqueRun:
    path = directory(ot_dir, run.critique_id)
    with file_lock(path / "completion"):
        if read_run(ot_dir, run.critique_id).status != "RUNNING":
            raise ResearchError("Completed/failed critiques are immutable; create a new critique.")
        if report is not None:
            if report.critique_id != run.critique_id or report.target_id != run.target_id:
                raise ResearchError("Critique completion identity mismatch.")
            atomic_write_text(path / "report.json", report.model_dump_json(indent=2))
        elif error:
            atomic_write_text(path / "failure.txt", error[:2000])
        else:
            raise ResearchError("Critique completion needs a report or failure.")
    return read_run(ot_dir, run.critique_id)


def claim_execution(ot_dir: Path, run: CritiqueRun) -> None:
    path = directory(ot_dir, run.critique_id)
    with file_lock(path / "execution"):
        marker = path / "started.txt"
        if marker.exists():
            raise ResearchError("Critique already executed; create a new independent session.")
        atomic_write_text(marker, run.session_id)


def list_runs(ot_dir: Path, problem_id: str) -> list[CritiqueRun]:
    base = ot_dir.resolve() / "critiques"
    if base.resolve() != base:
        raise ResearchError("Critique directory must not redirect.")
    runs = [read_run(ot_dir, path.parent.name) for path in base.glob("*/request.json")]
    return sorted(
        (r for r in runs if r.problem_id == problem_id),
        key=lambda r: (r.created_at, r.critique_id),
        reverse=True,
    )


def history(ot_dir: Path, problem_id: str, target_id: str) -> list[CritiqueRun]:
    return [r for r in list_runs(ot_dir, problem_id) if r.target_id == target_id]
