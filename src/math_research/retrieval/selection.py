"""Internal material selection for Recall and Context; records remain authoritative."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from math_research.core.errors import ResearchError
from math_research.ledger.archive import source_path
from math_research.ledger.episodes import (
    ResearchEpisode,
    ReviewDecision,
    list_episodes,
    list_reviews,
)
from math_research.ledger.records import store
from math_research.ledger.records.evidence_content import render_evidence
from math_research.ledger.records.models import (
    Approach,
    ClaimRecord,
    CounterexampleRecord,
    EvidenceRecord,
    FailedAttempt,
    ProofAttempt,
)
from math_research.ledger.relations.ledger import active_relations
from math_research.ledger.relations.models import ConfirmedRelation
from math_research.ledger.relations.policy import LOGICAL_RELATIONS
from math_research.ledger.source_records import get_paper
from math_research.ledger.target import ResearchTarget, validate_research_target
from math_research.retrieval.index import (
    gather_documents,
    scoped_memory_documents,
    search_documents,
)
from math_research.retrieval.related_research import RelatedResearch

Tier = Literal["mandatory", "relevant", "optional"]
Basis = Literal[
    "target",
    "recorded_dependency",
    "direct_record",
    "source",
    "human_relation",
    "model_relation",
    "textual",
    "soft_relevance",
]
_ORDER = {"mandatory": 0, "relevant": 1, "optional": 2}
_CJK = re.compile(r"[\u3400-\u9fff]")


class ResearchMaterial(BaseModel):
    key: str
    artifact_id: str
    kind: str
    tier: Tier
    basis: Basis
    title: str
    status: str
    reason: str
    content: str = ""
    source_path: str | None = None
    provenance: list[str] = Field(default_factory=list)
    included: bool = True


class ResearchManifest(BaseModel):
    problem_id: str
    target: ResearchTarget
    language: Literal["zh", "en"]
    created_at: datetime
    materials: list[ResearchMaterial]
    warnings: list[str] = Field(default_factory=list)


class ClaimDetail(BaseModel):
    claim: ClaimRecord
    mathematical_status: str
    assumptions: list[str]
    dependencies: list[ClaimRecord]
    proofs: list[ProofAttempt]
    failed_attempts: list[FailedAttempt]
    counterexamples: list[CounterexampleRecord | ClaimRecord]
    gaps: list[ClaimRecord]
    special_cases: list[ClaimRecord]
    revisions: list[str]
    branches: list[Approach]
    source_episodes: list[ResearchEpisode]
    confirmed_relations: list[ConfirmedRelation] = Field(default_factory=list)
    human_confirmed_relations: list[ReviewDecision]
    provenance: list[str]
    evidence: list[EvidenceRecord] = Field(default_factory=list)


def build_claim_detail(ot_dir: Path, problem_id: str, claim_id: str) -> ClaimDetail:
    """A traceable view; human relation review is separate from mathematical status."""
    store.require_dossier(ot_dir, problem_id)
    claim = store.get_claim(ot_dir, problem_id, claim_id)
    if claim is None:
        raise ResearchError(f"No Claim {claim_id} in {problem_id}.")
    all_claims = store.list_claims(ot_dir, problem_id)
    proofs = [
        proof
        for proof in store.list_proof_attempts(ot_dir, problem_id)
        if claim_id in proof.claim_links
    ]
    proof_ids = {proof.id for proof in proofs}
    reviews = list_reviews(ot_dir, problem_id)
    failure_targets = {
        review.mapped_id: review.reviewed_candidate.target_id
        for review in reviews
        if review.decision == "accept"
        and review.mapped_id
        and review.reviewed_candidate
        and review.reviewed_candidate.kind != "relation"
    }
    failed = [
        item
        for item in store.list_failed_attempts(ot_dir, problem_id)
        if claim_id in [*item.artifacts, *item.tags]
        or proof_ids.intersection(item.artifacts)
        or failure_targets.get(item.id) in proof_ids | {claim_id}
    ]
    children = [item for item in all_claims if claim_id in item.depends_on]
    reviewed_children = {
        review.mapped_id
        for review in reviews
        if review.decision == "accept"
        and review.reviewed_candidate
        and review.reviewed_candidate.kind in {"gap", "counterexample"}
        and review.reviewed_candidate.target_id == claim_id
        and review.mapped_id
        and review.mapped_id != claim_id
    }
    children.extend(
        item for item in all_claims if item.id in reviewed_children and item not in children
    )
    reviewed_specials = {
        review.source_id
        for review in active_relations(ot_dir, problem_id)
        if review.relation == "SPECIAL_CASE_OF" and review.target_id == claim_id
    }
    specials = [
        item
        for item in all_claims
        if f"source_reported_special_case_of:{claim_id}" in item.notes
        or item.id in reviewed_specials
    ]
    connected = [
        item
        for item in reviews
        if item.decision == "accept"
        and item.relation in LOGICAL_RELATIONS
        and claim_id in {item.source_id, item.target_id}
    ]
    branches = [
        item
        for item in store.list_approaches(ot_dir, problem_id)
        if claim_id in item.resulting_artifacts
        or claim_id in item.notes
        or failure_targets.get(item.id) == claim_id
    ]
    counterexamples = [
        item
        for item in store.list_counterexamples(ot_dir, problem_id)
        if item.target_id in {claim_id, *proof_ids, *(b.id for b in branches)}
    ]
    connected.extend(
        r
        for r in reviews
        if r.decision == "accept"
        and r.relation == "INVALIDATES"
        and r.target_id in proof_ids | {b.id for b in branches}
        and r not in connected
    )
    relevant_artifacts = {
        claim_id,
        *proof_ids,
        *(item.id for item in failed),
        *(item.id for item in children),
        *(item.id for item in specials),
        *(item.id for item in branches),
        *(item.id for item in counterexamples),
    }
    episodes = _record_episodes(
        ot_dir, problem_id, relevant_artifacts | set(claim.source_artifacts)
    )
    revisions = [
        f"{review.mapped_id} REVISES {review.reviewed_candidate.revises_proof_id}"
        for review in reviews
        if review.decision == "accept"
        and review.mapped_id in proof_ids
        and review.reviewed_candidate
        and review.reviewed_candidate.revises_proof_id
    ]
    verified = claim.status in {"verified", "formally_verified"}
    return ClaimDetail(
        claim=claim,
        mathematical_status="verified_by_ledger" if verified else "not_verified_by_ledger",
        assumptions=[item.statement for item in store.list_assumptions(ot_dir, problem_id)],
        dependencies=[item for item in all_claims if item.id in claim.depends_on],
        proofs=proofs,
        evidence=[
            item for item in store.list_evidence(ot_dir, problem_id) if item.claim_id == claim_id
        ],
        failed_attempts=failed,
        counterexamples=[
            *counterexamples,
            *(item for item in children if item.type.startswith("COUNTEREXAMPLE_")),
        ],
        gaps=[item for item in children if item.type == "OPEN_GAP"],
        special_cases=specials,
        revisions=revisions,
        branches=branches,
        source_episodes=[
            item for item in list_episodes(ot_dir, problem_id) if item.episode_id in episodes
        ],
        human_confirmed_relations=connected,
        confirmed_relations=[
            r
            for r in active_relations(ot_dir, problem_id)
            if r.source_id in relevant_artifacts or r.target_id in relevant_artifacts
        ],
        provenance=[*claim.source_artifacts, claim.notes],
    )


def _proof_path(ot_dir: Path, problem_id: str, proof: ProofAttempt) -> Path | None:
    if not proof.body_path:
        return None
    base = store.dossier_dir(ot_dir, problem_id).resolve()
    path = (base / proof.body_path).resolve()
    return path if path.is_relative_to(base) and path.is_file() else None


def _language(text: str) -> Literal["zh", "en"]:
    return "zh" if len(_CJK.findall(text)) >= 2 else "en"


def _record_episodes(ot_dir: Path, problem_id: str, artifact_ids: set[str]) -> set[str]:
    found = {artifact for artifact in artifact_ids if artifact.startswith("EPISODE-")}
    for item in store.list_counterexamples(ot_dir, problem_id):
        if item.id in artifact_ids:
            found.update(s for s in item.source_artifacts if s.startswith("EPISODE-"))
    for review in list_reviews(ot_dir, problem_id):
        if review.decision == "accept" and review.mapped_id in artifact_ids:
            found.add(review.episode_id)
    advisory = {
        e.episode_id
        for e in list_episodes(ot_dir, problem_id)
        if (e.provenance or "").startswith("SOURCE_DIGEST:")
    }
    return found - advisory


def build_research_manifest(
    ot_dir: Path,
    target: ResearchTarget,
    *,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
    related_memory: RelatedResearch | None = None,
) -> ResearchManifest:
    """Select by explicit dossier relations first, then optional scoped text hits.

    ``include``/``exclude`` contain material keys (e.g. ``proof:PROOF-0001``).
    No fixed file-count limit is imposed. A mandatory exclusion is allowed but
    clearly warned about; the researcher, not the algorithm, owns the handoff.
    """
    node = validate_research_target(ot_dir, target)
    pid = target.problem_id
    scoped_docs = gather_documents(ot_dir, problem_id=pid)
    statement = node.statement
    language = _language(statement)
    materials: dict[str, ResearchMaterial] = {}
    episodes_by_id = {e.episode_id: e for e in list_episodes(ot_dir, pid)}

    def add(material: ResearchMaterial) -> None:
        # Even an optional textual Episode hit retains its raw-source provenance.
        # Membership/selection still comes from the existing scoped pipeline.
        episode = episodes_by_id.get(material.artifact_id)
        if episode is not None and material.kind.removeprefix("dossier:") == "episode":
            material.source_path = str(source_path(ot_dir, episode.archive_path))
            material.provenance = list(
                dict.fromkeys(
                    [
                        *material.provenance,
                        episode.archive_path,
                        episode.content_sha256,
                        *([episode.provenance] if episode.provenance else []),
                    ]
                )
            )
        prior = materials.get(material.key)
        if prior is None or _ORDER[material.tier] < _ORDER[prior.tier]:
            materials[material.key] = material

    claim_by_id = {claim.id: claim for claim in store.list_claims(ot_dir, pid)}
    proofs = store.list_proof_attempts(ot_dir, pid)
    failures = store.list_failed_attempts(ot_dir, pid)
    reviews = list_reviews(ot_dir, pid)
    review_by_object = {
        review.mapped_id: review
        for review in reviews
        if review.decision == "accept"
        and review.mapped_id
        and review.reviewed_candidate
        and review.reviewed_candidate.kind != "relation"
    }
    target_claim_ids = {target.node_id}

    def claim_material(
        claim: ClaimRecord, tier: Tier, basis: Basis, reason: str
    ) -> ResearchMaterial:
        return ResearchMaterial(
            key=f"claim:{claim.id}",
            artifact_id=claim.id,
            kind=claim.type,
            tier=tier,
            basis=basis,
            title=claim.statement[:100],
            status=claim.status,
            reason=reason,
            content=claim.statement,
            provenance=[*claim.source_artifacts, *([claim.notes] if claim.notes else [])],
        )

    add(claim_material(node, "mandatory", "target", "当前数学目标 / selected target"))

    for assumption in store.list_assumptions(ot_dir, pid):
        add(
            ResearchMaterial(
                key=f"assumption:{assumption.id}",
                artifact_id=assumption.id,
                kind="assumption",
                tier="mandatory",
                basis="direct_record",
                title=assumption.statement[:100],
                status="recorded",
                reason="Problem Record 级显式假设；须核对是否适用于当前目标",
                content=assumption.statement,
                provenance=[assumption.rationale],
            )
        )

    for dependency_id in node.depends_on:
        dependency = claim_by_id.get(dependency_id)
        if dependency:
            add(
                claim_material(
                    dependency,
                    "mandatory",
                    "recorded_dependency",
                    "Problem Record 显式 depends_on；若是候选命题，仍须核查其真值",
                )
            )

    direct_proofs = [proof for proof in proofs if target_claim_ids.intersection(proof.claim_links)]
    proof_ids = {proof.id for proof in direct_proofs}
    review_targets = {
        mapped_id: review.reviewed_candidate.target_id
        for mapped_id, review in review_by_object.items()
        if review.reviewed_candidate is not None
    }
    related_failures = [
        failure
        for failure in failures
        if target.node_id in [*failure.artifacts, *failure.tags]
        or proof_ids.intersection(failure.artifacts)
        or review_targets.get(failure.id) in proof_ids | target_claim_ids
    ]
    invalidated = {
        proof_id
        for failure in related_failures
        for proof_id in proof_ids
        if proof_id in failure.artifacts
    }
    for proof in direct_proofs:
        path = _proof_path(ot_dir, pid, proof)
        stale = proof.id in invalidated or proof.status in {"blocked", "abandoned"}
        reason = (
            "已发现漏洞/失效路线，必须阅读以免重复使用"
            if stale
            else "直接关联的完整候选证明；不得当作系统已验证结论"
        )
        add(
            ResearchMaterial(
                key=f"proof:{proof.id}",
                artifact_id=proof.id,
                kind="proof",
                tier="mandatory",
                basis="direct_record",
                title=proof.title,
                status="invalidated_candidate" if stale else proof.status,
                reason=reason,
                content=path.read_text(encoding="utf-8") if path else "",
                source_path=str(path) if path else None,
                provenance=[proof.body_path or "", *proof.claim_links],
            )
        )

    from math_research.ledger.records.counterexamples import read_counterexample

    direct_approach_ids = {
        a.id
        for a in store.list_approaches(ot_dir, pid)
        if target_claim_ids.intersection(a.resulting_artifacts)
        or review_targets.get(a.id) in target_claim_ids
    }
    mathematical_targets = target_claim_ids | proof_ids | direct_approach_ids
    for counterexample in store.list_counterexamples(ot_dir, pid):
        if counterexample.target_id not in mathematical_targets:
            continue
        body, path = read_counterexample(ot_dir, counterexample)
        relations = [
            r.relation
            for r in active_relations(ot_dir, pid)
            if r.source_id == counterexample.id
            and r.target_id == counterexample.target_id
            and r.relation in {"REFUTES", "INVALIDATES"}
        ]
        relation = ", ".join(relations) or "not accepted (object acceptance is independent)"
        meaning = (
            "INVALIDATES: target proof/route is invalidated; "
            "underlying claim is not thereby refuted."
            if "INVALIDATES" in relations
            else "REFUTES: source attacks the statement itself."
            if "REFUTES" in relations
            else "No accepted mathematical attack relation."
        )
        add(
            ResearchMaterial(
                key=f"counterexample:{counterexample.id}",
                artifact_id=counterexample.id,
                kind="counterexample",
                tier="mandatory",
                basis="direct_record",
                title=counterexample.title or counterexample.id,
                status=counterexample.status,
                reason="精确 target 的完整反例；关系单独审核",
                content=f"Relation: {relation}\n{meaning}\n\n{body}",
                source_path=str(path),
                provenance=[*counterexample.source_artifacts, counterexample.body_path],
            )
        )

    for claim in claim_by_id.values():
        review = review_by_object.get(claim.id)
        reviewed_target = (
            review.reviewed_candidate.target_id if review and review.reviewed_candidate else None
        )
        direct = (
            bool(target_claim_ids.intersection(claim.depends_on))
            or reviewed_target in target_claim_ids
        )
        if claim.id == target.node_id:
            continue
        if claim.type == "OPEN_GAP" and direct:
            add(claim_material(claim, "mandatory", "direct_record", "当前目标的开放缺口"))
        elif claim.type.startswith("COUNTEREXAMPLE_") and direct:
            add(claim_material(claim, "mandatory", "direct_record", "当前目标的反例或候选反例"))
        elif f"source_reported_special_case_of:{target.node_id}" in claim.notes:
            add(
                claim_material(
                    claim,
                    "relevant",
                    "source",
                    "论文报告的局部情形；不证明一般目标",
                )
            )

    for edge in active_relations(ot_dir, pid):
        if edge.relation in {"DEPENDS_ON", "USES"} and edge.source_id in target_claim_ids:
            prerequisite = claim_by_id.get(edge.target_id)
            if prerequisite:
                add(
                    claim_material(
                        prerequisite,
                        "mandatory",
                        "human_relation" if edge.confirmed_by == "human" else "model_relation",
                        f"{edge.label} {edge.relation} 关系；前提命题本身仍需独立核查",
                    )
                )
        elif edge.relation in {"SPECIAL_CASE_OF", "GENERALIZES"}:
            neighbor_id = (
                edge.source_id
                if edge.target_id in target_claim_ids
                else edge.target_id
                if edge.source_id in target_claim_ids
                else None
            )
            neighbor = claim_by_id.get(neighbor_id or "")
            if neighbor:
                add(
                    claim_material(
                        neighbor,
                        "relevant",
                        "human_relation" if edge.confirmed_by == "human" else "model_relation",
                        f"{edge.label} {edge.relation} 关系；非数学验证",
                    )
                )

    # Accepted hard neighbors that are not expressible through Claim.depends_on
    # still participate in handoff. Never infer these edges from soft scores.
    documents = scoped_memory_documents(ot_dir, pid, documents=scoped_docs)
    by_object = {doc.artifact_id: doc for doc in documents.values()}
    for edge in active_relations(ot_dir, pid):
        neighbor_id = (
            edge.source_id
            if edge.target_id in mathematical_targets
            else edge.target_id
            if edge.source_id in target_claim_ids
            else None
        )
        hard_doc = by_object.get(neighbor_id or "")
        if hard_doc is None:
            continue
        hard_proof = next((p for p in proofs if p.id == neighbor_id), None)
        path = _proof_path(ot_dir, pid, hard_proof) if hard_proof else None
        mandatory = edge.relation in {"PROVES", "REFUTES", "INVALIDATES", "REVISES", "SUPERSEDES"}
        add(
            ResearchMaterial(
                key=_search_key(hard_doc.artifact_type, hard_doc.artifact_id),
                artifact_id=hard_doc.artifact_id,
                kind=hard_doc.artifact_type,
                tier="mandatory" if mandatory else "relevant",
                basis="human_relation" if edge.confirmed_by == "human" else "model_relation",
                title=hard_doc.title,
                status=f"{edge.confirmed_by}_confirmed_relation; not_verified",
                reason=f"{edge.label} 直接 {edge.relation} 材料；不构成数学验证证书",
                content=path.read_text(encoding="utf-8") if path else hard_doc.text,
                source_path=str(path) if path else None,
                provenance=[edge.episode_id, edge.decision_id, edge.label],
            )
        )

    partial_claim_ids = {
        item.artifact_id
        for item in materials.values()
        if item.kind == "THEOREM" and item.tier == "relevant"
    }
    for proof in proofs:
        if not partial_claim_ids.intersection(proof.claim_links):
            continue
        path = _proof_path(ot_dir, pid, proof)
        manuscript_special = any(
            claim_by_id[claim_id].notes.startswith("bootstrap:theorem:")
            for claim_id in proof.claim_links
            if claim_id in partial_claim_ids
        )
        add(
            ResearchMaterial(
                key=f"proof:{proof.id}",
                artifact_id=proof.id,
                kind="proof",
                tier="relevant",
                basis="source" if manuscript_special else "human_relation",
                title=proof.title,
                status="source_reported_candidate" if manuscript_special else proof.status,
                reason="局部结果的完整论文证明；不能当作一般目标的证明",
                content=path.read_text(encoding="utf-8") if path else "",
                source_path=str(path) if path else None,
                provenance=[proof.body_path or "", *proof.claim_links],
            )
        )

    for evidence in store.list_evidence(ot_dir, pid):
        if evidence.claim_id not in target_claim_ids:
            continue
        add(
            ResearchMaterial(
                key=f"evidence:{evidence.id}",
                artifact_id=evidence.id,
                kind="evidence",
                tier="mandatory" if evidence.direction == "contradicts" else "relevant",
                basis="direct_record",
                title=evidence.summary[:100],
                status=f"{evidence.direction}; source-reported/candidate",
                reason="直接关联的 Problem Record Evidence；不是数学验证证书",
                content=render_evidence(evidence),
                source_path=evidence.path,
                provenance=evidence.source_artifacts,
            )
        )

    for failure in related_failures:
        add(
            ResearchMaterial(
                key=f"failed:{failure.id}",
                artifact_id=failure.id,
                kind="failed_attempt",
                tier="mandatory",
                basis="direct_record",
                title=failure.attempted_method,
                status="failed_route",
                reason="直接相关的失败路线或已知边界",
                content=f"{failure.summary}\n{failure.reason_failed}",
                provenance=failure.artifacts,
            )
        )
        for artifact in failure.artifacts:
            caveat = claim_by_id.get(artifact)
            if caveat and caveat.id not in target_claim_ids:
                add(
                    claim_material(
                        caveat, "mandatory", "direct_record", "失败路线所依据的边界/反例记录"
                    )
                )

    for approach in store.list_approaches(ot_dir, pid):
        if (
            target.node_id in approach.resulting_artifacts
            or target.node_id in approach.notes
            or review_targets.get(approach.id) == target.node_id
        ):
            add(
                ResearchMaterial(
                    key=f"approach:{approach.id}",
                    artifact_id=approach.id,
                    kind="branch",
                    tier="relevant",
                    basis="direct_record",
                    title=approach.objective,
                    status="research_approach",
                    reason="与目标明确关联的研究路线；不是已成立依赖",
                    content=f"{approach.method}\n{approach.notes}",
                    provenance=approach.resulting_artifacts,
                )
            )

    linked_ids = {item.artifact_id for item in materials.values()}
    episode_ids = _record_episodes(ot_dir, pid, linked_ids)
    for episode in list_episodes(ot_dir, pid):
        if episode.episode_id not in episode_ids:
            continue
        path = source_path(ot_dir, episode.archive_path)
        add(
            ResearchMaterial(
                key=f"episode:{episode.episode_id}",
                artifact_id=episode.episode_id,
                kind="episode",
                tier="relevant",
                basis="source",
                title=episode.source_filename,
                status="archived_source",
                reason="上述材料可追溯的原始研究 Episode",
                content=path.read_text(encoding="utf-8") if path.is_file() else "",
                source_path=str(path) if path.is_file() else None,
                provenance=[episode.archive_path, episode.content_sha256, episode.provenance or ""],
            )
        )

    # Source manuscript is background, not an Episode and not a proof certificate.
    cited_papers = {
        source_id
        for item in materials.values()
        for source_id in item.provenance
        if source_id.startswith("PAPER-")
    }
    for paper_id in cited_papers:
        paper = get_paper(ot_dir, paper_id)
        if paper is None:
            continue
        if paper.source_connector == "harness_source":
            from math_research.ledger.sources import read_source

            # Explicitly required/cited Sources still fail closed on a SHA mismatch.
            # Optional stale Source navigation must not bypass this content boundary.
            read_source(ot_dir, pid, paper_id)
        path = (ot_dir / paper.local_path).resolve() if paper.local_path else None
        add(
            ResearchMaterial(
                key=f"paper:{paper.id}",
                artifact_id=paper.id,
                kind="paper",
                tier="optional",
                basis="source",
                title=paper.title or paper.source,
                status="pinned_source" if paper.pinned else "unverified_source",
                reason="论文原件背景；需核查具体定理/页码，不是系统验证证书",
                source_path=str(path) if path and path.is_file() else None,
                provenance=[paper.source, paper.sha256 or ""],
                included=False,
            )
        )

    # A scoped lexical hit is never upgraded to a logical dependency.
    for doc, score in search_documents(scoped_docs, statement, k=len(scoped_docs)):
        key = _search_key(doc.artifact_type, doc.artifact_id)
        if key in materials or doc.artifact_id == target.node_id:
            continue
        add(
            ResearchMaterial(
                key=key,
                artifact_id=doc.artifact_id,
                kind=doc.artifact_type,
                tier="optional",
                basis="textual",
                title=doc.title,
                status="text_match_only",
                reason=f"同 scope 词项匹配 (score={score:.2f})；不构成数学依赖",
                content=doc.text,
                included=False,
            )
        )

    if related_memory is not None:
        if related_memory.problem_id != pid or related_memory.target_id != target.node_id:
            raise ResearchError(
                "Soft relevance result belongs to a different research target/scope."
            )
        for hit in related_memory.hits:
            if (
                hit.validation_status != "reranked"
                or hit.relevance_score is None
                or hit.relevance_score < 0.5
                or hit.category == "irrelevant"
            ):
                continue
            soft_doc = documents.get(f"{hit.object_type}:{hit.object_id}")
            if soft_doc is None:
                raise ResearchError("Soft relevance object is outside the current Problem.")
            body = soft_doc.text
            soft_proof = next((p for p in proofs if p.id == hit.object_id), None)
            path = _proof_path(ot_dir, pid, soft_proof) if soft_proof else None
            if path:
                body = path.read_text(encoding="utf-8")
            add(
                ResearchMaterial(
                    key=_search_key(soft_doc.artifact_type, soft_doc.artifact_id),
                    artifact_id=soft_doc.artifact_id,
                    kind=soft_doc.artifact_type,
                    tier="relevant",
                    basis="soft_relevance",
                    title=soft_doc.title,
                    status="query_relevance_only",
                    reason=hit.short_reason + "；非逻辑依赖/数学验证",
                    content=body,
                    source_path=str(path) if path else None,
                    provenance=[
                        f"query target:{target.node_id}",
                        *hit.retrieval_reasons,
                        *sorted(_record_episodes(ot_dir, pid, {soft_doc.artifact_id})),
                    ],
                )
            )

        # Keep original Episode provenance for newly selected soft materials too.
        selected_episode_ids = _record_episodes(
            ot_dir, pid, {item.artifact_id for item in materials.values() if item.included}
        )
        for episode in list_episodes(ot_dir, pid):
            if episode.episode_id not in selected_episode_ids:
                continue
            episode_path = source_path(ot_dir, episode.archive_path)
            add(
                ResearchMaterial(
                    key=f"episode:{episode.episode_id}",
                    artifact_id=episode.episode_id,
                    kind="episode",
                    tier="relevant",
                    basis="source",
                    title=episode.source_filename,
                    status="archived_source",
                    reason="检索材料对应的完整原始 Episode；非逻辑前提",
                    content=episode_path.read_text(encoding="utf-8")
                    if episode_path.is_file()
                    else "",
                    source_path=str(episode_path) if episode_path.is_file() else None,
                    provenance=[
                        episode.archive_path,
                        episode.content_sha256,
                        episode.provenance or "",
                    ],
                )
            )

    chosen = include or set()
    omitted = exclude or set()
    unknown = (chosen | omitted) - set(materials)
    if unknown:
        raise ResearchError(
            f"Unknown material keys in this Problem Record: {', '.join(sorted(unknown))}"
        )
    if chosen & omitted:
        raise ResearchError("A material cannot be both included and excluded.")
    warnings: list[str] = [
        f"{doc.artifact_id}: {caution}"
        for doc in scoped_docs
        for caution in doc.caveats
        if caution.startswith("Unavailable pinned Source:")
    ]
    for key, item in materials.items():
        recalled = by_object.get(item.artifact_id)
        if recalled and recalled.caveats:
            caution = "\n".join(recalled.caveats)
            item.reason += "\n" + caution
            warnings.append(f"Historical material {item.artifact_id}: {caution}")
        item.included = (item.tier != "optional" or key in chosen) and key not in omitted
        if item.tier == "mandatory" and not item.included:
            warnings.append(f"Mandatory material excluded by human choice: {key}")
    ordered = sorted(materials.values(), key=lambda item: (_ORDER[item.tier], item.key))
    return ResearchManifest(
        problem_id=pid,
        target=target,
        language=language,
        created_at=datetime.now().astimezone(),
        materials=ordered,
        warnings=warnings,
    )


def _search_key(artifact_type: str, artifact_id: str) -> str:
    mapping = {
        "dossier:claim": "claim",
        "dossier:proof": "proof",
        "dossier:counterexample": "counterexample",
        "dossier:failed": "failed",
        "dossier:evidence": "evidence",
        "dossier:approach": "approach",
        "dossier:episode": "episode",
        "campaign:obligation": "obligation",
        "campaign:branch": "branch",
    }
    return f"{mapping.get(artifact_type, artifact_type)}:{artifact_id}"


def render_manifest(manifest: ResearchManifest) -> str:
    zh = manifest.language == "zh"
    heading = "研究资料清单" if zh else "Research Manifest"
    lines = [
        f"# {heading}: {manifest.target.node_id}",
        "",
        f"Scope: `{manifest.problem_id}` · Target: `{manifest.target.kind}` · "
        "human-confirmed relations ≠ mathematical verification",
        "",
    ]
    labels = (
        ("mandatory", "必要材料 / Mandatory"),
        ("relevant", "相关材料 / Relevant"),
        ("optional", "可选背景 / Optional"),
    )
    for tier, title in labels:
        lines.extend([f"## {title}", ""])
        for item in manifest.materials:
            if item.tier != tier:
                continue
            selected = "x" if item.included else " "
            lines.append(f"- [{selected}] `{item.key}` [{item.status}; {item.basis}] {item.title}")
            lines.append(f"  - {item.reason}")
            if item.source_path:
                lines.append(f"  - Full source: `{item.source_path}`")
            if item.provenance:
                lines.append(f"  - Provenance: {'; '.join(item.provenance)}")
        lines.append("")
    if manifest.warnings:
        lines.extend(["## Selection warnings", "", *(f"- {w}" for w in manifest.warnings), ""])
    return "\n".join(lines).rstrip() + "\n"
