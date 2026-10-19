"""Small, framework-independent adapter for the human Research Episode UI.

All writes delegate to Phase 1 archive/extraction/review functions. Reading a
preview or candidate never changes the authoritative Problem Record.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from tempfile import TemporaryDirectory

from math_research.core.errors import ResearchError
from math_research.memory.archive import source_path
from math_research.memory.episodes import (
    DecisionKind,
    Proposal,
    ResearchEpisode,
    ReviewDecision,
    _front_matter,
    archive_episode,
    extract_candidates,
    list_candidates,
    list_episodes,
    list_reviews,
    review_candidate,
)
from math_research.memory.records import store
from math_research.retrieval.index import IndexDoc, search
from math_research.retrieval.selection import build_claim_detail

MAX_UPLOAD_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class EpisodePreview:
    filename: str
    size_bytes: int
    front_matter: dict[str, object]
    body: str


@dataclass(frozen=True)
class ImportResult:
    episode: ResearchEpisode
    candidates: list[Proposal]
    duplicate: bool


@dataclass(frozen=True)
class ProposalWithReview:
    candidate: Proposal
    review: ReviewDecision | None


@dataclass(frozen=True)
class EpisodeSummary:
    episode: ResearchEpisode
    candidate_count: int
    accepted: int
    rejected: int
    deferred: int
    pending: int


def _decode_upload(filename: str, raw: bytes) -> tuple[str, str]:
    safe_name = PureWindowsPath(filename).name
    if not safe_name or safe_name in {".", ".."} or not safe_name.lower().endswith((".md", ".txt")):
        raise ResearchError("Upload one .md or .txt Research Episode file.")
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ResearchError("Markdown upload must be nonempty and at most 10 MiB.")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ResearchError("Research Episode must be UTF-8 Markdown.") from exc
    if not content.strip():
        raise ResearchError("Research Episode cannot be empty.")
    return safe_name, content


def preview_uploaded_episode(filename: str, raw: bytes) -> EpisodePreview:
    name, content = _decode_upload(filename, raw)
    front_matter, offset = _front_matter(content)
    return EpisodePreview(
        filename=name,
        size_bytes=len(raw),
        front_matter=front_matter,
        body="\n".join(content.splitlines()[offset:]),
    )


def import_uploaded_episode(
    ot_dir: Path,
    problem_id: str,
    filename: str,
    raw: bytes,
    *,
    provenance: str | None = None,
) -> ImportResult:
    """Preserve upload bytes and original basename; use the official archive API."""
    store.require_dossier(ot_dir, problem_id)
    name, content = _decode_upload(filename, raw)
    # A Windows UTF-8 BOM is an encoding marker, not mathematical content.
    # Normalize it before Phase 1 parsing so front matter remains visible.
    normalized = content.encode("utf-8")
    digest = hashlib.sha256(normalized).hexdigest()
    duplicate = any(episode.content_sha256 == digest for episode in list_episodes(ot_dir))
    with TemporaryDirectory(prefix="math_research-episode-") as directory:
        source = Path(directory) / name
        source.write_bytes(normalized)
        episode = archive_episode(ot_dir, problem_id, source, provenance=provenance)
    candidates = extract_candidates(ot_dir, episode)
    return ImportResult(episode=episode, candidates=candidates, duplicate=duplicate)


def candidates_with_reviews(
    ot_dir: Path, problem_id: str, episode_id: str
) -> list[ProposalWithReview]:
    store.require_dossier(ot_dir, problem_id)
    if not any(item.episode_id == episode_id for item in list_episodes(ot_dir, problem_id)):
        raise ResearchError(f"No Episode {episode_id} in {problem_id}.")
    reviews = {item.candidate_id: item for item in list_reviews(ot_dir, problem_id)}
    return [
        ProposalWithReview(candidate=item, review=reviews.get(item.candidate_id))
        for item in list_candidates(ot_dir, problem_id, episode_id)
    ]


def review_episode_candidate(
    ot_dir: Path,
    problem_id: str,
    candidate_id: str,
    decision: DecisionKind,
    *,
    edits: dict[str, object] | None = None,
) -> ReviewDecision:
    """Review through the shared Human Review authority gate."""
    if decision not in {"accept", "reject", "defer"}:
        raise ResearchError("Decision must be accept, reject, or defer.")
    return review_candidate(ot_dir, problem_id, candidate_id, decision, edits=edits)


def recent_episodes(ot_dir: Path, problem_id: str) -> list[EpisodeSummary]:
    store.require_dossier(ot_dir, problem_id)
    candidates = list_candidates(ot_dir, problem_id)
    reviews = {item.candidate_id: item for item in list_reviews(ot_dir, problem_id)}
    rows = []
    for episode in reversed(list_episodes(ot_dir, problem_id)):
        linked = [item for item in candidates if item.episode_id == episode.episode_id]
        counts = {"accept": 0, "reject": 0, "defer": 0}
        for candidate in linked:
            review = reviews.get(candidate.candidate_id)
            if review:
                counts[review.decision] += 1
        rows.append(
            EpisodeSummary(
                episode=episode,
                candidate_count=len(linked),
                accepted=counts["accept"],
                rejected=counts["reject"],
                deferred=counts["defer"],
                pending=len(linked) - sum(counts.values()),
            )
        )
    return rows


def episode_source(ot_dir: Path, problem_id: str, episode_id: str) -> str:
    episode = next(
        (item for item in list_episodes(ot_dir, problem_id) if item.episode_id == episode_id),
        None,
    )
    if episode is None:
        raise ResearchError(f"No Episode {episode_id} in {problem_id}.")
    path = source_path(ot_dir, episode.archive_path)
    if not path.is_file():
        raise ResearchError("Archived Episode path is missing.")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != episode.content_sha256:
        raise ResearchError("Archived Episode content hash changed.")
    return raw.decode("utf-8")


def current_object_rows(ot_dir: Path, problem_id: str, kind: str) -> list[tuple[str, str]]:
    store.require_dossier(ot_dir, problem_id)
    if kind == "Claim":
        objects = [c for c in store.list_claims(ot_dir, problem_id) if c.type != "OPEN_GAP"]
        return [(c.id, f"{c.statement[:100]} [{c.status}]") for c in objects]
    if kind == "Gap":
        return [
            (c.id, f"{c.statement[:100]} [{c.status}]")
            for c in store.list_claims(ot_dir, problem_id)
            if c.type == "OPEN_GAP"
        ]
    if kind == "Proof":
        return [
            (p.id, f"{p.title} [{p.status}]") for p in store.list_proof_attempts(ot_dir, problem_id)
        ]
    if kind == "Counterexample":
        return [
            (c.id, f"{c.title or c.target_id} [{c.status}]")
            for c in store.list_counterexamples(ot_dir, problem_id)
        ]
    if kind == "Failed Attempt":
        return [(f.id, f.attempted_method) for f in store.list_failed_attempts(ot_dir, problem_id)]
    if kind == "Evidence":
        return [(e.id, e.summary[:100]) for e in store.list_evidence(ot_dir, problem_id)]
    raise ResearchError(f"Unknown research object type: {kind}.")


def object_detail(ot_dir: Path, problem_id: str, object_id: str) -> str:
    """Read one scoped object's complete available text and source metadata."""
    store.require_dossier(ot_dir, problem_id)
    claim = store.get_claim(ot_dir, problem_id, object_id)
    if claim:
        return build_claim_detail(ot_dir, problem_id, object_id).model_dump_json(indent=2)
    from math_research.memory.records.counterexamples import get_counterexample, read_counterexample

    counterexample = get_counterexample(ot_dir, problem_id, object_id)
    if counterexample:
        body, path = read_counterexample(ot_dir, counterexample)
        return (
            f"{counterexample.model_dump_json(indent=2)}\n\nFull Counterexample: {path}\n\n{body}"
        )
    for proof in store.list_proof_attempts(ot_dir, problem_id):
        if proof.id == object_id:
            body, path = read_full_proof(ot_dir, problem_id, object_id)
            return f"{proof.model_dump_json(indent=2)}\n\nFull Proof: {path}\n\n{body}"
    for collection in (
        store.list_failed_attempts(ot_dir, problem_id),
        store.list_evidence(ot_dir, problem_id),
    ):
        for item in collection:
            if item.id == object_id:
                return item.model_dump_json(indent=2)
    if object_id.startswith("EPISODE-"):
        return episode_source(ot_dir, problem_id, object_id)
    raise ResearchError(f"No research object {object_id} in {problem_id}.")


def read_full_proof(ot_dir: Path, problem_id: str, proof_id: str) -> tuple[str, Path]:
    """Return the full Proof body and its validated Problem Record-local source path."""
    store.require_dossier(ot_dir, problem_id)
    proof = next(
        (item for item in store.list_proof_attempts(ot_dir, problem_id) if item.id == proof_id),
        None,
    )
    if proof is None or not proof.body_path:
        raise ResearchError(f"Full Proof body unavailable: {proof_id}.")
    base = store.dossier_dir(ot_dir, problem_id).resolve()
    path = (base / proof.body_path).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ResearchError(f"Full Proof body unavailable: {proof_id}.")
    return path.read_text(encoding="utf-8"), path


def scoped_search(ot_dir: Path, problem_id: str, query: str, *, limit: int = 30) -> list[IndexDoc]:
    store.require_dossier(ot_dir, problem_id)
    if not query.strip():
        return []
    return [
        doc
        for doc, _score in search(ot_dir, query.strip(), k=limit, problem_id=problem_id)
        if doc.problem_id == problem_id
    ]
