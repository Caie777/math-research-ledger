"""Deterministic scoped navigation policy; scores never grant mathematical authority.

Intent vocabulary is general research language, not mathematical synonyms. Lexical
seeds and explicit records/relations supply relevance; Resolver supplies all state.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from math_research.memory.records import store
from math_research.memory.relations.ledger import active_relations
from math_research.memory.state import KnowledgeState
from math_research.retrieval.index import IndexDoc, search_documents


class RecallIntent(BaseModel):
    temporal_intent: Literal["CURRENT", "HISTORICAL", "ANY"] = "ANY"
    research_state_intent: Literal["OPEN", "FAILED", "RESOLVED", "ANY"] = "ANY"
    preferred_types: tuple[str, ...] = ()
    relation_intent: Literal["NONE", "DEPENDENCY", "RELATED", "MULTI_HOP"] = "NONE"


class RecallScore(BaseModel):
    lexical: float = 0
    type_match: float = 0
    state_match: float = 0
    temporal_match: float = 0
    relation: float = 0
    authority: float = 0
    provenance_currentness: float = 0

    @property
    def total_score(self) -> float:
        return sum(self.model_dump().values())


class RankedRecord(BaseModel):
    record_id: str
    score: RecallScore
    lexical_score: float
    reasons: list[str]
    expansion: list[dict] = Field(default_factory=list)


# All contributions live here. No domain words, fixture IDs or gold are consulted.
WEIGHTS = dict(
    lexical=10.0,
    type_match=9.0,
    type_mismatch=-3.0,
    state_match=9.0,
    state_mismatch=-8.0,
    current=7.0,
    stale=-12.0,
    historical=10.0,
    historical_mismatch=-3.0,
    canonical=2.0,
    raw_source=-4.0,
    active=3.0,
    neutral_claim=2.0,
    explicit_anchor=32.0,
    lexical_expansion=6.0,
    thread=2.0,
)
RELATION_WEIGHTS = {
    "PROVES": 0.9,
    "REFUTES": 1.0,
    "INVALIDATES": 1.0,
    "USES": 0.9,
    "DEPENDS_ON": 0.9,
    "REVISES": 0.8,
    "SUPERSEDES": 0.8,
    "SPECIAL_CASE_OF": 0.55,
    "GENERALIZES": 0.55,
    "STRENGTHENS": 0.7,
    "WEAKENS": 0.7,
    "SAME_AS": 0.8,
    "PROOF_TARGET": 0.8,
    "FAILED_PROOF": 1.0,
    "EVIDENCE_TARGET": 0.55,
}
MAX_SEEDS = 15
MAX_CANDIDATES = 200
MAX_HOPS = 2
MAX_NEIGHBORS = 32
MAX_FRONTIER = 64
HOP_DECAY = 0.55
STALE_STATES = {"SUPERSEDED", "REVISED", "INVALIDATED", "REFUTED", "HISTORICAL"}


def _signal(query: str, english: str, chinese: tuple[str, ...]) -> bool:
    return bool(re.search(r"\b(?:" + english + r")\b", query, re.I)) or any(
        word in query for word in chinese
    )


def detect_intent(query: str) -> RecallIntent:
    """Small bilingual research-language rules; ambiguity preserves both types."""
    current = _signal(query, "current|latest|now|currently", ("当前", "现在", "最新", "现有"))
    history = _signal(
        query,
        "earlier|previous|initial|formerly|old|before\\s+revision",
        ("之前", "早期", "原先", "修订前"),
    )
    opened = _signal(
        query,
        "open|unresolved|remains|remaining|missing|gaps?",
        ("未解决", "尚未", "尚缺", "还缺", "剩余", "缺口"),
    )
    failed = _signal(
        query,
        "failed|failure|tried|attempted|abandoned|dead\\s+end|already\\s+try",
        ("失败", "尝试过", "行不通", "死路"),
    )
    resolved = _signal(query, "resolved|settled|closed", ("已解决", "已闭合"))
    gap_type = _signal(query, "gaps?", ("缺口",))
    if resolved:
        opened = False
    dependency = _signal(
        query,
        "depends|dependency|dependencies|prerequisites?|prior|required|needed|used|uses|using",
        ("依赖", "前提", "使用", "需要"),
    )
    attack = _signal(
        query,
        "counterexamples?|witness|disproved|disprove|refuted|refute|attacked|invalidated",
        ("反例", "推翻", "驳倒", "失效"),
    )
    evidence = _signal(
        query, "evidence|computation|computational|observations", ("证据", "计算", "观测")
    )
    proof = _signal(query, "proofs?|prove|proved|proving", ("证明",))
    claim = _signal(
        query,
        "claims?|statements?|results?",
        (
            "命题",
            "结果",
        ),
    )
    preferred = (
        ("failed",)
        if failed
        else ("gap",)
        if opened or gap_type
        else ("claim",)
        if dependency
        else ("counterexample",)
        if attack
        else ("evidence", "proof")
        if evidence and proof
        else ("evidence",)
        if evidence
        else ("proof",)
        if proof
        else ("claim",)
        if claim or current or history
        else ()
    )
    return RecallIntent(
        temporal_intent="ANY" if current == history else "CURRENT" if current else "HISTORICAL",
        research_state_intent="FAILED"
        if failed
        else "OPEN"
        if opened
        else "RESOLVED"
        if resolved
        else "ANY",
        preferred_types=preferred,
        relation_intent="MULTI_HOP"
        if failed and (dependency or attack)
        else "DEPENDENCY"
        if dependency
        else "RELATED"
        if attack
        else "NONE",
    )


def record_type(doc: IndexDoc, state: KnowledgeState | None) -> str:
    if state and state.kind == "OPEN_GAP":
        return "gap"
    return doc.artifact_type.removeprefix("dossier:")


def rank_records(
    state_root: Path,
    pid: str,
    documents: list[IndexDoc],
    states: dict[str, KnowledgeState],
    query: str,
    *,
    anchor_id: str | None = None,
    existing_ids: set[str] | None = None,
    thread_id: str | None = None,
) -> tuple[RecallIntent, list[RankedRecord]]:
    """Union lexical, scoped direct, graph and intent candidates, then additive scoring."""
    intent = detect_intent(query)
    docs = {d.artifact_id: d for d in documents if d.problem_id == pid}
    lexical = {
        d.artifact_id: score for d, score in search_documents(list(docs.values()), query, k=100)
    }
    top = max(lexical.values(), default=1.0)
    candidates = set(lexical) | ((existing_ids or set()) & docs.keys())
    seeds = sorted(lexical, key=lambda ident: (-lexical[ident], ident))[:MAX_SEEDS]
    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)

    def edge(source: str, target: str, relation: str) -> None:
        if source in docs and target in docs:
            adjacency[source].append((target, relation))
            adjacency[target].append((source, relation))

    for accepted_relation in active_relations(state_root, pid):
        if accepted_relation.relation in RELATION_WEIGHTS:
            edge(
                accepted_relation.source_id, accepted_relation.target_id, accepted_relation.relation
            )
    for ident, resolver_state in states.items():
        if ident not in docs or resolver_state.authority != "CANONICAL":
            continue
        for dependency in resolver_state.dependencies:
            edge(ident, dependency, "DEPENDS_ON")
    # Record attachments are explicit provenance, not inferred PROVES/REFUTES edges.
    for proof in store.list_proof_attempts(state_root, pid):
        for target in proof.claim_links:
            edge(proof.id, target, "PROOF_TARGET")
    for failed_record in store.list_failed_attempts(state_root, pid):
        for artifact in failed_record.artifacts:
            if artifact.startswith("PROOF-"):
                edge(failed_record.id, artifact, "FAILED_PROOF")
    for evidence_record in store.list_evidence(state_root, pid):
        edge(evidence_record.id, evidence_record.claim_id, "EVIDENCE_TARGET")

    relation_scores: dict[str, float] = {}
    paths: dict[str, list[dict]] = defaultdict(list)
    if anchor_id is not None and anchor_id in docs:
        candidates.add(anchor_id)
        seeds = [anchor_id, *[ident for ident in seeds if ident != anchor_id]]
        relation_scores[anchor_id] = WEIGHTS["explicit_anchor"]
    for seed in seeds:
        base = (
            WEIGHTS["explicit_anchor"]
            if seed == anchor_id
            else WEIGHTS["lexical_expansion"] * lexical.get(seed, 0) / top
        )
        frontier: list[tuple[str, list[str], list[str], float]] = [(seed, [seed], [], base)]
        for hop in range(1, MAX_HOPS + 1):
            following = []
            for source, visited, relations, contribution in frontier:
                neighbors = sorted(
                    set(adjacency.get(source, [])),
                    key=lambda pair: (-RELATION_WEIGHTS[pair[1]], pair),
                )[:MAX_NEIGHBORS]
                for target, relation in neighbors:
                    if target in visited:
                        continue
                    weight = RELATION_WEIGHTS[relation]
                    if intent.relation_intent == "DEPENDENCY" and relation in {
                        "USES",
                        "DEPENDS_ON",
                    }:
                        weight = 1.0
                    value = contribution * weight * (HOP_DECAY if hop > 1 else 1.0)
                    candidates.add(target)
                    if value > relation_scores.get(target, 0):
                        relation_scores[target] = value
                        paths[target] = [
                            dict(
                                seed_id=seed,
                                hops=hop,
                                record_ids=[*visited, target],
                                relations=[*relations, relation],
                                contribution=value,
                            )
                        ]
                    following.append((target, [*visited, target], [*relations, relation], value))
            frontier = sorted(following, key=lambda row: (-row[3], row[0], row[1]))[:MAX_FRONTIER]

    if intent != RecallIntent():
        compatible = [
            ident
            for ident, d in docs.items()
            if record_type(d, states.get(ident)) in intent.preferred_types
        ]
        candidates.update(
            sorted(compatible, key=lambda ident: (-lexical.get(ident, 0), ident))[:MAX_CANDIDATES]
        )
    # Preserve a true no-match for neutral text; intent alone is never a truth conclusion.
    candidates = set(
        sorted(
            candidates,
            key=lambda ident: (
                ident != anchor_id,
                -relation_scores.get(ident, 0),
                -lexical.get(ident, 0),
                ident,
            ),
        )[:MAX_CANDIDATES]
    )
    ranked = []
    for ident in candidates:
        doc = docs[ident]
        state = states.get(ident)
        kind = record_type(doc, state)
        canonical = bool(state and state.authority == "CANONICAL")
        score = RecallScore(
            lexical=WEIGHTS["lexical"] * lexical.get(ident, 0) / top,
            relation=relation_scores.get(ident, 0),
            authority=WEIGHTS["canonical"] if canonical else WEIGHTS["raw_source"],
        )
        if intent.preferred_types:
            score.type_match = (
                WEIGHTS["type_match"]
                if kind in intent.preferred_types
                else WEIGHTS["type_mismatch"]
            )
        elif kind == "claim":
            score.type_match = WEIGHTS["neutral_claim"]
        if canonical and state:
            active = state.research_state not in STALE_STATES
            score.provenance_currentness = WEIGHTS["active"] if active else 0
            if thread_id and thread_id in state.thread_ids:
                score.provenance_currentness += WEIGHTS["thread"]
            if intent.research_state_intent == "OPEN" and kind == "gap":
                score.state_match = (
                    WEIGHTS["state_match"]
                    if state.research_state == "OPEN"
                    else WEIGHTS["state_mismatch"]
                )
            elif intent.research_state_intent == "FAILED":
                score.state_match = (
                    WEIGHTS["state_match"]
                    if kind == "failed"
                    else WEIGHTS["state_match"] / 2
                    if state.research_state == "INVALIDATED"
                    else 0
                )
            elif intent.research_state_intent == "RESOLVED":
                score.state_match = (
                    WEIGHTS["state_match"] if state.research_state == "RESOLVED" else 0
                )
            if intent.temporal_intent == "CURRENT":
                score.temporal_match = WEIGHTS["current"] if active else WEIGHTS["stale"]
            elif intent.temporal_intent == "HISTORICAL":
                score.temporal_match = (
                    WEIGHTS["historical"]
                    if state.research_state in {"REVISED", "SUPERSEDED"}
                    else WEIGHTS["historical_mismatch"]
                )
        reasons = (
            ["textual"]
            if ident in lexical
            else ["intent_compatible" if kind in intent.preferred_types else "structured_candidate"]
        )
        if paths[ident]:
            reasons.append("relation_expansion")
        ranked.append(
            RankedRecord(
                record_id=ident,
                score=score,
                lexical_score=lexical.get(ident, 0),
                reasons=reasons,
                expansion=paths[ident],
            )
        )
    ranked.sort(key=lambda record: (-record.score.total_score, record.record_id))
    return intent, ranked
