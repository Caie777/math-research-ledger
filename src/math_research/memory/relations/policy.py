"""Stable mathematical relation vocabulary; relevance is computed at query time."""

from pathlib import Path

from math_research.core.errors import ResearchError

LOGICAL_RELATIONS = frozenset(
    {
        "SAME_AS",
        "PROVES",
        "REFUTES",
        "INVALIDATES",
        "USES",
        "DEPENDS_ON",
        "REVISES",
        "SUPERSEDES",
        "SPECIAL_CASE_OF",
        "GENERALIZES",
        "STRENGTHENS",
        "WEAKENS",
    }
)
HARD_CONFIDENCE_THRESHOLD = 0.8
COMPLETED_VALIDATIONS = frozenset(
    {"legacy", "accepted_by_validator", "uncertain", "no_hard_relation"}
)


def validate_mathematical_relation(
    ot_dir: Path, problem_id: str, source_id: str, relation: str, target_id: str
) -> None:
    """Type-check a human acceptance; no verification or status write occurs here."""
    from math_research.memory.records import store
    from math_research.memory.records.counterexamples import get_counterexample, read_counterexample

    proof = next(
        (p for p in store.list_proof_attempts(ot_dir, problem_id) if p.id == source_id), None
    )
    if relation == "PROVES":
        if proof and proof.conclusion_relation == "REFUTES":
            raise ResearchError("A refutation Proof cannot PROVES its target.")
        if get_counterexample(ot_dir, problem_id, source_id):
            raise ResearchError("A Counterexample cannot PROVES a Statement.")
        return
    if relation not in {"REFUTES", "INVALIDATES"}:
        return
    counterexample = get_counterexample(ot_dir, problem_id, source_id)
    if counterexample:
        read_counterexample(ot_dir, counterexample)
        if counterexample.target_id != target_id:
            raise ResearchError("Counterexample relation must match its precise reviewed target.")
    elif proof:
        base = store.dossier_dir(ot_dir, problem_id).resolve()
        path = (base / (proof.body_path or "")).resolve()
        if not path.is_relative_to(base / "proof_attempts") or not path.is_file():
            raise ResearchError("REFUTES/INVALIDATES requires an available full Proof body.")
        if not path.read_text(encoding="utf-8").strip():
            raise ResearchError("REFUTES/INVALIDATES requires a nonempty full Proof body.")
        if relation == "REFUTES" and (
            proof.conclusion_relation != "REFUTES" or target_id not in proof.claim_links
        ):
            raise ResearchError("REFUTES requires a refutation Proof with this target.")
    else:
        raise ResearchError("REFUTES/INVALIDATES requires a canonical Counterexample or Proof.")
    if relation == "REFUTES":
        if store.get_claim(ot_dir, problem_id, target_id) is None:
            raise ResearchError("REFUTES attacks a Statement, not a Proof or Approach.")
    elif not any(
        p.id == target_id for p in store.list_proof_attempts(ot_dir, problem_id)
    ) and not any(a.id == target_id for a in store.list_approaches(ot_dir, problem_id)):
        raise ResearchError("INVALIDATES targets a Proof or Approach, never its underlying Claim.")
