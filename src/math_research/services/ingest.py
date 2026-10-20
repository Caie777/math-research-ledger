"""External harness output enters through deterministic provisional ingestion."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from math_research.core.errors import ResearchError
from math_research.core.limits import MAX_UPLOAD_BYTES
from math_research.core.refs import VersionPin
from math_research.ledger.archive import archive_source
from math_research.ledger.episodes import (
    DecisionKind,
    ResearchEpisode,
    _front_matter,
    extract_candidates,
    list_episodes,
    parse_candidate_proposals,
    review_candidate,
    structured_episode_metadata,
)
from math_research.ledger.records import store


def ingest_file(
    state: Path, problem_id: str, file: Path, *, provenance: str, preview: bool = False
):
    raw = file.read_bytes()
    return (
        preview_episode(state, problem_id, file.name, raw)
        if preview
        else ingest_episode(state, problem_id, file.name, raw, provenance=provenance)
    )


def ingest_source_file(state: Path, problem_id: str, file: Path):
    from math_research.ledger.sources import save_source, validate_source

    return save_source(state, problem_id, validate_source(file.name, file.read_bytes()))


def preview_episode(state: Path, problem_id: str, filename: str, raw: bytes) -> dict:
    store.require_dossier(state, problem_id)
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ResearchError("Episode must contain at most 10 MiB of nonempty UTF-8 Markdown.")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ResearchError("Episode must be UTF-8.") from exc
    digest = hashlib.sha256(raw).hexdigest()
    episode = ResearchEpisode(
        episode_id="EPISODE-"
        + hashlib.sha256(f"project-source-v1:{digest}".encode()).hexdigest()[:16].upper(),
        problem_id=problem_id,
        archive_path="preview.md",
        imported_at=datetime.now(UTC),
        source_filename=Path(filename).name,
        content_sha256=digest,
    )
    proposals = parse_candidate_proposals(content, episode, store.list_claims(state, problem_id))
    if not proposals:
        raise ResearchError("No recognized Research Episode objects; source was not imported.")
    metadata, _ = _front_matter(content)
    input_versions = metadata.get("input_versions", [])
    if not isinstance(input_versions, list):
        raise ResearchError("input_versions must be a list of qualified version pins.")
    pins = [VersionPin.model_validate(pin) for pin in input_versions]
    return {
        "sha256": digest,
        "candidates": proposals,
        "metadata": structured_episode_metadata(content).model_copy(
            update={"input_versions": pins}
        ),
    }


def ingest_episode(
    state: Path,
    problem_id: str,
    filename: str,
    raw: bytes,
    *,
    provenance: str,
    expected_sha256: str | None = None,
) -> dict:
    preview = preview_episode(state, problem_id, filename, raw)
    if expected_sha256 and preview["sha256"] != expected_sha256:
        raise ResearchError("Episode changed since preview.")
    duplicate = any(e.content_sha256 == preview["sha256"] for e in list_episodes(state))
    content = raw.decode("utf-8-sig")
    metadata, _ = _front_matter(content)
    language = metadata.get("language")
    threads = metadata.get("thread_ids", [])
    if not isinstance(threads, list) or any(
        not isinstance(t, str) or not t.strip() or len(t) > 128 for t in threads
    ):
        raise ResearchError("Invalid Episode thread_ids.")
    episode = archive_source(
        state,
        problem_id,
        Path(filename).name,
        raw,
        datetime.now(UTC),
        related_problem_ids=[],
        thread_ids=threads,
        provenance=provenance,
        source_language=language if isinstance(language, str) else None,
        output_metadata=preview["metadata"],
    )
    return {
        "episode": episode.model_dump(mode="json"),
        "candidates": [c.model_dump(mode="json") for c in extract_candidates(state, episode)],
        "duplicate": duplicate,
        "canonical_records_created": 0,
    }


def review_proposal(
    state: Path, problem_id: str, candidate_id: str, decision: str, *, edits: dict | None = None
):
    if decision not in {"accept", "reject", "defer"}:
        raise ResearchError("Review must accept, reject or defer.")
    return review_candidate(
        state, problem_id, candidate_id, cast(DecisionKind, decision), edits=edits
    )


def review_from_file(
    state: Path, problem_id: str, candidate_id: str, decision: str, edits_file: Path | None = None
):
    import json

    edits = json.loads(edits_file.read_text("utf-8")) if edits_file else None
    if edits is not None and not isinstance(edits, dict):
        raise ResearchError("Review edits must be a JSON object.")
    return review_proposal(state, problem_id, candidate_id, decision, edits=edits)
