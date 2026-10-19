"""Proof attempts as provenance-rich artifacts.

Each submission of a formal goal/term to a backend produces a ``PROOF-*``
artifact: the exact source, the backend + version, and the verbatim
accept/reject output. Accepted proofs that target a claim add a ``validates``
edge to the artifact graph (rendered in the M35 graph view).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from math_research.core.jsonl import read_jsonl

if TYPE_CHECKING:
    pass

_SUFFIX = {
    "lean4": ".lean",
    "lean": ".lean",
    "coq": ".v",
    "smt": ".smt2",
    "z3": ".smt2",
    "sympy": ".json",
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ProofAttempt(BaseModel):
    """A recorded formal-verification attempt."""

    id: str
    backend: str
    backend_version: str | None = None
    accepted: bool
    available: bool = True
    # Timeout/crash/parse failure: the checker gave up — distinct from a genuine
    # rejection, so "the tool gave up" is never read as "the proof is wrong".
    inconclusive: bool = False
    outcome: str | None = None  # SMT: "unsat" | "sat" | "unknown"
    claim_id: str | None = None
    # Which dossier ``claim_id`` belongs to; ``None`` means the workspace claim ladder.
    # The two stores share the ``CLAIM-NNNN`` id space while proofs.jsonl is
    # workspace-global, so an unqualified id is ambiguous: one real workspace held a
    # dossier CLAIM-0001 ("for every bipartite graph H …") and a workspace CLAIM-0001
    # ("for the 4-vertex block graph …") at once. Without this field a proof of the
    # instance answers a lookup for the general statement.
    problem_id: str | None = None
    # Which campaign produced this submission. Distinct from ``problem_id`` above, and
    # deliberately so: that one answers "which claim store does claim_id belong to"
    # (identity), this one answers "was anything machine-checked while working on this
    # dossier" (provenance). Collapsing the two into one field is what made the id
    # collision possible in the first place, and an attempt to reuse ``problem_id`` for
    # the second question blocked the campaign gate outright — every agent submission
    # targets a workspace claim and so carries no ``problem_id`` at all.
    submitted_under: str | None = None
    source_path: str
    output: str = ""
    # Digest of the exact source submitted. Lets an identical resubmission be answered
    # from the ledger instead of re-running the backend. ``None`` on records written
    # before this field existed; those simply never match.
    source_sha256: str | None = None
    # True when this record answers a resubmission of source already checked, rather
    # than a fresh backend run. Recorded so the artifact never overstates what ran.
    cached: bool = False
    created_at: datetime = Field(default_factory=_utcnow)


def proofs_path(ot_dir: Path) -> Path:
    return ot_dir / "proofs.jsonl"


def list_proofs(ot_dir: Path) -> list[ProofAttempt]:
    return read_jsonl(proofs_path(ot_dir), ProofAttempt)


def get_proof(ot_dir: Path, proof_id: str) -> ProofAttempt | None:
    for proof in list_proofs(ot_dir):
        if proof.id == proof_id:
            return proof
    return None
