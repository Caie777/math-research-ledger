"""Bounded publication navigation derived from existing proposals and review aliases."""

from pathlib import Path

from math_research.ledger.episodes import list_candidates, list_reviews
from math_research.ledger.identity import ScopedIdentityResolver, working_ref
from math_research.ledger.projection import ObjectView


def publication_navigation(
    state: Path,
    problem_id: str,
    episode_id: str,
    views: list[ObjectView],
    *,
    offset: int = 0,
    limit: int = 6,
) -> dict:
    """Never reparse prose or infer missing legacy mappings. No persisted new state."""
    candidates = list_candidates(state, problem_id)
    reviews = list_reviews(state, problem_id)
    resolver = ScopedIdentityResolver((v.object.ref for v in views), candidates, reviews)
    by_ref = {v.object.qualified_id: v for v in views}
    decisions = {r.candidate_id: r for r in reviews}
    produced, relations = [], []
    for row in sorted(candidates, key=lambda c: c.candidate_id):
        if row.episode_id != episode_id:
            continue
        review = decisions.get(row.candidate_id)
        common = {
            "candidate_id": row.candidate_id,
            "local_id": row.local_id,
            "kind": row.kind,
            "review_decision": review.decision if review else "UNREVIEWED",
        }
        if row.kind == "relation":
            relations.append({**common, "relation": row.relation})
            continue
        original = working_ref(row)
        resolved = resolver.resolve(row.candidate_id, problem_id=problem_id)
        view = by_ref.get(resolved.ref.qualified_id) if resolved.ref else None
        produced.append(
            {
                **common,
                "publication_ref": original.qualified_id,
                "qualified_ref": view.object.qualified_id if view else None,
                "identity_diagnostic": resolved.reason,
                "version": view.object.version if view else None,
                "authority": view.authority if view else None,
                "freshness": view.freshness if view else None,
                "integrity": view.object.integrity if view else None,
                "premise_eligibility": view.premise_eligibility if view else "BLOCKED",
            }
        )
    return {
        "mapping_status": "AVAILABLE"
        if produced or relations
        else "UNAVAILABLE_NO_PERSISTED_MAPPING",
        "mapping_basis": "persisted_episode_proposals_and_reviews",
        "produced_objects": produced[offset : offset + limit],
        "produced_total": len(produced),
        "produced_offset": offset,
        "produced_omitted": len(produced) - len(produced[offset : offset + limit]),
        "next_produced_offset": offset + limit if offset + limit < len(produced) else None,
        "relation_proposals": relations[offset : offset + limit],
        "relation_total": len(relations),
        "next_relation_offset": offset + limit if offset + limit < len(relations) else None,
        "relation_proposals_are_mathematical_objects": False,
    }
