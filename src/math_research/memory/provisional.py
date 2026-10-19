"""Stable working identities over the existing Proposal Store, never accepted facts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError
from math_research.memory.episodes import Proposal, list_candidates, list_reviews

_PREFIX = {
    "claim": "CLAIM",
    "gap": "CLAIM",
    "proof": "PROOF",
    "refutation": "PROOF",
    "counterexample": "COUNTEREXAMPLE",
    "evidence": "EVIDENCE",
    "failed_attempt": "FAILED",
    "revision": "APPROACH",
    "branch": "APPROACH",
}


def provisional_object_id(candidate: Proposal) -> str | None:
    prefix = _PREFIX.get(candidate.kind)
    if prefix is None or candidate.source_fields.get("origin") == "source_digest":
        return None  # Advisory Source Digest and relation authority are unchanged.
    digest = (
        hashlib.sha256(f"{candidate.problem_id}:{candidate.candidate_id}".encode())
        .hexdigest()[:16]
        .upper()
    )
    return f"{prefix}-P{digest}"


def backfill_provisional_records(ot_dir: Path, problem_id: str, episode_id: str) -> dict[str, str]:
    """Add identity metadata only to saved proposals; never open or reparse raw Episodes."""
    from math_research.memory.records import store

    base = store.dossier_dir(ot_dir, problem_id)
    path = base / "archive" / "episodes" / "candidates.jsonl"
    with file_lock(path):
        lines = path.read_text("utf-8").splitlines(keepends=True)
        changed = False
        for i, line in enumerate(lines):
            if not line.strip():
                continue
            candidate = Proposal.model_validate_json(line)  # Fail closed before rewriting.
            if candidate.problem_id != problem_id:
                raise ResearchError("Proposal scope mismatch.")
            if candidate.episode_id != episode_id:
                continue
            expected = provisional_object_id(candidate)
            if candidate.object_id and candidate.object_id != expected:
                raise ResearchError("Provisional identity mismatch.")
            if expected and not candidate.object_id:
                value = json.loads(line)
                value["object_id"] = expected
                lines[i] = json.dumps(value, ensure_ascii=False) + "\n"
                changed = True
        if changed:
            atomic_write_text(path, "".join(lines))
    return episode_local_mapping(ot_dir, problem_id, episode_id)


def episode_local_mapping(ot_dir: Path, problem_id: str, episode_id: str) -> dict[str, str]:
    reviews = {r.candidate_id: r for r in list_reviews(ot_dir, problem_id)}
    mapping: dict[str, str] = {}
    for candidate in list_candidates(ot_dir, problem_id, episode_id):
        if not candidate.local_id or not candidate.object_id:
            continue
        review = reviews.get(candidate.candidate_id)
        if review and review.decision == "reject":
            continue
        identity = (
            review.mapped_id if review and review.decision == "accept" else candidate.object_id
        )
        if identity:
            if candidate.local_id in mapping and mapping[candidate.local_id] != identity:
                raise ResearchError("Ambiguous Episode-local identity.")
            mapping[candidate.local_id] = identity
    return mapping


def resolve_episode_target(ot_dir: Path, problem_id: str, episode_id: str, local_id: str) -> str:
    candidate = next(
        (
            c
            for c in list_candidates(ot_dir, problem_id, episode_id)
            if c.local_id == local_id and c.kind in {"claim", "gap"}
        ),
        None,
    )
    identity = episode_local_mapping(ot_dir, problem_id, episode_id).get(local_id)
    if candidate is None or not identity:
        raise ResearchError("NO_UNAMBIGUOUS_TARGET")
    return identity


def priority_direction_target(content: str) -> str:
    """Only explicit Direction priority/target fields; never infer from mathematical prose."""
    directions: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    field: str | None = None
    for line in content.splitlines():
        if re.fullmatch(r"## DIRECTION-\d+\s*", line, re.I):
            current = {}
            directions.append(current)
            field = None
        elif line.startswith("# ") or line.startswith("## "):
            current = None
            field = None
        elif current is not None:
            match = re.fullmatch(r"\*\*(target|priority)\*\*\s*:?(.*)", line.strip(), re.I)
            plain = re.fullmatch(r"(target|priority)\s*:\s*(.*)", line.strip(), re.I)
            if match or plain:
                item = match or plain
                assert item is not None
                field = item[1].lower()
                if item[2].strip():
                    current[field] = item[2].strip()
                    field = None
            elif line.strip().startswith("**"):
                field = None
            elif field and line.strip():
                current[field] = line.strip()
                field = None
    top = [d for d in directions if d.get("priority", "").strip("` ") == "1"]
    if len(top) != 1:
        raise ResearchError("NO_UNAMBIGUOUS_TARGET")
    refs = set(re.findall(r"\b(?:GAP|RESULT|CLAIM)-\d+\b", top[0].get("target", "")))
    if len(refs) != 1:
        raise ResearchError("NO_UNAMBIGUOUS_TARGET")
    return refs.pop()
