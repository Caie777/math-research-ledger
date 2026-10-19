"""Append-only advisory artifacts and separate human provenance confirmations."""

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from math_research.agent.source_digest.models import (
    DigestRun,
    DigestSettings,
    SourceDigest,
    SourceDigestContext,
)
from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError


def directory(ot_dir: Path, digest_id: str) -> Path:
    if not re.fullmatch(r"DIGEST-[A-F0-9]{16}", digest_id):
        raise ResearchError("Invalid source digest ID.")
    base = ot_dir.resolve() / "source_digests"
    path = base / digest_id
    if base.resolve() != base or path.resolve() != path:
        raise ResearchError("Source digest storage must not redirect.")
    return path


def context_sha(context: SourceDigestContext) -> str:
    return hashlib.sha256(context.model_dump_json(indent=2).encode()).hexdigest()


def prepare(ot_dir: Path, context: SourceDigestContext, settings: DigestSettings) -> DigestRun:
    run = DigestRun(
        digest_id="DIGEST-" + uuid4().hex[:16].upper(),
        problem_id=context.problem_id,
        source_id=context.source_id,
        source_sha256=context.source_sha256,
        created_at=datetime.now(UTC),
        settings=settings,
        context_sha256=context_sha(context),
        session_id="SOURCE-SESSION-" + uuid4().hex.upper(),
    )
    path = directory(ot_dir, run.digest_id)
    path.mkdir(parents=True, exist_ok=False)
    atomic_write_text(path / "context.json", context.model_dump_json(indent=2))
    atomic_write_text(path / "request.json", run.model_dump_json(indent=2))
    return run


def read_run(ot_dir: Path, digest_id: str) -> DigestRun:
    path = directory(ot_dir, digest_id)
    try:
        run = DigestRun.model_validate_json((path / "request.json").read_text("utf-8"))
        if run.digest_id != digest_id:
            raise ResearchError("Digest identity mismatch.")
        if (path / "digest.json").is_file():
            digest = SourceDigest.model_validate_json((path / "digest.json").read_text("utf-8"))
            if (
                digest.digest_id != digest_id
                or digest.problem_id != run.problem_id
                or digest.source_sha256 != run.source_sha256
                or digest.source_id != run.source_id
            ):
                raise ResearchError("Digest completion identity mismatch.")
            run.digest = digest
            run.status = (
                "COMPLETED"
                if digest.coverage_complete and not digest.validation_warnings
                else "PARTIAL"
            )
        elif (path / "failure.txt").is_file():
            run.status, run.error = "FAILED", (path / "failure.txt").read_text("utf-8")
        return run
    except FileNotFoundError as exc:
        raise ResearchError("Source digest not found.") from exc


def read_context(ot_dir: Path, run: DigestRun) -> SourceDigestContext:
    raw = (directory(ot_dir, run.digest_id) / "context.json").read_text("utf-8")
    if hashlib.sha256(raw.encode()).hexdigest() != run.context_sha256:
        raise ResearchError("Saved source context SHA mismatch.")
    return SourceDigestContext.model_validate_json(raw)


def finish(
    ot_dir: Path, run: DigestRun, *, digest: SourceDigest | None = None, error: str | None = None
) -> DigestRun:
    path = directory(ot_dir, run.digest_id)
    with file_lock(path / "completion"):
        if read_run(ot_dir, run.digest_id).status != "RUNNING":
            raise ResearchError("Completed digests are immutable; start a new digest.")
        if digest is not None:
            if digest.digest_id != run.digest_id or digest.source_sha256 != run.source_sha256:
                raise ResearchError("Digest identity mismatch.")
            atomic_write_text(path / "digest.json", digest.model_dump_json(indent=2))
        elif error:
            atomic_write_text(path / "failure.txt", error[:2000])
        else:
            raise ResearchError("Digest completion requires output or failure.")
    return read_run(ot_dir, run.digest_id)


def claim_execution(ot_dir: Path, run: DigestRun) -> None:
    path = directory(ot_dir, run.digest_id)
    with file_lock(path / "execution"):
        if (path / "started.txt").exists():
            raise ResearchError("Digest execution cannot reuse an old model session.")
        atomic_write_text(path / "started.txt", run.session_id)


def list_runs(ot_dir: Path, pid: str, source_id: str) -> list[DigestRun]:
    base = ot_dir.resolve() / "source_digests"
    if base.resolve() != base:
        raise ResearchError("Digest directory must not redirect.")
    runs = [read_run(ot_dir, p.parent.name) for p in base.glob("*/request.json")]
    return sorted(
        (r for r in runs if r.problem_id == pid and r.source_id == source_id),
        key=lambda r: (r.created_at, r.digest_id),
        reverse=True,
    )
