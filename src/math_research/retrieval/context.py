"""INTERNAL Recall budgeted assembly over Manifest, search and provisional ledgers."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from math_research.core.errors import ResearchError
from math_research.memory.episodes import list_candidates, list_episodes, list_reviews
from math_research.memory.records import store
from math_research.memory.relations.ledger import active_relations
from math_research.memory.state import KnowledgeState, KnowledgeStateResolver, research_version
from math_research.memory.target import ResearchTarget, validate_research_target
from math_research.retrieval.index import IndexDoc, search_documents
from math_research.retrieval.policy import STALE_STATES, detect_intent
from math_research.retrieval.related_research import RelatedResearch
from math_research.retrieval.selection import ResearchMaterial, build_research_manifest

QueryPurpose = Literal["CONTINUE_RESEARCH", "RECOVER_PROOF", "TRACE_HISTORY", "FIND_FAILURES"]
Section = Literal[
    "mandatory",
    "canonical",
    "proofs",
    "counterexamples",
    "provisional",
    "failures",
    "history",
    "gaps",
    "sources",
    "research_state",
]
AUTHORITY_PROTOCOL = (
    "CANONICAL means human-recorded/accepted research memory, "
    "not automatic mathematical verification. "
    "PROVISIONAL is a working result/assumption only; VERIFIER_PASSED does not mean ACCEPTED. "
    "REJECTED/HISTORICAL, revised, refuted, superseded, invalidated material "
    "is not a positive premise. "
    "Preserve IDs of provisional dependencies used in the next Episode. "
    "Human Review is asynchronous; "
    "pending or deferred review never blocks research."
)


def estimate_tokens(text: str) -> int:
    """Deterministic model-independent estimate; UTF-8 bytes / 3, rounded up."""
    return math.ceil(len(text.encode("utf-8")) / 3)


class ContextItem(BaseModel):
    object_id: str
    section: Section
    title: str
    content: str
    state: KnowledgeState
    mandatory: bool = False
    priority: float = 0
    source_path: str | None = None
    full_text: bool = True
    conclusion_relation: Literal["PROVES", "REFUTES"] | None = None
    tier: Literal["MUST", "SHOULD", "MAY"] = "MAY"
    truncated: bool = False
    metadata_compact: bool = False


class ContextExclusion(BaseModel):
    object_id: str
    reason: str


class ResearchContextBundle(BaseModel):
    target: ResearchTarget
    purpose: QueryPurpose
    thread_id: str | None = None
    source_version: str
    header: str
    markdown: str
    items: list[ContextItem]
    excluded: list[ContextExclusion]
    unresolved_gaps: list[str]
    resolved_historical_gaps: list[str]
    warnings: list[str]
    token_budget: int
    token_estimate: int
    tokens_per_section: dict[str, int]
    section_allocations: dict[str, int]
    complete: bool
    required_context_truncated: bool = False
    required_record_ids: list[str] = Field(default_factory=list)
    required_omitted_ids: list[str] = Field(default_factory=list)
    estimator: str = "ceil(UTF-8 bytes / 3); estimate, not model tokenizer count"


def _render_item(item: ContextItem) -> str:
    state = item.state
    kind = {"counterexample": "Counterexample", "evidence": "Evidence"}.get(state.kind, state.kind)
    positive = (
        state.usable_premise
        and item.full_text
        and item.section not in {"failures", "history", "sources", "research_state"}
        and item.conclusion_relation != "REFUTES"
    )
    lines = [
        f"### {item.object_id}: {item.title}",
        f"Kind: {kind}",
        f"Authority: {state.authority} | Review: {state.review} | "
        f"Verification: {state.verification} | Research state: {state.research_state}",
        f"Positive premise permitted: {positive}",
        f"Dependencies: {', '.join(state.dependencies) or 'none recorded'}",
        f"Resolution: {', '.join(state.resolution_ids) or 'none recorded'}; "
        f"Replacement: {', '.join(state.replacement_ids) or 'none recorded'}",
        f"Provenance: {'; '.join(state.provenance) or 'local record'}",
        *state.relation_confirmations,
        f"Derivation IDs: {', '.join(state.derivation_ids) or 'ledger'}",
        *[f"WARNING: {warning}" for warning in state.warnings],
    ]
    if item.metadata_compact:
        lines = [line for line in lines if not line.startswith(("Provenance:", "Derivation IDs:"))]
        lines.append("Provenance abbreviated; full record and derivation IDs available by ID.")
    if item.source_path and not item.metadata_compact:
        lines.append(f"Full source: {item.source_path}")
    if item.conclusion_relation == "REFUTES":
        lines.append("Conclusion role: REFUTES; this proof does not support its target as true.")
    lines.extend(["", item.content])
    return "\n".join(lines) + "\n\n"


SECTION_HEADINGS = {
    "mandatory": "TARGET / REQUIRED DEPENDENCIES",
    "proofs": "REQUIRED PROOF / DEPENDENCIES",
    "canonical": "CURRENT ACCEPTED CONTEXT",
    "gaps": "OPEN GAPS",
    "failures": "FAILED ROUTES / DO NOT REPEAT",
    "history": "HISTORICAL / SUPERSEDED",
    "sources": "OPTIONAL ORIGINAL SOURCES",
    "provisional": "PROVISIONAL WORKING MATERIAL",
    "research_state": "CURRENT OPERATIONAL STATE",
    "counterexamples": "COUNTEREXAMPLES",
}


def _excerpt(content: str, length: int, query: str) -> str:
    """Head + first literal matched span + tail; never an inferred/LLM summary."""
    if len(content) <= length:
        return content
    if length < 12:
        return content[:length]
    part = length // 3
    terms = re.findall(r"[\w\u3400-\u9fff]{4,}", query.casefold())
    locations = [content.casefold().find(term) for term in terms if term in content.casefold()]
    center = min(locations, default=len(content) // 2)
    start = max(0, center - part // 2)
    return content[:part] + "\n[…]\n" + content[start : start + part] + "\n[…]\n" + content[-part:]


class ResearchContextBuilder:
    def __init__(self, ot_dir: Path):
        self.ot_dir = ot_dir

    def build(
        self,
        target: ResearchTarget,
        *,
        purpose: QueryPurpose = "CONTINUE_RESEARCH",
        token_budget: int = 8000,
        thread_id: str | None = None,
        include_provisional: bool = True,
        query: str = "",
        related_memory: RelatedResearch | None = None,
        explore: bool = False,
    ) -> ResearchContextBundle:
        if purpose not in {"CONTINUE_RESEARCH", "RECOVER_PROOF", "TRACE_HISTORY", "FIND_FAILURES"}:
            raise ResearchError("Unsupported query purpose.")
        if not 128 <= token_budget <= 200_000:
            raise ResearchError("Context token budget must be between 128 and 200000.")
        if thread_id is not None and (not thread_id.strip() or len(thread_id) > 128):
            raise ResearchError("Thread ID must contain 1–128 characters.")
        validate_research_target(self.ot_dir, target)
        pid = target.problem_id
        # No context cache: review/body/relation changes are reflected on every build.
        version = research_version(self.ot_dir, pid)
        states = KnowledgeStateResolver(self.ot_dir).resolve(pid)
        if not include_provisional and states[target.node_id].authority == "PROVISIONAL":
            raise ResearchError("Provisional target requires include_provisional=true.")
        manifest = build_research_manifest(self.ot_dir, target, related_memory=related_memory)
        candidates = list_candidates(self.ot_dir, pid)
        from math_research.memory.provisional import episode_local_mapping

        local_mappings = {
            eid: episode_local_mapping(self.ot_dir, pid, eid)
            for eid in {c.episode_id for c in candidates}
        }
        reviews = {r.candidate_id: r for r in list_reviews(self.ot_dir, pid)}
        selected: dict[str, ContextItem] = {}
        excluded: list[ContextExclusion] = []
        material_by_id = {m.artifact_id: m for m in manifest.materials}
        proof_roles = {
            p.id: p.conclusion_relation for p in store.list_proof_attempts(self.ot_dir, pid)
        }

        def add(material: ResearchMaterial, *, mandatory: bool | None = None) -> None:
            kind = material.kind.removeprefix("dossier:")
            source_kind = (
                kind in {"episode", "paper", "related_paper", "source"}
                or material.basis == "source"
                or material.basis in {"soft_relevance", "textual"}
                and not material.kind.startswith("dossier:")
            )
            obligation = material.artifact_id == target.node_id and target.kind == "obligation"
            state = ({} if source_kind else states).get(
                material.artifact_id,
                KnowledgeState(
                    object_id=material.artifact_id,
                    kind="obligation" if obligation else kind,
                    review="PROVISIONAL",
                    authority="PROVISIONAL" if obligation else "REJECTED/HISTORICAL",
                    research_state="OPEN" if obligation else "HISTORICAL",
                    provenance=material.provenance,
                ),
            )
            if not include_provisional and state.authority == "PROVISIONAL":
                excluded.append(
                    ContextExclusion(
                        object_id=material.artifact_id, reason="include_provisional policy"
                    )
                )
                return
            hard = (
                mandatory
                if mandatory is not None
                else (
                    material.tier == "mandatory"
                    and kind not in {"proof", "episode", "failed_attempt", "evidence"}
                )
            )
            section: Section = "mandatory" if hard else "canonical"
            if source_kind:
                section = "sources"
            elif state.kind in {"OPEN_GAP", "gap"}:
                section = "gaps" if state.research_state == "OPEN" else "history"
            elif kind == "failed_attempt" or state.kind == "failed_attempt":
                section = "failures"
            elif not state.usable_premise and state.kind not in {"CONJECTURE", "obligation"}:
                section = "history"
            elif kind == "proof" or state.kind == "proof":
                section = "proofs"
                hard = hard or purpose == "RECOVER_PROOF" and material.tier == "mandatory"
            elif kind == "counterexample" or state.kind == "counterexample":
                section = "counterexamples"
            priority = (
                100
                if hard
                else 40
                if material.tier == "mandatory"
                else 20
                if material.tier == "relevant"
                else 0
            )
            if thread_id and thread_id in state.thread_ids:
                priority += 10
            content, source_path, full_text = material.content, material.source_path, True
            if state.kind == "counterexample" and state.authority == "CANONICAL":
                from math_research.memory.records.counterexamples import (
                    get_counterexample,
                    read_counterexample,
                )

                counterexample = get_counterexample(self.ot_dir, pid, material.artifact_id)
                if counterexample:
                    content, ce_path = read_counterexample(self.ot_dir, counterexample)
                    source_path = str(ce_path)
                    relations = [
                        r.relation
                        for r in active_relations(self.ot_dir, pid)
                        if r.source_id == counterexample.id
                        and r.target_id == counterexample.target_id
                        and r.relation in {"REFUTES", "INVALIDATES"}
                    ]
                    content = (
                        f"Relation: {', '.join(relations) or 'not accepted'}\n"
                        "REFUTES: source attacks the statement itself.\n"
                        "INVALIDATES: target proof/route is invalidated; "
                        "underlying claim is not thereby refuted.\n\n" + content
                    )
            if (
                state.kind == "proof"
                and not source_kind
                and material.kind != "dossier:provisional"
                and (material.basis == "textual" or not material.source_path)
            ):
                from math_research.app.workflows.episodes import read_full_proof

                try:
                    content, path = read_full_proof(self.ot_dir, pid, material.artifact_id)
                    source_path = str(path)
                except ResearchError:
                    content = "Full proof unavailable; navigation record only."
                    full_text = False
            selected[material.artifact_id] = ContextItem(
                object_id=material.artifact_id,
                section=section,
                title=material.title,
                content=content,
                state=state,
                mandatory=hard,
                priority=priority,
                source_path=source_path,
                full_text=full_text,
                truncated=not full_text,
                conclusion_relation=proof_roles.get(material.artifact_id),
            )

        for material in manifest.materials:
            if material.kind == "dossier:provisional" and material.artifact_id != target.node_id:
                continue  # Existing proposal selection below owns non-target working bodies.
            if material.included or material.basis == "textual":
                add(material)
        # Keep accepted outputs attached to their original research target. Their
        # canonical bodies come from Problem Record; the Episode only supplies provenance.
        for candidate in candidates:
            canonical_id = states[candidate.candidate_id].canonical_id
            accepted_review = reviews.get(candidate.candidate_id)
            accepted_candidate = (
                accepted_review.reviewed_candidate
                if accepted_review and accepted_review.reviewed_candidate
                else candidate
            )
            if accepted_candidate.target_id != target.node_id or not canonical_id:
                continue
            accepted_material = material_by_id.get(canonical_id)
            if accepted_material:
                add(accepted_material)
            elif canonical_id.startswith("CLAIM-"):
                claim = store.get_claim(self.ot_dir, pid, canonical_id)
                if claim:
                    add(
                        ResearchMaterial(
                            key=f"claim:{canonical_id}",
                            artifact_id=canonical_id,
                            kind=claim.type,
                            tier="relevant",
                            basis="direct_record",
                            title=claim.statement[:100],
                            status=claim.status,
                            reason="Human-accepted output for this target",
                            content=claim.statement,
                            provenance=states[canonical_id].provenance,
                        )
                    )
        if purpose == "TRACE_HISTORY":
            navigation = self.node_navigation(target)
            selected["NODE-HISTORY"] = ContextItem(
                object_id="NODE-HISTORY",
                section="history",
                title="Node history navigation",
                content=navigation,
                state=KnowledgeState(
                    object_id="NODE-HISTORY",
                    kind="navigation",
                    authority="REJECTED/HISTORICAL",
                    research_state="HISTORICAL",
                ),
                priority=15,
            )
        # Transitive dependencies use the same Problem Record/Manifest, never a second graph.
        queue = [target.node_id]
        seen: set[str] = set()
        claims = {c.id: c for c in store.list_claims(self.ot_dir, pid)}
        while queue:
            oid = queue.pop()
            if oid in seen:
                continue
            seen.add(oid)
            current = states.get(oid)
            if current is None:
                continue
            for dep in current.dependencies:
                if dep in claims and dep not in material_by_id:
                    claim = claims[dep]
                    material_by_id[dep] = ResearchMaterial(
                        key=f"claim:{dep}",
                        artifact_id=dep,
                        kind=claim.type,
                        tier="mandatory",
                        basis="recorded_dependency",
                        title=claim.statement[:100],
                        status=claim.status,
                        reason="Transitive explicit dependency",
                        content=claim.statement,
                        provenance=claim.source_artifacts,
                    )
                if dep in material_by_id:
                    add(material_by_id[dep], mandatory=True)
                queue.append(dep)

        # Proposal search delegates to the same lexical/BM25 implementation.
        pending = [
            c
            for c in candidates
            if states[c.candidate_id].canonical_id is None
            and c.kind != "relation"
            and c.source_fields.get("origin") != "source_digest"
        ]
        docs = [
            IndexDoc(
                artifact_id=c.candidate_id,
                artifact_type="candidate",
                title=c.title,
                text=c.title + "\n" + c.body,
                problem_id=pid,
            )
            for c in pending
        ]
        text_query = (
            query or claims[target.node_id].statement
            if target.node_id in claims
            else query or target.node_id
        )
        scores = {
            d.artifact_id: score for d, score in search_documents(docs, text_query, k=len(docs))
        }
        candidate_by_id = {c.candidate_id: c for c in pending}
        for candidate in pending:
            if candidate.object_id == target.node_id:
                continue  # The same full target is already mandatory by its stable ID.
            state = states[candidate.candidate_id]
            mapped_target = local_mappings[candidate.episode_id].get(
                candidate.target_id or "", candidate.target_id
            )
            direct = mapped_target == target.node_id or target.node_id in state.dependencies
            if not include_provisional and state.authority == "PROVISIONAL":
                excluded.append(
                    ContextExclusion(
                        object_id=candidate.candidate_id, reason="include_provisional policy"
                    )
                )
                continue
            if (
                not direct
                and candidate.candidate_id not in scores
                and candidate.candidate_id not in seen
            ):
                excluded.append(
                    ContextExclusion(
                        object_id=candidate.candidate_id, reason="not relevant to this target"
                    )
                )
                continue
            section: Section = (
                "failures"
                if state.review == "REJECTED" or candidate.kind == "failed_attempt"
                else "provisional"
            )
            selected[candidate.candidate_id] = ContextItem(
                object_id=candidate.candidate_id,
                section=section,
                title=candidate.title,
                content=candidate.body,
                state=state,
                conclusion_relation="REFUTES" if candidate.kind == "refutation" else None,
                priority=35
                + scores.get(candidate.candidate_id, 0)
                + (10 if direct else 0)
                + (10 if thread_id and thread_id in state.thread_ids else 0),
            )
        # Explicit cross-thread working dependencies stay visible even with no lexical match.
        queue = [
            dep
            for item in selected.values()
            for dep in [
                *item.state.dependencies,
                *item.state.replacement_ids,
                *[
                    r
                    for r in item.state.resolution_ids
                    if states.get(r) and states[r].usable_premise
                ],
            ]
        ]
        seen_deps: set[str] = set()
        proof_by_id = {p.id: p for p in store.list_proof_attempts(self.ot_dir, pid)}
        while queue:
            dep = queue.pop()
            if dep in seen_deps:
                continue
            seen_deps.add(dep)
            if dep in states and states[dep].authority == "CANONICAL":
                dependency_material = material_by_id.get(dep)
                if dependency_material is None and dep in claims:
                    dependency_material = ResearchMaterial(
                        key=f"claim:{dep}",
                        artifact_id=dep,
                        kind=claims[dep].type,
                        tier="mandatory",
                        basis="recorded_dependency",
                        title=claims[dep].statement[:100],
                        status=claims[dep].status,
                        content=claims[dep].statement,
                        reason="Explicit dependency of selected research output",
                    )
                if dependency_material is None and dep in proof_by_id:
                    from math_research.app.workflows.episodes import read_full_proof

                    body, path = read_full_proof(self.ot_dir, pid, dep)
                    dependency_material = ResearchMaterial(
                        key=f"proof:{dep}",
                        artifact_id=dep,
                        kind="proof",
                        tier="mandatory",
                        basis="recorded_dependency",
                        title=proof_by_id[dep].title,
                        status=proof_by_id[dep].status,
                        content=body,
                        source_path=str(path),
                        reason="Explicit proof dependency of selected research output",
                    )
                if dependency_material:
                    add(dependency_material, mandatory=True)
                queue.extend([*states[dep].dependencies, *states[dep].replacement_ids])
            if dep in candidate_by_id and include_provisional:
                candidate = candidate_by_id[dep]
                state = states[dep]
                selected[dep] = ContextItem(
                    object_id=dep,
                    section="failures" if state.review == "REJECTED" else "provisional",
                    title=candidate.title,
                    content=candidate.body,
                    state=state,
                    mandatory=True,
                    priority=110,
                )
                queue.extend(state.dependencies)

        for candidate in candidates:
            if candidate.object_id in selected:
                selected.pop(candidate.candidate_id, None)

        if explore:
            from math_research.memory.handoff import current_research_state, resolved_work_ids

            projection = current_research_state(
                self.ot_dir, target, include_provisional=include_provisional, states=states
            )
            selected["CURRENT-RESEARCH-STATE"] = ContextItem(
                object_id="CURRENT-RESEARCH-STATE",
                section="research_state",
                title="Latest Research Handoff and current operational state (HOT)",
                content=projection.markdown,
                state=KnowledgeState(
                    object_id="CURRENT-RESEARCH-STATE",
                    kind="navigation",
                    authority="PROVISIONAL",
                    review="PROVISIONAL",
                    research_state="HISTORICAL",
                    provenance=projection.cold_episode_ids,
                    warnings=[
                        "Operational projection is not a mathematical premise or Human Accept."
                    ],
                ),
                mandatory=True,
                priority=250,
                full_text=False,
            )
            closed = resolved_work_ids(states)
            resolved_proofs = {
                oid
                for ident, state in states.items()
                if ident in closed
                for oid in state.resolution_ids
            }
            dates = {e.episode_id: e.imported_at for e in list_episodes(self.ot_dir, pid)}
            candidate_episodes = {c.candidate_id: c.episode_id for c in candidates}
            relevant_episodes = {
                candidate_episodes[oid] for oid in selected if oid in candidate_episodes
            } | set(projection.cold_episode_ids)
            newest = set(
                sorted(relevant_episodes, key=lambda ident: (dates[ident], ident), reverse=True)[:3]
            )
            for item in selected.values():
                if item.object_id == target.node_id:
                    item.priority = 300
                    continue
                if item.object_id == "CURRENT-RESEARCH-STATE":
                    continue
                if item.object_id in resolved_proofs or item.object_id in closed:
                    item.content = (
                        "WARM resolved subcase summary: "
                        + item.title[:400]
                        + ". Resolution IDs: "
                        + (", ".join(item.state.resolution_ids) or item.object_id)
                        + ". "
                        "Do not redo unless its mechanism is explicitly needed. "
                        "Read the full original by ID before relying on its argument."
                    )
                    item.full_text = False
                    item.priority = min(item.priority, 15)
                elif item.section in {"failures", "history"} or item.state.research_state in {
                    "REVISED",
                    "SUPERSEDED",
                    "INVALIDATED",
                    "REFUTED",
                }:
                    item.content = (
                        "WARM failure/history summary (do not repeat without reassessment):\n"
                        + item.content[:900]
                    )
                    item.full_text = False
                    item.priority = min(item.priority, 10)
                elif item.section == "sources":
                    item.content = (
                        "COLD original source remains retrievable by Episode ID; "
                        "latest planning is in CURRENT-RESEARCH-STATE.\n" + item.title[:300]
                    )
                    item.full_text = False
                    item.priority = 5
                elif item.section == "provisional":
                    if candidate_episodes.get(item.object_id) in newest:
                        item.priority += 30
                    else:
                        item.content = (
                            "WARM provisional summary (not theorem truth):\n" + item.content[:1400]
                        )
                        item.full_text = False
                elif item.section == "proofs" and len(item.content) > 6000:
                    item.content = (
                        "WARM active proof excerpt; retrieve the original by ID "
                        "before relying on omitted steps.\n" + item.content[:6000]
                    )
                    item.full_text = False

        # Promote actual canonical direct proof material, never a colliding raw checker source.
        direct_proofs = {p.id for p in proof_by_id.values() if target.node_id in p.claim_links}
        direct_proofs.update(
            r.source_id
            for r in active_relations(self.ot_dir, pid)
            if r.relation == "PROVES" and r.target_id == target.node_id
        )
        if purpose in {"CONTINUE_RESEARCH", "RECOVER_PROOF"}:
            for ident in direct_proofs:
                proof_item = selected.get(ident)
                if (
                    proof_item
                    and proof_item.state.authority == "CANONICAL"
                    and proof_item.state.research_state not in STALE_STATES
                ):
                    proof_item.mandatory = True
                    proof_item.priority = max(proof_item.priority, 100)
        required_dependencies = {
            dep
            for item in selected.values()
            if item.mandatory
            and (item.state.research_state not in STALE_STATES or item.object_id == target.node_id)
            for dep in item.state.dependencies
        }
        intent = detect_intent(query)
        include_history = (
            purpose in {"TRACE_HISTORY", "FIND_FAILURES"}
            or intent.temporal_intent == "HISTORICAL"
            or intent.research_state_intent == "FAILED"
        )
        explicit_context_ids = (
            {target.node_id}
            | {ident for ident, item in selected.items() if item.mandatory}
            | {
                ident
                for ident, material in material_by_id.items()
                if material.included
                and material.basis not in {"textual", "soft_relevance", "source"}
            }
        )
        # Resolver-supplied predecessor IDs remain relevant to failure provenance;
        # this is navigation through recorded replacement, never a new truth rule.
        initial_context_ids = frozenset(explicit_context_ids)
        explicit_context_ids.update(
            ident
            for ident, state in states.items()
            if state.authority == "CANONICAL"
            and initial_context_ids.intersection(state.replacement_ids)
        )
        explicit_context_ids.update(
            proof.id
            for proof in proof_by_id.values()
            if explicit_context_ids.intersection(
                [*proof.claim_links, *states[proof.id].dependencies]
            )
        )
        attached_failures = {
            failed.id
            for failed in store.list_failed_attempts(self.ot_dir, pid)
            if explicit_context_ids.intersection(failed.artifacts)
        }
        if purpose == "FIND_FAILURES":
            for failed in store.list_failed_attempts(self.ot_dir, pid):
                if failed.id in attached_failures and failed.id not in selected:
                    add(
                        ResearchMaterial(
                            key=f"failed:{failed.id}",
                            artifact_id=failed.id,
                            kind="failed_attempt",
                            tier="relevant",
                            basis="direct_record",
                            title=failed.attempted_method,
                            status="failed_route",
                            content=f"{failed.summary}\n{failed.reason_failed}",
                            reason="Explicit failed-route attachment to current/history context",
                            provenance=failed.artifacts,
                        )
                    )
        for ident, item in list(selected.items()):
            matched_material = material_by_id.get(ident)
            if (
                purpose == "FIND_FAILURES"
                and not item.mandatory
                and item.section in {"canonical", "failures"}
                and matched_material
                and matched_material.basis == "textual"
                and ident not in attached_failures
            ):
                del selected[ident]
                excluded.append(
                    ContextExclusion(
                        object_id=ident,
                        reason="lexical overlap alone does not establish failed-route provenance",
                    )
                )
                continue
            if (
                item.state.research_state in STALE_STATES
                and ident != target.node_id
                and ident not in required_dependencies
                and item.section != "sources"
            ):
                if (
                    purpose == "CONTINUE_RESEARCH"
                    and not include_history
                    and item.state.authority == "CANONICAL"
                    and item.state.research_state in {"SUPERSEDED", "REVISED", "HISTORICAL"}
                    and item.section not in {"failures", "counterexamples"}
                ):
                    del selected[ident]
                    excluded.append(
                        ContextExclusion(
                            object_id=ident,
                            reason="historical material not required for current continuation",
                        )
                    )
                    continue
                item.mandatory = False
            item.tier = (
                "MUST"
                if item.mandatory
                else "MAY"
                if item.section in {"history", "sources"}
                or matched_material
                and matched_material.basis == "textual"
                else "SHOULD"
            )
            if purpose == "FIND_FAILURES" and item.section == "failures":
                item.priority += 80

        target_state = states.get(target.node_id)
        dossier = store.require_dossier(self.ot_dir, pid)
        header = (
            f"# Research Context: {pid} / {target.node_id}\n"
            f"Problem: {dossier.title}\nPurpose: {purpose}\n"
            f"Thread: {thread_id or 'problem scope'}\n"
            f"Current research state: {target_state.research_state if target_state else 'OPEN'}\n"
            f"Source version: {version}\n\n{AUTHORITY_PROTOCOL}\n\n"
        )
        if estimate_tokens(header) > token_budget:
            raise ResearchError("Token budget cannot fit the authority/header protocol.")
        sections: dict[str, list[str]] = {}
        included: list[ContextItem] = []
        warnings = list(manifest.warnings)
        used = estimate_tokens(header)
        tokens_per_section = {"header": used}
        weights = {
            "canonical": 0.20,
            "proofs": 0.20,
            "provisional": 0.25,
            "failures": 0.10,
            "history": 0.10,
            "gaps": 0.10,
            "sources": 0.05,
        }
        if explore:
            weights.update(proofs=0.10, gaps=0.15, history=0.05, research_state=0.20)
        if purpose == "RECOVER_PROOF":
            weights.update(proofs=0.50, provisional=0.10, canonical=0.10, history=0.05)
        elif purpose == "TRACE_HISTORY":
            weights.update(
                history=0.35,
                sources=0.15,
                proofs=0.10,
                provisional=0.10,
                canonical=0.10,
                gaps=0.05,
                failures=0.15,
            )
        elif purpose == "FIND_FAILURES":
            weights.update(
                failures=0.45,
                history=0.20,
                proofs=0.05,
                provisional=0.10,
                canonical=0.10,
                gaps=0.05,
                sources=0.05,
            )
        if any(item.section == "counterexamples" for item in selected.values()):
            weights["counterexamples"] = 0.10
        allocations = {
            key: int((token_budget - used) * value / sum(weights.values()))
            for key, value in weights.items()
        }

        def include(item: ContextItem, cap: int, *, allow_navigation: bool = False) -> bool:
            nonlocal used
            text = _render_item(item)
            section = item.section
            heading = f"## {SECTION_HEADINGS[section]}\n\n" if section not in sections else ""
            cost = estimate_tokens(heading + text)
            if cost > cap:
                compact = item.model_copy(update={"metadata_compact": True})
                text = _render_item(compact)
                cost = estimate_tokens(heading + text)
                if cost > cap:
                    if item.mandatory:
                        banner = (
                            "TRUNCATED required mathematical text. Read the full original "
                            "by ID before relying on omitted steps.\n"
                        )
                        compact = compact.model_copy(
                            update={"content": banner, "full_text": False, "truncated": True}
                        )
                        if estimate_tokens(heading + _render_item(compact)) > cap:
                            return False
                        low, high = 0, len(item.content)
                        while low < high:
                            middle = (low + high + 1) // 2
                            compact.content = banner + _excerpt(item.content, middle, query)
                            if estimate_tokens(heading + _render_item(compact)) <= cap:
                                low = middle
                            else:
                                high = middle - 1
                        compact.content = banner + _excerpt(item.content, low, query)
                    elif item.section in {"proofs", "sources"} and allow_navigation:
                        compact = compact.model_copy(
                            update={
                                "content": (
                                    "Full mathematical text omitted for budget. Retrieve the "
                                    "original by ID before relying on its argument."
                                ),
                                "full_text": False,
                                "truncated": True,
                            }
                        )
                    else:
                        return False
                    text = _render_item(compact)
                    cost = estimate_tokens(heading + text)
                    if cost > cap:
                        return False
                item = compact
                if item.truncated:
                    excluded.append(
                        ContextExclusion(
                            object_id=item.object_id,
                            reason="mandatory full mathematical text truncated for budget"
                            if item.mandatory
                            else "full mathematical text exceeds section/bundle budget",
                        )
                    )
            sections.setdefault(section, []).append(heading + text)
            included.append(item)
            used += cost
            tokens_per_section[section] = tokens_per_section.get(section, 0) + cost
            return True

        ordered = sorted(
            selected.values(),
            key=lambda i: ({"MUST": 0, "SHOULD": 1, "MAY": 2}[i.tier], -i.priority, i.object_id),
        )
        omitted_mandatory: list[str] = []
        remainder: list[ContextItem] = []
        required = [item for item in ordered if item.mandatory]
        for index, item in enumerate(ordered):
            if item.mandatory:
                # Reserve compact existence/authority for every remaining MUST record.
                reserve = sum(
                    estimate_tokens(
                        _render_item(
                            other.model_copy(
                                update={
                                    "content": (
                                        "TRUNCATED required mathematical text. Read the full "
                                        "original by ID before relying on omitted steps.\n"
                                    ),
                                    "metadata_compact": True,
                                    "full_text": False,
                                    "truncated": True,
                                }
                            )
                        )
                    )
                    + 20
                    for other in required[index + 1 :]
                )
                if not include(item, max(0, token_budget - used - reserve)):
                    omitted_mandatory.append(item.object_id)
                    excluded.append(
                        ContextExclusion(
                            object_id=item.object_id,
                            reason="mandatory context cannot fit token budget",
                        )
                    )
            else:
                remainder.append(item)
        # Reallocate after mandatory information, preserving category reservations.
        allocations = {
            key: int((token_budget - used) * value / sum(weights.values()))
            for key, value in weights.items()
        }
        mandatory_spent = dict(tokens_per_section)
        for tier in ("SHOULD", "MAY"):
            overflow: list[ContextItem] = []
            for item in (candidate for candidate in remainder if candidate.tier == tier):
                capacity = min(
                    token_budget - used,
                    allocations.get(item.section, 0)
                    - tokens_per_section.get(item.section, 0)
                    + mandatory_spent.get(item.section, 0),
                )
                if not include(item, max(0, capacity)):
                    overflow.append(item)
            # Reuse category budgets within each tier before spending on the next tier.
            for item in overflow:
                if not include(item, token_budget - used, allow_navigation=True):
                    excluded.append(
                        ContextExclusion(object_id=item.object_id, reason="token budget")
                    )
        if omitted_mandatory:
            warnings.append("Incomplete mandatory context: " + ", ".join(omitted_mandatory))
        warnings.extend(w for item in included for w in item.state.warnings)
        if research_version(self.ot_dir, pid) != version:
            raise ResearchError(
                "Research state changed while building context; retry for a coherent view."
            )
        markdown = header + "".join("".join(value) for value in sections.values())
        related_ids = set(selected)
        unresolved = [
            oid
            for oid, state in states.items()
            if oid in related_ids and state.kind == "OPEN_GAP" and state.research_state == "OPEN"
        ]
        resolved = [
            oid
            for oid, state in states.items()
            if oid in related_ids
            and state.kind == "OPEN_GAP"
            and state.research_state == "RESOLVED"
        ]
        return ResearchContextBundle(
            target=target,
            purpose=purpose,
            thread_id=thread_id,
            source_version=version,
            header=header,
            markdown=markdown,
            items=included,
            excluded=excluded,
            unresolved_gaps=unresolved,
            resolved_historical_gaps=resolved,
            warnings=list(dict.fromkeys(warnings)),
            token_budget=token_budget,
            token_estimate=estimate_tokens(markdown),
            tokens_per_section=tokens_per_section,
            section_allocations=allocations,
            complete=not omitted_mandatory
            and not any(i.mandatory and i.truncated for i in included),
            required_context_truncated=bool(omitted_mandatory)
            or any(i.mandatory and i.truncated for i in included),
            required_record_ids=[item.object_id for item in required],
            required_omitted_ids=omitted_mandatory,
        )

    def node_navigation(self, target: ResearchTarget) -> str:
        """Read the full selected record history using the current material selection."""
        from math_research.retrieval.selection import render_manifest

        return render_manifest(build_research_manifest(self.ot_dir, target))
