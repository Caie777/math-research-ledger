"""INTERNAL Recall related-object view; query scores never become memory edges."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from math_research.core.errors import ResearchError
from math_research.ledger.episodes import list_candidates, list_episodes, list_reviews
from math_research.ledger.records import store
from math_research.ledger.relations.ledger import active_relations
from math_research.ledger.relations.policy import LOGICAL_RELATIONS
from math_research.retrieval.index import IndexDoc, gather_documents, search_documents
from math_research.retrieval.index import scoped_memory_documents as scoped_memory_documents

RelevanceCategory = Literal[
    "directly_relevant",
    "useful_prerequisite",
    "analogous_result",
    "failed_route_worth_recalling",
    "background",
    "irrelevant",
]


class MemoryHit(BaseModel):
    object_id: str
    object_type: str
    title: str
    excerpt: str
    retrieval_score: float = 0
    retrieval_reasons: list[str] = Field(default_factory=list)
    hard_relation: str | None = None
    relevance_score: float | None = None
    category: RelevanceCategory | None = None
    short_reason: str = ""
    validation_status: str = "retrieved"
    navigation_kind: str = "memory"
    record_status: str | None = None
    caveats: list[str] = Field(default_factory=list)


class ExpansionSuggestion(BaseModel):
    object_id: str
    short_reason: str
    validation_status: Literal["ready_for_reassessment", "out_of_scope_target"]
    hit: MemoryHit | None = None


class RelatedResearch(BaseModel):
    problem_id: str
    target_id: str
    query: str
    hits: list[MemoryHit]
    expansion_suggestions: list[ExpansionSuggestion] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provider: str | None = None
    actual_models: list[str] = Field(default_factory=list)
    reasoning_effort: str | None = None
    elapsed_seconds: float = 0
    usage: dict | None = None


def memory_document(ot_dir: Path, problem_id: str, object_type: str, object_id: str) -> IndexDoc:
    doc = scoped_memory_documents(ot_dir, problem_id).get(f"{object_type}:{object_id}")
    if doc is None:
        raise ResearchError(f"Memory object {object_id} is absent in {problem_id}.")
    return doc


def _hit(doc: IndexDoc, reasons: list[str], score: float = 0) -> MemoryHit:
    navigation = {
        "dossier:claim": "claim",
        "dossier:proof": "proof",
        "dossier:counterexample": "counterexample",
        "dossier:failed": "failed_attempt",
        "dossier:evidence": "evidence",
        "dossier:episode": "episode",
    }.get(doc.artifact_type, "memory")
    return MemoryHit(
        object_id=doc.artifact_id,
        object_type=doc.artifact_type,
        title=doc.title,
        excerpt=doc.text[:1200],
        retrieval_score=score,
        retrieval_reasons=reasons,
        navigation_kind=navigation,
        record_status=doc.record_status,
        caveats=doc.caveats,
    )


def retrieve_related_memory(
    ot_dir: Path,
    problem_id: str,
    target_id: str,
    *,
    query: str | None = None,
    recall_limit: int = 24,
    expansion_ids: list[str] | None = None,
    documents: list[IndexDoc] | None = None,
) -> RelatedResearch:
    """Broad recall combines lexical hits, direct records and provenance in one Problem."""
    if not 1 <= recall_limit <= 100:
        raise ResearchError("recall_limit must be between 1 and 100 (model input budget).")
    scoped_docs = (
        documents if documents is not None else gather_documents(ot_dir, problem_id=problem_id)
    )
    keyed_documents = scoped_memory_documents(ot_dir, problem_id, documents=scoped_docs)
    by_id = {doc.artifact_id: doc for doc in keyed_documents.values()}
    candidate = next(
        (
            c
            for c in list_candidates(ot_dir, problem_id)
            if target_id in {c.candidate_id, c.object_id}
        ),
        None,
    )
    target_doc = by_id.get(target_id)
    if candidate is None and target_doc is None:
        raise ResearchError(f"Research target {target_id} is absent in {problem_id}.")
    if candidate:
        text = candidate.summary or candidate.body or candidate.title
    else:
        assert target_doc is not None
        text = target_doc.text
    query_text = query.strip() if query and query.strip() else text[:700]
    sources = {candidate.episode_id} if candidate else set()
    neighbors: dict[str, str] = {}
    gap_ids: set[str] = set()
    target_ids = {target_id}
    reviews = list_reviews(ot_dir, problem_id)
    for review in reviews:
        if review.decision != "accept":
            continue
        if review.candidate_id == target_id and review.mapped_id:
            target_ids.add(review.mapped_id)
        if review.mapped_id in target_ids or review.source_id in target_ids:
            sources.add(review.episode_id)
    # Unaccepted research still leads to its original file, never to a hard edge.
    for item in list_candidates(ot_dir, problem_id):
        if item.target_id in target_ids or target_ids.intersection(item.uses):
            sources.add(item.episode_id)
    # Reviewed Gap/Failure/Approach target metadata is a direct record, not a
    # mathematical closure. Include resolved gaps too, to preserve route history.
    for review in reviews:
        if (
            review.decision == "accept"
            and review.mapped_id
            and review.reviewed_candidate
            and review.reviewed_candidate.kind != "relation"
            and review.reviewed_candidate.target_id in target_ids
        ):
            neighbors[review.mapped_id] = "direct_reviewed_record"
    for claim in store.list_claims(ot_dir, problem_id):
        if claim.type == "OPEN_GAP":
            gap_ids.add(claim.id)
        if claim.id in target_ids:
            neighbors.update({dep: "DEPENDS_ON" for dep in claim.depends_on})
            sources.update(
                source for source in claim.source_artifacts if source.startswith("EPISODE-")
            )
        elif target_ids.intersection(claim.depends_on):
            neighbors[claim.id] = "reverse_dependency"
    for proof in store.list_proof_attempts(ot_dir, problem_id):
        if target_ids.intersection(proof.claim_links):
            neighbors[proof.id] = "direct_proof_record"
        if proof.id in target_ids:
            neighbors.update({cid: "proof_target" for cid in proof.claim_links})
    for failure in store.list_failed_attempts(ot_dir, problem_id):
        if (target_ids | set(neighbors)).intersection([*failure.artifacts, *failure.tags]):
            neighbors[failure.id] = "direct_failed_attempt"
    for evidence in store.list_evidence(ot_dir, problem_id):
        if evidence.claim_id in target_ids:
            neighbors[evidence.id] = "direct_evidence_record"
    mathematical_targets = target_ids | {
        ident for ident, reason in neighbors.items() if reason == "direct_proof_record"
    }
    for approach in store.list_approaches(ot_dir, problem_id):
        if target_ids.intersection(approach.resulting_artifacts) or any(
            r.decision == "accept"
            and r.mapped_id == approach.id
            and r.reviewed_candidate
            and r.reviewed_candidate.target_id in target_ids
            for r in reviews
        ):
            neighbors[approach.id] = "direct_approach_record"
            mathematical_targets.add(approach.id)
    for counterexample in store.list_counterexamples(ot_dir, problem_id):
        if counterexample.target_id in mathematical_targets:
            neighbors[counterexample.id] = "direct_counterexample_record"
            sources.update(counterexample.source_artifacts)
        if counterexample.id in target_ids:
            neighbors[counterexample.target_id] = "counterexample_target"
            sources.update(counterexample.source_artifacts)
    confirmations: dict[str, list[str]] = {}
    for edge in active_relations(ot_dir, problem_id):
        if edge.source_id in target_ids:
            neighbors[edge.target_id] = edge.relation
            confirmations.setdefault(edge.target_id, []).append(edge.label)
        if edge.target_id in mathematical_targets:
            neighbors[edge.source_id] = edge.relation
            confirmations.setdefault(edge.source_id, []).append(edge.label)
    # Provenance of the mathematical neighborhood includes full Proof sources,
    # accepted and pending Episode interpretations, and explicit source links.
    for review in reviews:
        if review.decision == "accept" and review.mapped_id in neighbors:
            sources.add(review.episode_id)
    for claim in store.list_claims(ot_dir, problem_id):
        if claim.id in neighbors:
            sources.update(claim.source_artifacts)
    for evidence in store.list_evidence(ot_dir, problem_id):
        if evidence.id in neighbors:
            sources.update(evidence.source_artifacts)
    hits: dict[str, MemoryHit] = {}

    def add(object_id: str, reason: str, score: float = 0) -> None:
        doc = by_id.get(object_id)
        if doc is None or object_id in target_ids:
            return
        hit = hits.setdefault(object_id, _hit(doc, [], score))
        if reason not in hit.retrieval_reasons:
            hit.retrieval_reasons.append(reason)
        hit.retrieval_score = max(hit.retrieval_score, score)
        hit.retrieval_reasons.extend(
            x for x in confirmations.get(object_id, []) if x not in hit.retrieval_reasons
        )
        recorded = neighbors.get(object_id)
        hit.hard_relation = recorded if recorded in LOGICAL_RELATIONS else None
        if recorded and recorded not in LOGICAL_RELATIONS and recorded not in hit.retrieval_reasons:
            hit.retrieval_reasons.append(recorded)
        if hit.navigation_kind == "claim" and object_id in gap_ids:
            hit.navigation_kind = "gap"

    for object_id in neighbors:
        add(object_id, "hard_neighbor_or_direct_record")
    for episode_id in sources:
        add(episode_id, "source_episode")
    for review in reviews:
        if review.decision == "accept" and review.episode_id in sources and review.mapped_id:
            add(review.mapped_id, "same_episode")
    for doc, score in search_documents(scoped_docs, query_text, k=recall_limit * 3):
        if f"{doc.artifact_type}:{doc.artifact_id}" in keyed_documents:
            add(doc.artifact_id, "textual", score)
    # Recent sources are recall candidates only, never mandatory logical prerequisites.
    for episode in sorted(
        list_episodes(ot_dir, problem_id), key=lambda e: e.imported_at, reverse=True
    )[:4]:
        add(episode.episode_id, "recent_source")
    result = RelatedResearch(problem_id=problem_id, target_id=target_id, query=query_text, hits=[])
    for object_id in expansion_ids or []:
        if object_id not in by_id:
            raise ResearchError(f"Expansion object {object_id} is absent in current Problem.")
        add(object_id, "retrieval_expansion")
    # Invalid hard targets can suggest a new soft query, but never enlarge the hard whitelist.
    result.hits = sorted(
        hits.values(),
        key=lambda h: (
            h.hard_relation is None,
            "retrieval_expansion" not in h.retrieval_reasons,
            "hard_neighbor_or_direct_record" not in h.retrieval_reasons,
            "source_episode" not in h.retrieval_reasons,
            -h.retrieval_score,
            h.object_id,
        ),
    )[:recall_limit]
    return result


