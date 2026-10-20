"""Deterministic navigation over existing records, authority and relation ledgers.

No map state is stored. Labels are excerpts, never additional mathematical records.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from math_research.ledger.episodes import list_candidates
from math_research.ledger.records import store
from math_research.ledger.relations.edges import list_edges
from math_research.ledger.relations.ledger import active_relations
from math_research.ledger.state import Authority, KnowledgeState, KnowledgeStateResolver

NodeType = Literal[
    "problem", "claim", "gap", "proof", "counterexample", "evidence", "failed_attempt"
]
Layer = Literal["current", "failed_routes", "historical"]
GROUPS: tuple[tuple[Layer, str], ...] = (
    ("current", "Current"),
    ("failed_routes", "Failed Routes"),
    ("historical", "Historical"),
)
HISTORICAL = {"REVISED", "REFUTED", "SUPERSEDED", "HISTORICAL", "INVALIDATED"}


class ResearchMapNode(BaseModel):
    id: str
    type: NodeType
    title: str
    status: str
    authority: Authority
    is_primary: bool = False
    group: Layer = "current"
    review: str = "ACCEPTED"
    verification: str = "NOT_CHECKED"
    warnings: list[str] = Field(default_factory=list)
    episode_id: str | None = None
    research_target_id: str | None = None
    critique_count: int = 0


class ResearchMapEdge(BaseModel):
    source: str
    target: str
    relation_type: str
    authority: str
    witness_id: str | None = None


class ResearchMapGroup(BaseModel):
    id: Layer
    title: str
    node_ids: list[str]


class ResearchMap(BaseModel):
    problem_id: str
    primary_target_id: str | None
    nodes: list[ResearchMapNode]
    edges: list[ResearchMapEdge]
    groups: list[ResearchMapGroup]
    warnings: list[str] = Field(default_factory=list)


def _label(text: str, fallback: str) -> str:
    return " ".join(text.split())[:120] or fallback


def unique_canonical_target(
    explicit: Iterable[str], canonical_claim_ids: Collection[str]
) -> str | None:
    targets = sorted(set(explicit).intersection(canonical_claim_ids))
    return targets[0] if len(targets) == 1 else None


def _layer(kind: NodeType, state: KnowledgeState) -> Layer:
    if state.authority != "REJECTED/HISTORICAL" and (
        kind == "failed_attempt" or kind == "proof" and state.research_state == "INVALIDATED"
    ):
        return "failed_routes"
    if state.authority == "REJECTED/HISTORICAL" or state.research_state in HISTORICAL:
        return "historical"
    return "current"


def build_research_map(ot_dir: Path, problem_id: str) -> ResearchMap:
    """Fresh read-only projection. Never guess a primary target or create relationships."""
    problem = store.require_dossier(ot_dir, problem_id)
    states = KnowledgeStateResolver(ot_dir).resolve(problem_id)
    primary = problem.primary_claim_id
    nodes = {
        problem.id: ResearchMapNode(
            id=problem.id,
            type="problem",
            title=_label(problem.title, problem.id),
            status=problem.status,
            authority="CANONICAL",
        )
    }

    def node(ident: str, kind: NodeType, title: str, episode_id: str | None = None) -> None:
        state = states.get(ident)
        if state is None:
            return
        group = _layer(kind, state)
        nodes[ident] = ResearchMapNode(
            id=ident,
            type=kind,
            title=_label(title, ident),
            status=state.research_state,
            authority=state.authority,
            is_primary=ident == primary,
            group=group,
            review=state.review,
            verification=state.verification,
            warnings=sorted(set(state.warnings)),
            episode_id=episode_id,
            research_target_id=ident
            if kind in {"claim", "gap"}
            and state.authority == "CANONICAL"
            and group == "current"
            and state.research_state != "RESOLVED"
            and state.verification != "VERIFIER_PASSED"
            else None,
        )

    for claim in store.list_claims(ot_dir, problem_id):
        node(claim.id, "gap" if claim.type == "OPEN_GAP" else "claim", claim.statement)
    proofs = store.list_proof_attempts(ot_dir, problem_id)
    proof_targets = {proof.id: set(proof.claim_links) for proof in proofs}
    for proof in proofs:
        node(proof.id, "proof", proof.title)
    for example in store.list_counterexamples(ot_dir, problem_id):
        node(example.id, "counterexample", example.title or example.construction)
    for evidence in store.list_evidence(ot_dir, problem_id):
        node(evidence.id, "evidence", evidence.summary)
    for failure in store.list_failed_attempts(ot_dir, problem_id):
        node(failure.id, "failed_attempt", failure.summary or failure.attempted_method)
    kinds: dict[str, NodeType] = {
        "claim": "claim",
        "gap": "gap",
        "proof": "proof",
        "revision": "proof",
        "refutation": "proof",
        "counterexample": "counterexample",
        "evidence": "evidence",
        "failed_attempt": "failed_attempt",
    }
    for proposal in list_candidates(ot_dir, problem_id):
        if proposal.source_fields.get("origin") == "source_digest":
            continue  # Accepted records already enter through canonical nodes above.
        state = states.get(proposal.candidate_id)
        # Accepted proposal aliases already have their canonical node; no duplicate identities.
        if state and not state.canonical_id and proposal.kind in kinds:
            node(
                proposal.candidate_id,
                kinds[proposal.kind],
                proposal.title or proposal.summary or proposal.body,
                proposal.episode_id,
            )
            if kinds[proposal.kind] == "proof":
                proof_targets[proposal.candidate_id] = (
                    {proposal.target_id} if proposal.target_id else set()
                )

    warnings = []
    if (
        primary is None
        or primary not in nodes
        or nodes[primary].type not in {"claim", "gap"}
        or nodes[primary].authority != "CANONICAL"
    ):
        primary = None
        for entry in nodes.values():
            entry.is_primary = False
        warnings.append("No primary target is designated or available; the map does not guess.")

    edges: dict[tuple[str, str, str], ResearchMapEdge] = {}

    def edge(source: str, target: str, relation: str, authority: str, witness: str | None) -> None:
        if source not in nodes or target not in nodes:
            return
        if nodes[source].authority != "CANONICAL" or nodes[target].authority != "CANONICAL":
            return
        edges[(source, target, relation)] = ResearchMapEdge(
            source=source,
            target=target,
            relation_type=relation,
            authority=authority,
            witness_id=witness,
        )

    # Use the same qualified active relation seam as the Resolver, including Human precedence.
    for relation in sorted(active_relations(ot_dir, problem_id), key=lambda r: r.decision_id):
        edge(
            relation.source_id,
            relation.target_id,
            relation.relation,
            relation.label,
            relation.decision_id,
        )
    for recorded in sorted(list_edges(ot_dir), key=lambda r: r.id):
        if recorded.relation in {"depends_on", "supersedes", "resolves"}:
            key = (recorded.source_id, recorded.target_id, recorded.relation.upper())
            if key not in edges:
                edge(*key, "recorded: human", recorded.id)
    for ident, state in sorted(states.items()):
        if ident not in nodes:
            continue
        for dependency in sorted(set(state.dependencies)):
            if not any((ident, dependency, kind) in edges for kind in ("USES", "DEPENDS_ON")):
                edge(ident, dependency, "DEPENDS_ON", "recorded dependency", None)

    # The Agent accepts Claim/Gap targets only. A proof can navigate to its one explicit target.
    for ident, recorded_targets in proof_targets.items():
        item = nodes.get(ident)
        explicit = recorded_targets | {
            e.target
            for e in edges.values()
            if e.source == ident and e.relation_type in {"PROVES", "REFUTES"}
        }
        target = unique_canonical_target(
            explicit,
            {
                ident
                for ident, node in nodes.items()
                if node.type in {"claim", "gap"} and node.authority == "CANONICAL"
            },
        )
        if item:
            item.research_target_id = target
    ordered = sorted(nodes.values(), key=lambda n: (not n.is_primary, n.type, n.id))
    return ResearchMap(
        problem_id=problem_id,
        primary_target_id=primary,
        nodes=ordered,
        edges=[edges[key] for key in sorted(edges)],
        groups=[
            ResearchMapGroup(
                id=key, title=title, node_ids=[n.id for n in ordered if n.group == key]
            )
            for key, title in GROUPS
        ],
        warnings=warnings,
    )
