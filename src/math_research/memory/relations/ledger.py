"""Append-only hard-candidate staging and authority-aware active relation projection."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal
from uuid import uuid4

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError
from math_research.core.jsonl import append_jsonl, atomic_append_jsonl, read_jsonl
from math_research.memory.episodes import Proposal, list_candidates, list_reviews
from math_research.memory.records import store
from math_research.memory.records.write_boundary import assert_human_write, human_write
from math_research.memory.relations.models import (
    AdjudicationOutput,
    AdjudicationPolicy,
    AdjudicationRun,
    ConfirmedRelation,
    PoolItem,
    RelationDecision,
    RelationProposal,
    ScoutRun,
)
from math_research.memory.relations.policy import LOGICAL_RELATIONS, validate_mathematical_relation

SENSITIVE_RELATIONS = frozenset({"REFUTES", "INVALIDATES", "SUPERSEDES"})


def workflow_path(ot_dir: Path, pid: str, name: str) -> Path:
    store.require_dossier(ot_dir, pid)
    return store.dossier_dir(ot_dir, pid) / "archive/hard_relations" / name


def get_policy(ot_dir: Path, pid: str) -> AdjudicationPolicy:
    path = workflow_path(ot_dir, pid, "policy.json")
    return (
        AdjudicationPolicy.model_validate_json(path.read_text("utf-8"))
        if path.is_file()
        else AdjudicationPolicy()
    )


@human_write
def set_policy(ot_dir: Path, pid: str, policy: AdjudicationPolicy) -> AdjudicationPolicy:
    path = workflow_path(ot_dir, pid, "policy.json")
    with file_lock(path):
        atomic_write_text(path, policy.model_dump_json(indent=2) + "\n")
    return policy


def source_candidate(ot_dir: Path, pid: str, ident: str) -> Proposal:
    source = next(
        (
            c
            for c in list_candidates(ot_dir, pid)
            if c.candidate_id == ident and c.kind != "relation"
        ),
        None,
    )
    if source is None:
        raise ResearchError("Hard relation requires an existing source mathematical Proposal.")
    return source


def canonical_ids(ot_dir: Path, pid: str) -> set[str]:
    ids: set[str] = set()
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
        ids.update(item.id for item in reader(ot_dir, pid))
    return ids


def aliases(ot_dir: Path, pid: str) -> dict[str, str]:
    latest = {r.candidate_id: r for r in list_reviews(ot_dir, pid)}
    return {
        key: r.mapped_id
        for key, r in latest.items()
        if r.decision == "accept"
        and r.mapped_id
        and r.reviewed_candidate
        and r.reviewed_candidate.kind != "relation"
    }


def resolve_reference(ot_dir: Path, pid: str, ref: str) -> str:
    return aliases(ot_dir, pid).get(ref, ref)


def validate_proposal(
    ot_dir: Path,
    pid: str,
    source_id: str,
    relation: str,
    target_id: str,
    *,
    allowed: list[str] | None = None,
    allow_pending_target: bool = False,
) -> None:
    source = source_candidate(ot_dir, pid, source_id)
    if relation not in LOGICAL_RELATIONS:
        raise ResearchError("Unknown hard relation type.")
    target = resolve_reference(ot_dir, pid, target_id)
    ids = canonical_ids(ot_dir, pid)
    if target not in ids:
        if not allow_pending_target or target_id not in {
            c.candidate_id for c in list_candidates(ot_dir, pid) if c.kind != "relation"
        }:
            raise ResearchError("Target must be a canonical object in this Problem.")
    if (
        allowed is not None
        and target_id not in allowed
        and target not in {resolve_reference(ot_dir, pid, i) for i in allowed}
    ):
        raise ResearchError("Target is outside the allowed recall/correction scope.")
    mapped = aliases(ot_dir, pid).get(source_id)
    if mapped == target or source_id == target_id:
        raise ResearchError("Self relation is not a valid hard proposal.")
    if relation == "PROVES" and source.kind != "proof":
        raise ResearchError(
            "PROVES requires a Proof source; finite checks cannot prove a Statement."
        )
    target_kind = next(
        (c.kind for c in list_candidates(ot_dir, pid) if c.candidate_id == target_id), None
    )
    claim_ids = {c.id for c in store.list_claims(ot_dir, pid)}
    proof_ids = {p.id for p in store.list_proof_attempts(ot_dir, pid)}
    approach_ids = {a.id for a in store.list_approaches(ot_dir, pid)}
    if (
        relation in {"PROVES", "REFUTES"}
        and target not in claim_ids
        and target_kind not in {"claim", "gap"}
    ):
        raise ResearchError("PROVES/REFUTES targets a Statement.")
    if (
        relation == "INVALIDATES"
        and target not in proof_ids | approach_ids
        and target_kind != "proof"
    ):
        raise ResearchError("INVALIDATES targets a Proof or Approach.")
    if relation in {"REFUTES", "INVALIDATES"} and source.kind not in {
        "counterexample",
        "proof",
        "refutation",
    }:
        raise ResearchError("REFUTES/INVALIDATES requires a Proof or Counterexample source.")
    if mapped and target in ids:
        validate_mathematical_relation(ot_dir, pid, mapped, relation, target)


def list_proposals(ot_dir: Path, pid: str) -> list[RelationProposal]:
    return read_jsonl(workflow_path(ot_dir, pid, "pool.jsonl"), RelationProposal)


def add_proposal(ot_dir: Path, proposal: RelationProposal) -> RelationProposal:
    if (
        source_candidate(ot_dir, proposal.problem_id, proposal.source_candidate_id).episode_id
        != proposal.episode_id
    ):
        raise ResearchError("Source is not in the proposal Episode.")
    validate_proposal(
        ot_dir,
        proposal.problem_id,
        proposal.source_candidate_id,
        proposal.proposed_relation,
        proposal.target_id,
        allowed=proposal.allowed_target_ids if proposal.origin == "model_scout" else None,
        allow_pending_target=proposal.origin == "episode_explicit",
    )
    key = ":".join(
        (
            proposal.problem_id,
            proposal.source_candidate_id,
            proposal.proposed_relation,
            proposal.target_id,
        )
    )
    proposal.proposal_id = "HARD-" + hashlib.sha256(key.encode()).hexdigest()[:16].upper()
    path = workflow_path(ot_dir, proposal.problem_id, "pool.jsonl")
    with file_lock(path):
        existing = next(
            (
                p
                for p in read_jsonl(path, RelationProposal)
                if p.proposal_id == proposal.proposal_id
            ),
            None,
        )
        if existing:
            return existing
        append_jsonl(path, proposal)
    return proposal


def list_scout_runs(ot_dir: Path, pid: str, episode_id: str | None = None) -> list[ScoutRun]:
    runs = read_jsonl(workflow_path(ot_dir, pid, "scout_runs.jsonl"), ScoutRun)
    return [r for r in runs if episode_id is None or r.episode_id == episode_id]


def list_adjudication_runs(ot_dir: Path, pid: str) -> list[AdjudicationRun]:
    return read_jsonl(workflow_path(ot_dir, pid, "adjudication_runs.jsonl"), AdjudicationRun)


def append_workflow(ot_dir: Path, pid: str, name: str, record: ScoutRun | AdjudicationRun) -> None:
    path = workflow_path(ot_dir, pid, name)
    with file_lock(path):
        append_jsonl(path, record)


def decision_history(
    ot_dir: Path, pid: str, proposal_id: str | None = None
) -> list[RelationDecision]:
    items = read_jsonl(workflow_path(ot_dir, pid, "decisions.jsonl"), RelationDecision)
    return [d for d in items if proposal_id is None or d.proposal_id == proposal_id]


def append_decision(
    ot_dir: Path,
    proposal: RelationProposal,
    output: AdjudicationOutput,
    *,
    confirmed_by: Literal["human", "model"],
    run: AdjudicationRun | None = None,
    source_sha256: str | None = None,
    target_sha256: str | None = None,
) -> RelationDecision:
    if confirmed_by == "human":
        assert_human_write()
    if output.decision in {"CONFIRM", "CORRECT"}:
        candidates = list_candidates(ot_dir, proposal.problem_id)
        source_items = [
            c
            for c in candidates
            if c.candidate_id in {proposal.explicit_candidate_id, proposal.source_candidate_id}
            and c.source_fields.get("origin") == "source_digest"
        ]
        if source_items:
            if confirmed_by != "human":
                raise ResearchError("Source Digest relations require Human Relation Review.")
            from math_research.agent.source_digest.review import validate_acceptance

            for candidate in source_items:
                # LOW source objects must already have passed edited Human Review.
                reviewed = any(
                    r.candidate_id == candidate.candidate_id and r.decision == "accept"
                    for r in list_reviews(ot_dir, proposal.problem_id)
                )
                validate_acceptance(
                    ot_dir, candidate, {"body": candidate.body} if reviewed else None
                )
                if candidate.kind == "relation":
                    effective = output.corrected_relation or proposal.proposed_relation
                    validate_acceptance(
                        ot_dir,
                        candidate.model_copy(update={"relation": effective}),
                        {"body": candidate.body} if reviewed else None,
                    )
    if confirmed_by == "model" and get_policy(ot_dir, proposal.problem_id).mode == "HUMAN_ONLY":
        raise ResearchError("Human only policy does not permit new model decisions.")
    if confirmed_by == "model" and (
        run is None
        or run.problem_id != proposal.problem_id
        or run.proposal_id != proposal.proposal_id
    ):
        raise ResearchError("Model decisions require the matching adjudication run.")
    if output.decision == "CORRECT":
        if not output.corrected_relation or not output.corrected_target_id:
            raise ResearchError("CORRECT requires corrected_relation and corrected_target_id.")
        validate_proposal(
            ot_dir,
            proposal.problem_id,
            proposal.source_candidate_id,
            output.corrected_relation,
            output.corrected_target_id,
            allowed=proposal.allowed_target_ids if confirmed_by == "model" else None,
        )
    elif output.corrected_relation is not None or output.corrected_target_id is not None:
        raise ResearchError("Only CORRECT may supply corrected fields.")
    elif output.decision == "CONFIRM":
        validate_proposal(
            ot_dir,
            proposal.problem_id,
            proposal.source_candidate_id,
            proposal.proposed_relation,
            proposal.target_id,
            allow_pending_target=proposal.origin == "episode_explicit",
        )
    if confirmed_by not in {"human", "model"} or confirmed_by == "model" and run is None:
        raise ResearchError("Model decisions require an adjudication run.")
    decision = RelationDecision(
        decision_id="HARD-DECISION-" + uuid4().hex,
        proposal_id=proposal.proposal_id,
        problem_id=proposal.problem_id,
        decision=output.decision,
        confirmed_by=confirmed_by,
        rationale=output.rationale,
        corrected_relation=output.corrected_relation,
        corrected_target_id=output.corrected_target_id,
        provider=run.provider if run else None,
        model=(run.actual_models[-1] if run.actual_models else run.requested_model)
        if run
        else None,
        reasoning_effort=run.reasoning_effort if run else None,
        adjudication_run_id=run.run_id if run else None,
        source_sha256=source_sha256,
        target_sha256=target_sha256,
    )
    path = workflow_path(ot_dir, proposal.problem_id, "decisions.jsonl")
    with file_lock(path):
        atomic_append_jsonl(path, decision)
    return decision


@human_write
def human_adjudicate(
    ot_dir: Path, pid: str, proposal_id: str, output: AdjudicationOutput
) -> RelationDecision:
    proposal = next((p for p in list_proposals(ot_dir, pid) if p.proposal_id == proposal_id), None)
    if proposal is None:
        raise ResearchError("No hard proposal in this Problem.")
    return append_decision(ot_dir, proposal, output, confirmed_by="human")


@human_write
def enroll_explicit(ot_dir: Path, pid: str, episode_id: str) -> list[RelationProposal]:
    """Explicit user enrollment only; no migration or read-time workflow write."""
    candidates = list_candidates(ot_dir, pid, episode_id)
    local = {c.local_id: c.candidate_id for c in candidates if c.kind != "relation" and c.local_id}
    output = []
    for candidate in candidates:
        if (
            candidate.kind != "relation"
            or candidate.semantic_validation_status is not None
            or candidate.relation not in LOGICAL_RELATIONS
        ):
            continue
        source = candidate.origin_candidate_id or local.get(candidate.source_local_id or "")
        if source is None and candidate.candidate_id.endswith("-REL"):
            source = candidate.candidate_id.removesuffix("-REL")
        if not source or not candidate.target_id:
            continue
        target = local.get(candidate.target_id, candidate.target_id)
        output.append(
            add_proposal(
                ot_dir,
                RelationProposal(
                    proposal_id="",
                    problem_id=pid,
                    episode_id=episode_id,
                    source_candidate_id=source,
                    proposed_relation=candidate.relation,
                    target_id=target,
                    confidence=1.0,
                    rationale=candidate.body,
                    origin="episode_explicit",
                    validator_status="EPISODE_EXPLICIT",
                    allowed_target_ids=[target],
                    explicit_candidate_id=candidate.candidate_id,
                ),
            )
        )
    return output


def list_pool(
    ot_dir: Path,
    pid: str,
    *,
    episode_id: str | None = None,
    source_id: str | None = None,
    status: str | None = None,
) -> list[PoolItem]:
    history = decision_history(ot_dir, pid)
    policy = get_policy(ot_dir, pid)
    mappings = aliases(ot_dir, pid)
    ids = canonical_ids(ot_dir, pid)
    runs = list_scout_runs(ot_dir, pid)
    reviews = list_reviews(ot_dir, pid)
    output = []
    for proposal in list_proposals(ot_dir, pid):
        if (
            episode_id
            and proposal.episode_id != episode_id
            or source_id
            and proposal.source_candidate_id != source_id
        ):
            continue
        decisions = [d for d in history if d.proposal_id == proposal.proposal_id]
        human = [d for d in decisions if d.confirmed_by == "human"]
        latest = (human or decisions)[-1] if decisions else None
        legacy_accepted = next(
            (
                r
                for r in reversed(reviews)
                if r.decision == "accept"
                and r.relation == proposal.proposed_relation
                and r.source_id == mappings.get(proposal.source_candidate_id)
                and r.target_id == mappings.get(proposal.target_id, proposal.target_id)
            ),
            None,
        )
        if not human and legacy_accepted:
            latest = None
        item = PoolItem(
            **proposal.model_dump(),
            latest_decision=latest,
            source_id=mappings.get(proposal.source_candidate_id),
            scout_run_ids=[
                r.run_id
                for r in runs
                if any(x.proposal_id == proposal.proposal_id for x in r.results)
            ],
        )
        if latest:
            item.confirmed_by = latest.confirmed_by
            if latest.decision in {"REJECT", "UNCERTAIN"}:
                item.current_status = "REJECTED" if latest.decision == "REJECT" else "UNCERTAIN"
            else:
                item.confirmation = (
                    "HUMAN_CONFIRMED" if latest.confirmed_by == "human" else "MODEL_CONFIRMED"
                )
                item.effective_relation = latest.corrected_relation or proposal.proposed_relation
                item.effective_target_id = mappings.get(
                    latest.corrected_target_id or proposal.target_id,
                    latest.corrected_target_id or proposal.target_id,
                )
                item.current_status = item.confirmation
                if not item.source_id or item.source_id not in ids:
                    item.current_status = "confirmed_pending_source"
                elif item.effective_target_id not in ids:
                    item.current_status = "confirmed_pending_target"
                elif latest.confirmed_by == "model" and (
                    policy.mode == "HUMAN_ONLY"
                    or policy.require_human_for_state_changing
                    and item.effective_relation in SENSITIVE_RELATIONS
                ):
                    item.current_status = "model_confirmed_pending_human"
                else:
                    try:
                        validate_proposal(
                            ot_dir,
                            pid,
                            proposal.source_candidate_id,
                            item.effective_relation,
                            item.effective_target_id,
                        )
                        if latest.confirmed_by == "model":
                            from math_research.memory.relations.content import (
                                canonical_text,
                                digest,
                                source_text,
                            )

                            if latest.source_sha256 != digest(
                                source_text(ot_dir, pid, proposal.source_candidate_id)
                            ) or latest.target_sha256 != digest(
                                canonical_text(ot_dir, pid, item.effective_target_id)
                            ):
                                item.current_status = "confirmed_stale_input"
                                item.inactive_reason = (
                                    "Reviewed input changed; explicit re-adjudication required."
                                )
                            else:
                                item.active = True
                        else:
                            item.active = True
                    except ResearchError as exc:
                        item.current_status = "confirmed_inactive"
                        item.inactive_reason = str(exc)
        else:
            # Existing actual Human reviews remain Human; old model qualifications do not.
            accepted = next(
                (
                    r
                    for r in reversed(reviews)
                    if r.decision == "accept"
                    and r.relation == proposal.proposed_relation
                    and r.source_id == item.source_id
                    and r.target_id == mappings.get(proposal.target_id, proposal.target_id)
                ),
                None,
            )
            if accepted:
                item.confirmed_by = "human"
                item.confirmation = "HUMAN_CONFIRMED"
                item.current_status = "HUMAN_CONFIRMED"
                item.effective_relation = proposal.proposed_relation
                item.effective_target_id = accepted.target_id
                item.active = True
        if status is None or item.current_status == status:
            output.append(item)
    return output


def active_relations(ot_dir: Path, pid: str) -> list[ConfirmedRelation]:
    """The one operational relation seam. Reads never migrate or write records."""
    mappings = aliases(ot_dir, pid)
    ids = canonical_ids(ot_dir, pid)
    pool = list_pool(ot_dir, pid)
    overridden = {
        (
            mappings.get(p.source_candidate_id),
            p.proposed_relation,
            mappings.get(p.target_id, p.target_id),
        )
        for p in pool
        if p.latest_decision and p.latest_decision.confirmed_by == "human"
    }
    output = []
    for review in list_reviews(ot_dir, pid):
        source = mappings.get(review.source_id or "", review.source_id)
        if (
            review.decision != "accept"
            or review.relation not in LOGICAL_RELATIONS
            or source not in ids
            or review.target_id not in ids
        ):
            continue
        if (source, review.relation, review.target_id) in overridden:
            continue
        output.append(
            ConfirmedRelation(
                decision_id=review.candidate_id,
                episode_id=review.episode_id,
                source_id=source,
                target_id=review.target_id,
                relation=review.relation,
                confirmed_by="human",
            )
        )
    for item in pool:
        if (
            item.active
            and item.latest_decision
            and item.source_id
            and item.effective_relation
            and item.effective_target_id
        ):
            d = item.latest_decision
            output.append(
                ConfirmedRelation(
                    decision_id=d.decision_id,
                    proposal_id=item.proposal_id,
                    episode_id=item.episode_id,
                    source_id=item.source_id,
                    target_id=item.effective_target_id,
                    relation=item.effective_relation,
                    confirmed_by=d.confirmed_by,
                    provider=d.provider,
                    model=d.model,
                    reasoning_effort=d.reasoning_effort,
                )
            )
    # A persisted actual Human review has precedence over any later model decision.
    human_keys = {
        (r.source_id, r.relation, r.target_id) for r in output if r.confirmed_by == "human"
    }
    unique = {}
    for edge in output:
        key = (edge.source_id, edge.relation, edge.target_id)
        if edge.confirmed_by == "model" and key in human_keys:
            continue
        unique[key] = edge
    return list(unique.values())
