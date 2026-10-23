"""Dependency projection and authored local snapshots, never historical re-pinning."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import Dependency, DependencyRole
from math_research.ledger.identity import ScopedIdentityResolver, working_ref

if TYPE_CHECKING:
    from pathlib import Path

    from math_research.core.refs import VersionPin
    from math_research.ledger.episodes import Proposal, ResearchEpisode


def candidate_edges(
    candidate: Proposal,
    resolver: ScopedIdentityResolver,
    *,
    dependent: ObjectRef | None = None,
    input_pins: list[VersionPin] | tuple[VersionPin, ...] = (),
) -> list[Dependency]:
    pairs = [(value, DependencyRole.LOGICAL_PREMISE) for value in candidate.uses]
    if candidate.target_id:
        if candidate.kind in {"proof", "refutation"}:
            pairs.append((candidate.target_id, DependencyRole.PROOF_TARGET))
        elif candidate.kind == "evidence":
            pairs.append((candidate.target_id, DependencyRole.EVIDENCE))
    pins = [*input_pins, *candidate.dependency_pins]
    result = {}
    for value, role in pairs:
        resolution = resolver.resolve(
            value, problem_id=candidate.problem_id, episode_id=candidate.episode_id
        )
        target = resolution.ref
        if target is None:
            try:
                target = (
                    ObjectRef.parse(value)
                    if ":" in value
                    else ObjectRef(
                        problem_id=candidate.problem_id, kind="unresolved", object_id=value
                    )
                )
            except ValueError:
                target = ObjectRef(
                    problem_id=candidate.problem_id,
                    kind="unresolved",
                    object_id=hashlib.sha256(value.encode()).hexdigest()[:24],
                )
        if role == DependencyRole.LOGICAL_PREMISE and target.kind == "definition":
            role = DependencyRole.DEFINITION
        versions = {
            pin.version
            for pin in pins
            if pin.ref == target
            or (
                resolution.ref is not None
                and resolver.resolve(pin.ref.qualified_id).ref == resolution.ref
            )
        }
        if len(versions) > 1:
            raise ResearchError("Conflicting historical versions for one dependency input.")
        edge = Dependency(
            dependent=dependent or working_ref(candidate),
            target=target,
            role=role,
            expected_version=next(iter(versions), None),
            provenance="episode_input" if versions else "existing_record",
            resolution_reason=resolution.reason,
        )
        result[edge.key] = edge
    return list(result.values())


def bind_local_inputs(
    state: Path, proposed: list[Proposal], episodes: dict[str, ResearchEpisode], known: set[str]
) -> list[Proposal]:
    """Pin only brand-new same-Episode objects parsed from these exact source bytes.

    External usage requires caller-supplied input_versions. Never look up today's
    version to fill an absent historical input. Old proposal rows are not rewritten.
    """
    from math_research.core.hashing import content_hash
    from math_research.core.refs import VersionPin
    from math_research.ledger.episodes import list_candidates, list_reviews
    from math_research.ledger.manifest import Ledger, record_content_hash
    from math_research.ledger.records import store

    fresh = {
        c.candidate_id: c for c in proposed if c.candidate_id not in known and c.kind != "relation"
    }
    if not fresh:
        return proposed
    existing = Ledger(state).objects()
    candidates, reviews = [], []
    for problem in store.list_dossiers(state):
        candidates.extend(list_candidates(state, problem.id))
        reviews.extend(list_reviews(state, problem.id))
    candidates.extend(fresh.values())
    resolver = ScopedIdentityResolver(
        [*(e.ref for e in existing), *(working_ref(c) for c in fresh.values())],
        candidates,
        reviews,
    )
    by_ref = {working_ref(c).qualified_id: c for c in fresh.values()}
    versions: dict[str, str | None] = {}
    visiting: set[str] = set()

    def bind(candidate: Proposal) -> str | None:
        key = candidate.candidate_id
        if key in visiting or len(visiting) >= 256:
            return None  # Cyclic/oversized authored closures remain explicitly unbound.
        if key in versions:
            return versions[key]
        visiting.add(key)
        episode = episodes[candidate.episode_id]
        # Explicit input versions are immutable assertions, even if already stale.
        candidate.dependency_pins = list(episode.input_versions)
        edges = candidate_edges(candidate, resolver)
        for edge in edges:
            upstream = by_ref.get(edge.target.qualified_id)
            if (
                edge.expected_version is None
                and upstream
                and upstream.episode_id == candidate.episode_id
            ):
                version = bind(upstream)
                if version:
                    candidate.dependency_pins.append(VersionPin(ref=edge.target, version=version))
        edges = candidate_edges(candidate, resolver)
        version = content_hash(
            {
                "content": record_content_hash(
                    candidate.model_dump(mode="json"), candidate.body, []
                ),
                "dependencies": sorted(
                    (e.target.qualified_id, e.role.value, e.expected_version) for e in edges
                ),
            }
        )
        visiting.remove(key)
        versions[key] = version
        return version

    for candidate in fresh.values():
        bind(candidate)
    return proposed
