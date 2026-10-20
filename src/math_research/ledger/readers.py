"""Scoped full-body readers shared by retrieval and services."""

import hashlib
from pathlib import Path

from math_research.core.errors import ResearchError
from math_research.ledger.archive import source_path
from math_research.ledger.episodes import list_episodes
from math_research.ledger.records import store


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
