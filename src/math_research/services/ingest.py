"""External harness output enters through deterministic provisional ingestion."""

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import yaml

from math_research.core.errors import ResearchError
from math_research.ledger.archive import archive_source
from math_research.ledger.episodes import (
    DecisionKind,
    _front_matter,
    extract_candidates,
    list_episodes,
    review_candidate,
)
from math_research.ledger.preview import preview_episode as preview_episode


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


def ingest_episode(
    state: Path,
    problem_id: str,
    filename: str,
    raw: bytes,
    *,
    provenance: str,
    expected_sha256: str | None = None,
    archive_only: bool = False,
) -> dict:
    from math_research.ledger.checkpoint import checkpoint_transaction

    with checkpoint_transaction(state, problem_id):
        return _publish_episode(
            state,
            problem_id,
            filename,
            raw,
            provenance=provenance,
            expected_sha256=expected_sha256,
            archive_only=archive_only,
        )


def _publish_episode(
    state: Path,
    problem_id: str,
    filename: str,
    raw: bytes,
    *,
    provenance: str,
    expected_sha256: str | None = None,
    archive_only: bool = False,
) -> dict:
    preview = preview_episode(state, problem_id, filename, raw)
    if not archive_only and not preview["can_publish"]:
        codes = sorted({d["code"] for d in preview["diagnostics"] if d["severity"] == "ERROR"})
        details = "; ".join(
            d["message"] for d in preview["diagnostics"] if d["severity"] == "ERROR"
        )[:600]
        raise ResearchError(
            "Episode lint ERROR: "
            + ", ".join(codes)
            + ": "
            + details
            + "; use preview or explicit archive_only."
        )
    if expected_sha256 and preview["sha256"] != expected_sha256:
        raise ResearchError("Episode changed since preview.")
    duplicate = any(e.content_sha256 == preview["sha256"] for e in list_episodes(state))
    content = raw.decode("utf-8-sig")
    metadata: dict
    if archive_only:
        metadata = {}
    else:
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
        output_metadata=None if archive_only else preview["metadata"],
    )
    return {
        "episode": episode.model_dump(mode="json"),
        "candidates": []
        if archive_only
        else [c.model_dump(mode="json") for c in extract_candidates(state, episode)],
        "duplicate": duplicate,
        "canonical_records_created": 0,
        "structured_published": not archive_only,
        "diagnostics": preview["diagnostics"],
    }


def save_note(
    state: Path, problem_id: str, *, kind: str, title: str, body: str, provenance: str
) -> dict:
    """Stage one ordinary Episode proposal, with the same archive and deduplication.

    No alternative note store or canonicalization path is introduced. Ambiguous
    multi-section Markdown must use the complete Episode API instead.
    """
    headings = {
        "claim": "Claim",
        "gap": "Gap",
        "failed_attempt": "Failed Attempt",
        "evidence": "Evidence",
        "counterexample": "Counterexample",
    }
    if kind not in headings or not title.strip() or "\n" in title or "\r" in title:
        raise ResearchError("Use a supported note kind and a nonempty single-line title.")
    if not body.strip():
        raise ResearchError("A provisional note requires its complete body.")
    metadata = yaml.safe_dump({"note_provenance": provenance}, allow_unicode=True)
    raw = f"---\n{metadata}---\n\n## {headings[kind]}: {title}\n\n{body}\n".encode()
    preview = preview_episode(state, problem_id, "note.md", raw)
    candidates = preview["candidates"]
    if len(candidates) != 1 or candidates[0].kind != kind:
        raise ResearchError(
            "Note must stage one candidate; use research_ingest_episode for sections."
        )
    return ingest_episode(state, problem_id, "note.md", raw, provenance=provenance)


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
