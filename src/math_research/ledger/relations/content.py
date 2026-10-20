"""Full, scoped input bodies and immutable input digests for relation adjudication."""

from __future__ import annotations

import hashlib
from pathlib import Path

from math_research.core.errors import ResearchError
from math_research.ledger.episodes import list_candidates, list_reviews
from math_research.ledger.records import store
from math_research.ledger.records.counterexamples import read_counterexample
from math_research.ledger.records.models import CounterexampleRecord


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_text(ot_dir: Path, pid: str, ident: str) -> str:
    candidate = next((c for c in list_candidates(ot_dir, pid) if c.candidate_id == ident), None)
    for review in list_reviews(ot_dir, pid):
        if (
            review.candidate_id == ident
            and review.decision == "accept"
            and review.reviewed_candidate
        ):
            candidate = review.reviewed_candidate
    if candidate is None or candidate.kind == "relation":
        raise ResearchError("Source Proposal unavailable.")
    return candidate.body


def canonical_text(ot_dir: Path, pid: str, ident: str) -> str:
    for reader in (
        store.list_claims,
        store.list_proof_attempts,
        store.list_counterexamples,
        store.list_evidence,
        store.list_failed_attempts,
        store.list_approaches,
        store.list_known_results,
        store.list_definitions,
        store.list_assumptions,
    ):
        for record in reader(ot_dir, pid):
            if record.id != ident:
                continue
            text = record.model_dump_json(indent=2)
            if isinstance(record, CounterexampleRecord):
                return text + "\n\n" + read_counterexample(ot_dir, record)[0]
            body_path = getattr(record, "body_path", None)
            if body_path:
                base = store.dossier_dir(ot_dir, pid).resolve()
                path = (base / body_path).resolve()
                if not path.is_relative_to(base) or not path.is_file():
                    raise ResearchError(
                        "Canonical full body unavailable or outside Problem Record."
                    )
                text += "\n\n" + path.read_text("utf-8")
            return text
    raise ResearchError("Exact canonical target unavailable in this Problem.")
