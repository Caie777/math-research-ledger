"""Read-only research state derived from canonical ledgers and episode reviews.

Research resolution and human authority never imply machine verification.
Nothing in this module changes Problem Record status or rewrites historical records.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from math_research.ledger.archive import source_path
from math_research.ledger.episodes import (
    Proposal,
    list_candidates,
    list_episodes,
    list_reviews,
)
from math_research.ledger.identity import ScopedIdentityResolver
from math_research.ledger.premises import PremiseDecision, semantic_premise
from math_research.ledger.records import store
from math_research.ledger.verification.proofs import list_proofs

Authority = Literal["CANONICAL", "PROVISIONAL", "REJECTED/HISTORICAL"]
ReviewState = Literal["ACCEPTED", "PROVISIONAL", "REJECTED", "DEFERRED"]
VerificationState = Literal["NOT_CHECKED", "CHECKED", "VERIFIER_PASSED", "VERIFIER_FAILED"]
ResearchState = Literal[
    "OPEN",
    "PARTIALLY_RESOLVED",
    "RESOLVED",
    "CURRENT",
    "REVISED",
    "REFUTED",
    "SUPERSEDED",
    "HISTORICAL",
    "INVALIDATED",
]


class KnowledgeState(BaseModel):
    object_id: str
    kind: str
    research_state: ResearchState = "CURRENT"
    verification: VerificationState = "NOT_CHECKED"
    authority: Authority = "CANONICAL"
    review: ReviewState = "ACCEPTED"
    canonical_id: str | None = None
    resolution_ids: list[str] = Field(default_factory=list)
    replacement_ids: list[str] = Field(default_factory=list)
    derivation_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    provenance: list[str] = Field(default_factory=list)
    relation_confirmations: list[str] = Field(default_factory=list)
    thread_ids: list[str] = Field(default_factory=list)
    premise_decision: PremiseDecision | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def usable_premise(self) -> bool:
        return self._premise().usable_working_premise

    def _premise(self) -> PremiseDecision:
        return self.premise_decision or semantic_premise(
            self.kind, self.research_state, self.authority, self.verification, self.warnings
        )

    @property
    def premise_eligibility(self) -> str:
        return self._premise().premise_eligibility

    @property
    def premise_reasons(self) -> list[str]:
        return self._premise().premise_reasons

    @property
    def conditional_premise(self) -> bool:
        return self._premise().conditional_premise


def research_version(ot_dir: Path, problem_id: str) -> str:
    """Content-based version, including bodies/reviews; no mtime or cached truth state."""
    ot_dir = ot_dir.resolve()
    base = store.dossier_dir(ot_dir, problem_id)
    ignored = {"generated", "research_runs", "experiments", "campaigns", "__pycache__"}
    paths = [
        p
        for p in base.rglob("*")
        if p.is_file()
        and not ignored.intersection(p.relative_to(base).parts)
        and p.name != "report.md"
        and not p.name.endswith(".lock")
    ]
    paths.extend(p for p in (ot_dir / "proofs.jsonl", ot_dir / "graph.jsonl") if p.is_file())
    # Obligation/dependency changes must also invalidate a bundle.
    checksum = hashlib.sha256()
    # Global raw sources belong to the logical Problem view, not its directory.
    # Hash only scoped metadata so unrelated imports do not invalidate this view.
    for episode in list_episodes(ot_dir, problem_id):
        checksum.update(episode.model_dump_json().encode() + b"\0")
        path = source_path(ot_dir, episode.archive_path)
        if path.is_file():
            paths.append(path)
    for path in sorted(set(paths)):
        checksum.update(path.relative_to(ot_dir).as_posix().encode())
        checksum.update(b"\0" + path.read_bytes() + b"\0")
    return checksum.hexdigest()


def candidate_dependencies(
    candidate: Proposal, candidates: list[Proposal], resolver: ScopedIdentityResolver
) -> list[str]:
    def resolve(value):
        result = resolver.resolve(
            value, problem_id=candidate.problem_id, episode_id=candidate.episode_id
        )
        if result.ref is None:
            return value
        return (
            result.ref.object_id
            if result.ref.problem_id == candidate.problem_id
            else result.ref.qualified_id
        )

    return list(
        dict.fromkeys(
            resolve(value)
            for value in [
                *candidate.uses,
            ]
        )
    )


class KnowledgeStateResolver:
    """Fresh derived view on every call; Episode/Proposal remains the provisional layer."""

    def __init__(self, ot_dir: Path):
        self.ot_dir = ot_dir

    def resolve(self, problem_id: str, *, currentness: bool = True) -> dict[str, KnowledgeState]:
        store.require_dossier(self.ot_dir, problem_id)
        states: dict[str, KnowledgeState] = {}
        claims = store.list_claims(self.ot_dir, problem_id)
        proofs = store.list_proof_attempts(self.ot_dir, problem_id)
        candidates = list_candidates(self.ot_dir, problem_id)
        reviews = list_reviews(self.ot_dir, problem_id)
        latest = {r.candidate_id: r for r in reviews}
        checks = {p.id: p for p in list_proofs(self.ot_dir)}
        for claim in claims:
            research_state: ResearchState = "OPEN" if claim.type == "OPEN_GAP" else "CURRENT"
            if claim.status == "refuted":
                research_state = "RESOLVED" if claim.type == "OPEN_GAP" else "REFUTED"
            elif claim.type == "OPEN_GAP" and claim.status in {"verified", "formally_verified"}:
                research_state = "RESOLVED"
            states[claim.id] = KnowledgeState(
                object_id=claim.id,
                kind=claim.type,
                research_state=research_state,
                verification="VERIFIER_PASSED"
                if claim.status in {"verified", "formally_verified"}
                else "NOT_CHECKED",
                dependencies=claim.depends_on,
                provenance=claim.source_artifacts,
                warnings=[f"Ledger status: {claim.status}"]
                if claim.status in {"contradicted", "needs_review"}
                else [],
            )
        for proof in proofs:
            states[proof.id] = KnowledgeState(
                object_id=proof.id,
                kind="proof",
                research_state="INVALIDATED"
                if proof.status in {"blocked", "abandoned"}
                else "CURRENT",
                verification="VERIFIER_PASSED" if proof.status == "verified" else "NOT_CHECKED",
                # claim_links are conclusions/targets, not logical premises.
                dependencies=[],
                provenance=[proof.body_path or ""],
            )
        from math_research.core.errors import ResearchError
        from math_research.ledger.records.counterexamples import read_counterexample

        for counterexample in store.list_counterexamples(self.ot_dir, problem_id):
            warnings = [
                "Human-accepted Counterexample; verification text is not a verifier certificate"
            ]
            try:
                read_counterexample(self.ot_dir, counterexample)
            except (ResearchError, UnicodeError) as exc:
                warnings.append(f"Unresolved dependency: counterexample body integrity ({exc})")
            states[counterexample.id] = KnowledgeState(
                object_id=counterexample.id,
                kind="counterexample",
                provenance=[*counterexample.source_artifacts, counterexample.body_path],
                warnings=warnings,
            )
        for reader, kind in (
            (store.list_evidence, "evidence"),
            (store.list_failed_attempts, "failed_attempt"),
            (store.list_assumptions, "assumption"),
            (store.list_known_results, "known_result"),
            (store.list_approaches, "branch"),
            (store.list_definitions, "definition"),
        ):
            for item in reader(self.ot_dir, problem_id):
                states[item.id] = KnowledgeState(
                    object_id=item.id,
                    kind=kind,
                    research_state="HISTORICAL" if kind == "failed_attempt" else "CURRENT",
                )

        identity = ScopedIdentityResolver.from_state(self.ot_dir)
        aliases = {
            r.candidate_id: r.mapped_id for r in reviews if r.decision == "accept" and r.mapped_id
        }
        for candidate in candidates:
            review = latest.get(candidate.candidate_id)
            decision: ReviewState = (
                "ACCEPTED"
                if review and review.decision == "accept"
                else "REJECTED"
                if review and review.decision == "reject"
                else "DEFERRED"
                if review
                else "PROVISIONAL"
            )
            mapped = aliases.get(candidate.candidate_id)
            if decision == "ACCEPTED" and mapped in states:
                accepted_candidate = (
                    review.reviewed_candidate if review and review.reviewed_candidate else candidate
                )
                canonical = states[mapped]
                canonical.provenance.extend([candidate.episode_id, candidate.candidate_id])
                canonical.dependencies = list(
                    dict.fromkeys(
                        [
                            *canonical.dependencies,
                            *[
                                aliases.get(d, d)
                                for d in candidate_dependencies(
                                    accepted_candidate, candidates, identity
                                )
                            ],
                        ]
                    )
                )
                canonical.thread_ids = list(
                    dict.fromkeys([*canonical.thread_ids, *candidate.thread_ids])
                )
                states[candidate.candidate_id] = canonical.model_copy(
                    deep=True,
                    update={
                        "object_id": candidate.candidate_id,
                        "canonical_id": mapped,
                    },
                )
                continue
            deps = candidate_dependencies(candidate, candidates, identity)
            state = KnowledgeState(
                object_id=candidate.candidate_id,
                kind=candidate.kind,
                authority="REJECTED/HISTORICAL"
                if decision == "REJECTED"
                else "CANONICAL"
                if decision == "ACCEPTED"
                else "PROVISIONAL",
                review=decision,
                canonical_id=mapped,
                research_state="HISTORICAL"
                if decision == "REJECTED" or candidate.kind == "failed_attempt"
                else "OPEN"
                if candidate.kind == "gap"
                else "CURRENT",
                dependencies=[aliases.get(d, d) for d in deps],
                provenance=[candidate.episode_id],
                thread_ids=candidate.thread_ids,
            )
            # Actual verifier artifacts only; source_reported_status never grants verification.
            artifacts: list[str] = []
            for dep in [*artifacts, candidate.source_fields.get("verification_artifact", "")]:
                checked = checks.get(dep)
                if checked:
                    state.verification = (
                        "VERIFIER_PASSED"
                        if checked.accepted
                        else "VERIFIER_FAILED"
                        if checked.available and not checked.inconclusive
                        else "CHECKED"
                    )
                    state.derivation_ids.append(dep)
            states[candidate.candidate_id] = state

        # Stable IDs must already exist when a later Episode explicitly USES
        # them. Sharing this state here also propagates existing review policy.
        for candidate in candidates:
            if candidate.object_id:
                states[candidate.object_id] = states[candidate.candidate_id]

        # Include explicit logical edges in the intrinsic semantic pass, too.
        from math_research.ledger.dependencies import PREMISE_ROLES, Dependency
        from math_research.ledger.persistence import records

        for dep_edge in records(self.ot_dir, "dependencies", Dependency):
            source_ref = identity.resolve(dep_edge.dependent.qualified_id).ref
            target_ref = identity.resolve(dep_edge.target.qualified_id).ref
            if (
                dep_edge.role not in PREMISE_ROLES
                or source_ref is None
                or source_ref.problem_id != problem_id
            ):
                continue
            if source_ref.object_id in states:
                value = (
                    target_ref.object_id
                    if target_ref and target_ref.problem_id == problem_id
                    else dep_edge.target.qualified_id
                )
                if value not in states[source_ref.object_id].dependencies:
                    states[source_ref.object_id].dependencies.append(value)

        pending_resolutions: list[tuple[str, str, str, str]] = []
        pending_invalidations: list[tuple[str, str, str]] = []

        def affect(target: str | None, source: str | None, relation: str, witness: str) -> None:
            if not target or not source or target not in states or source not in states:
                return
            current = states[target]
            if states[source].authority != "CANONICAL":
                return
            if relation in {"REFUTES", "INVALIDATES", "PROVES"}:
                from math_research.ledger.relations.policy import validate_mathematical_relation

                try:
                    validate_mathematical_relation(
                        self.ot_dir, problem_id, source, relation, target
                    )
                except (ResearchError, UnicodeError) as exc:
                    current.warnings.append(f"Unqualified {relation} relation ignored: {exc}")
                    return
            if relation == "INVALIDATES":
                pending_invalidations.append((target, source, witness))
                return
            if relation in {"PROVES", "RESOLVES", "REFUTES"}:
                pending_resolutions.append((target, source, relation, witness))
                return
            if relation in {"USES", "DEPENDS_ON"}:
                states[source].dependencies.append(target)
                states[source].dependencies = list(dict.fromkeys(states[source].dependencies))
                states[source].derivation_ids.append(witness)
                return
            elif relation in {"REVISES", "SUPERSEDES"}:
                current.research_state = "REVISED" if relation == "REVISES" else "SUPERSEDED"
                current.replacement_ids.append(source)
            else:
                return
            current.derivation_ids.append(witness)
            if states[source].verification != "VERIFIER_PASSED":
                current.warnings.append(
                    "Confirmed research relation; not mathematical verification"
                )

        from math_research.ledger.relations.ledger import active_relations

        for relation_edge in active_relations(self.ot_dir, problem_id):
            affect(
                relation_edge.target_id,
                relation_edge.source_id,
                relation_edge.relation,
                relation_edge.decision_id,
            )
            for ident in (relation_edge.source_id, relation_edge.target_id):
                if ident in states:
                    states[ident].relation_confirmations.append(relation_edge.label)
                    states[ident].provenance.append(relation_edge.decision_id)

        for review in reviews:
            if review.decision != "accept":
                continue
            reviewed = review.reviewed_candidate
            if reviewed and reviewed.revises_proof_id:
                affect(
                    aliases.get(reviewed.revises_proof_id, reviewed.revises_proof_id),
                    review.mapped_id,
                    "REVISES",
                    review.candidate_id,
                )
        # Existing graph edges are manual/accepted through the same write boundary.
        # Support/contradiction alone are evidence, not resolutions or refutations.
        from math_research.ledger.relations.edges import list_edges

        graph_relations = {
            "resolves": "RESOLVES",
            "supersedes": "SUPERSEDES",
            "depends_on": "DEPENDS_ON",
        }
        for edge in list_edges(self.ot_dir):
            if edge.relation in graph_relations:
                affect(edge.target_id, edge.source_id, graph_relations[edge.relation], edge.id)
        for failure in store.list_failed_attempts(self.ot_dir, problem_id):
            for artifact in failure.artifacts:
                if artifact in states and states[artifact].kind == "proof":
                    states[artifact].research_state = "INVALIDATED"
                    states[artifact].derivation_ids.append(failure.id)

        # A small provenance walk, not a dependency database or planner.
        def warn_dependencies() -> None:
            for state in states.values():
                queue = list(state.dependencies)
                seen = {state.object_id}
                while queue:
                    dep = queue.pop()
                    if dep in seen:
                        continue
                    seen.add(dep)
                    upstream = states.get(dep)
                    if not upstream:
                        state.warnings.append(f"Unresolved dependency: {dep}")
                        continue
                    if upstream.review == "REJECTED":
                        state.warnings.append(f"upstream rejected dependency: {dep}")
                    elif upstream.conditional_premise:
                        state.warnings.append(f"Conditional upstream assumption: {dep}")
                    elif upstream.kind == "obligation":
                        state.warnings.append(
                            f"upstream unproved research target dependency: {dep}"
                        )
                    elif not upstream.usable_premise:
                        state.warnings.append(f"upstream historical/invalidated dependency: {dep}")
                    queue.extend(upstream.dependencies)

        # Resolve attacks on proof witnesses before using them for Gap closure.
        # Cyclic attacks are ambiguous and never grant a usable derivation.
        visiting: set[str] = set()
        visited: set[str] = set()

        def invalidate(target: str) -> None:
            if target in visited:
                return
            if target in visiting:
                for ident in visiting:
                    states[ident].warnings.append("upstream cyclic INVALIDATES relation")
                return
            visiting.add(target)
            for affected, source, witness in pending_invalidations:
                if affected != target:
                    continue
                invalidate(source)
                warn_dependencies()
                if not states[source].usable_premise:
                    states[target].warnings.append(
                        f"Invalidation source no longer current/usable: {source}"
                    )
                    continue
                states[target].research_state = "INVALIDATED"
                states[target].derivation_ids.extend([source, witness])
                states[target].warnings.append(
                    "INVALIDATES attacks this proof/route; underlying claim is not thereby refuted"
                )
            visiting.remove(target)
            visited.add(target)

        for target, _, _ in pending_invalidations:
            invalidate(target)
        warn_dependencies()
        for target, source, relation, witness in pending_resolutions:
            current = states[target]
            current.derivation_ids.append(witness)
            current.resolution_ids.append(source)
            if not states[source].usable_premise:
                current.warnings.append(f"Resolution source no longer current/usable: {source}")
                continue
            if current.kind == "OPEN_GAP":
                current.research_state = "RESOLVED"
            elif relation == "REFUTES":
                current.research_state = "REFUTED"
            if states[source].verification != "VERIFIER_PASSED":
                current.warnings.append(
                    "Confirmed research relation; not mathematical verification"
                )
        warn_dependencies()
        for candidate_id, canonical_id in aliases.items():
            if canonical_id in states:
                states[candidate_id] = states[canonical_id].model_copy(
                    deep=True,
                    update={"object_id": candidate_id, "canonical_id": canonical_id},
                )
        # Stable working IDs alias the same proposal/review state, never the
        # default human authority of a newly inserted Claim ledger row.
        for candidate in candidates:
            if candidate.object_id:
                current = states[candidate.candidate_id]
                current.provenance = list(
                    dict.fromkeys(
                        [
                            *current.provenance,
                            candidate.candidate_id,
                            candidate.episode_id
                            + "/"
                            + (candidate.local_id or candidate.candidate_id),
                        ]
                    )
                )
                states[candidate.object_id] = current.model_copy(
                    deep=True, update={"object_id": candidate.object_id}
                )
        for state in states.values():
            state.warnings = list(dict.fromkeys(state.warnings))
            state.resolution_ids = list(dict.fromkeys(state.resolution_ids))
            state.replacement_ids = list(dict.fromkeys(state.replacement_ids))
            state.derivation_ids = list(dict.fromkeys(state.derivation_ids))
        if currentness:
            # Manifest uses the intrinsic pass above, avoiding recursive projection.
            # Public KnowledgeState consumers get the same graph/currentness decision
            # as ObjectView rather than a second interpretation of premise safety.
            from math_research.ledger.manifest import Ledger
            from math_research.ledger.projection import list_objects

            ledger = Ledger(self.ot_dir)
            views = list_objects(self.ot_dir)
            entries = [view.object for view in views]
            decisions = {view.object.qualified_id: view for view in views}
            resolver = ledger._identity(entries)
            for ident, state in states.items():
                resolution = resolver.resolve(ident, problem_id=problem_id)
                if resolution.ref:
                    view = decisions[resolution.ref.qualified_id]
                    state.premise_decision = PremiseDecision(
                        premise_eligibility=view.premise_eligibility,
                        premise_reasons=view.premise_reasons,
                    )
        return states
