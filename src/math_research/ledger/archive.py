"""Project raw-source archive and explicit, resumable legacy-copy migration.

Proposal/review/reconciliation ledgers remain Problem-scoped. Reading never
migrates. Legacy identities are opaque; equal sources may retain several old IDs
but share one physical project copy after explicit migration.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

from pydantic import ValidationError

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError
from math_research.core.jsonl import rewrite_jsonl
from math_research.ledger.records import store

if TYPE_CHECKING:
    from math_research.ledger.episodes import EpisodeOutputMetadata, ResearchEpisode


def archive_index(ot_dir: Path) -> Path:
    return ot_dir / "research_archive" / "index.jsonl"


def _legacy_indices(ot_dir: Path) -> list[Path]:
    return sorted((ot_dir / "problems").glob("*/archive/episodes/index.jsonl"))


def _rows(path: Path) -> list[dict]:
    """Fail closed: a copy migration must not silently drop corrupt index rows."""
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("Episode index row must be an object")
            rows.append(row)
        except ValueError as exc:
            raise ResearchError(f"Invalid Episode index {path}:{number}: {exc}") from exc
    return rows


def _records(path: Path) -> list[ResearchEpisode]:
    from math_research.ledger.episodes import ResearchEpisode

    try:
        return [ResearchEpisode.model_validate(row) for row in _rows(path)]
    except ValidationError as exc:
        raise ResearchError(f"Invalid Episode metadata in {path}: {exc}") from exc


def load_episodes(ot_dir: Path, problem_id: str | None = None) -> list[ResearchEpisode]:
    """Read global metadata first, then legacy fallback, without any writes.

    A Problem view supplies the compatibility ``problem_id`` used by the current
    interpretation pipeline; it never changes primary membership or source ID.
    """
    by_id: dict[str, ResearchEpisode] = {}
    for path in [archive_index(ot_dir), *_legacy_indices(ot_dir)]:
        for record in _records(path):
            previous = by_id.get(record.episode_id)
            if previous and previous.content_sha256 != record.content_sha256:
                raise ResearchError(f"Episode ID collision: {record.episode_id}")
            if previous is None:
                by_id[record.episode_id] = record
    records = sorted(by_id.values(), key=lambda e: (e.imported_at, e.episode_id))
    if problem_id is None:
        return records
    return [
        e.model_copy(update={"problem_id": problem_id})
        for e in records
        if problem_id in {e.primary_problem_id, *e.related_problem_ids}
    ]


def source_path(ot_dir: Path, relative: str) -> Path:
    # Persisted Windows paths remain readable on POSIX installations too.
    parts = PureWindowsPath(relative)
    if parts.is_absolute() or parts.drive or ".." in parts.parts:
        raise ResearchError(f"Unsafe Episode source path: {relative}")
    path = (ot_dir.parent / Path(*parts.parts)).resolve()
    if not path.is_relative_to(ot_dir.resolve()):
        raise ResearchError(f"Episode source outside project state: {relative}")
    local = path.relative_to(ot_dir.resolve()).parts
    if not (
        local
        and local[0] == "research_archive"
        or len(local) >= 5
        and local[0] == "problems"
        and local[2:4] == ("archive", "episodes")
    ):
        raise ResearchError(f"Episode source outside raw archive directories: {relative}")
    return path


def _verified_bytes(ot_dir: Path, record: ResearchEpisode) -> bytes:
    path = source_path(ot_dir, record.archive_path)
    if not path.is_file():
        raise ResearchError(f"Missing Episode source: {record.archive_path}")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != record.content_sha256:
        raise ResearchError(f"Episode SHA-256 mismatch: {record.episode_id}")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ResearchError(f"Episode source is not UTF-8: {record.episode_id}") from exc
    return raw


def _next_path(
    ot_dir: Path, instant: datetime, used: set[str], *, reuse_digest: str | None = None
) -> str:
    directory = ot_dir / "research_archive" / instant.strftime("%Y/%m")
    day = instant.strftime("%Y_%m_%d")
    seq = 1
    while True:
        target = directory / f"{day}_{seq:02d}.md"
        relative = target.relative_to(ot_dir.parent).as_posix()
        reusable = (
            reuse_digest is not None
            and target.is_file()
            and hashlib.sha256(target.read_bytes()).hexdigest() == reuse_digest
        )
        if relative not in used and (not target.exists() or reusable):
            used.add(relative)
            return relative
        seq += 1


def archive_source(
    ot_dir: Path,
    problem_id: str | None,
    filename: str,
    raw: bytes,
    instant: datetime,
    *,
    related_problem_ids: list[str],
    thread_ids: list[str],
    provenance: str | None,
    source_language: str | None,
    output_metadata: EpisodeOutputMetadata | None = None,
) -> ResearchEpisode:
    from math_research.ledger.episodes import ResearchEpisode

    for scope in dict.fromkeys([*([problem_id] if problem_id else []), *related_problem_ids]):
        store.require_dossier(ot_dir, scope)
    digest = hashlib.sha256(raw).hexdigest()
    index = archive_index(ot_dir)
    with file_lock(index):
        global_records = _records(index)
        all_records = load_episodes(ot_dir)
        matches = [e for e in all_records if e.content_sha256 == digest]
        if matches:
            # Prefer the old scope's identity when equal legacy bytes have several
            # opaque IDs, so a repeated import never changes its candidate IDs.
            record = min(
                matches,
                key=lambda e: (
                    e.primary_problem_id != problem_id,
                    problem_id not in e.related_problem_ids,
                ),
            )
            if _verified_bytes(ot_dir, record) != raw:
                raise ResearchError("Source digest collision; archive import refused.")
            primary = record.primary_problem_id or problem_id
            related = list(
                dict.fromkeys(
                    [
                        *record.related_problem_ids,
                        *related_problem_ids,
                        *([problem_id] if problem_id and problem_id != primary else []),
                    ]
                )
            )
            record = ResearchEpisode.model_validate(
                record.model_dump()
                | {
                    **(output_metadata.model_dump() if output_metadata else {}),
                    "primary_problem_id": primary,
                    "problem_id": primary or "",
                    "related_problem_ids": [p for p in related if p != primary],
                    "thread_ids": list(dict.fromkeys([*record.thread_ids, *thread_ids])),
                }
            )
        else:
            ident = (
                "EPISODE-"
                + hashlib.sha256(f"project-source-v1:{digest}".encode()).hexdigest()[:16].upper()
            )
            if any(e.episode_id == ident for e in all_records):
                raise ResearchError(f"Episode ID collision: {ident}; import refused.")
            relative = _next_path(
                ot_dir, instant, {e.archive_path for e in all_records}, reuse_digest=digest
            )
            atomic_write_text(source_path(ot_dir, relative), raw.decode("utf-8"))
            record = ResearchEpisode(
                **(output_metadata.model_dump() if output_metadata else {}),
                episode_id=ident,
                problem_id=problem_id or "",
                primary_problem_id=problem_id,
                related_problem_ids=list(
                    dict.fromkeys(p for p in related_problem_ids if p != problem_id)
                ),
                archive_path=relative,
                imported_at=instant,
                source_filename=filename,
                source_language=source_language,
                content_sha256=digest,
                provenance=provenance,
                thread_ids=thread_ids,
            )
            _verified_bytes(ot_dir, record)
        replacement = [record if e.episode_id == record.episode_id else e for e in global_records]
        if not any(e.episode_id == record.episode_id for e in global_records):
            replacement.append(record)
        if replacement != global_records:
            rewrite_jsonl(index, replacement)
        return record.model_copy(update={"problem_id": problem_id or record.problem_id})
