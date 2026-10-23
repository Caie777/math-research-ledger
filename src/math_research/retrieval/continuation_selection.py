"""Deterministic local checkpoint selection, without lexical budget filling."""

import json
from pathlib import Path

from math_research.core.refs import ObjectRef
from math_research.ledger.episodes import list_candidates, list_episodes, list_reviews
from math_research.ledger.identity import ScopedIdentityResolver
from math_research.ledger.projection import ObjectView


def local_checkpoint_material(
    state: Path, target: ObjectRef, views: dict[str, ObjectView]
) -> tuple[dict[str, str], dict[str, str]]:
    """Return optional identities/reasons and stored checkpoint assertions, never a plan.

    A shared prerequisite or Problem membership is not an incoming-route witness.
    Select the latest intact meaningful publication explicitly attached to this target.
    """
    if target.problem_id is None:
        return {}, {}
    pid = target.problem_id
    candidates, reviews = list_candidates(state, pid), list_reviews(state, pid)
    resolver = ScopedIdentityResolver((v.object.ref for v in views.values()), candidates, reviews)
    reasons, excerpts = {}, {}

    def resolve(reference, episode_id=None):
        value = resolver.resolve(reference, problem_id=pid, episode_id=episode_id)
        return value.ref.qualified_id if value.ref else None

    def attached(view):
        entry = view.object
        if any(d.target == target for d in entry.dependencies):
            return True
        refs = [*entry.record.get("artifacts", []), *entry.record.get("claim_links", [])]
        refs += [entry.record.get("target_id", ""), entry.record.get("claim_id", "")]
        return any(resolve(r) == target.qualified_id for r in refs if r)

    for key, view in views.items():
        if key == target.qualified_id or view.object.ref.problem_id != pid:
            continue
        if view.object.ref.kind in {
            "failed_attempt",
            "counterexample",
            "refutation",
            "proof",
        } and attached(view):
            reasons[key] = "direct_target_record"
    for episode in sorted(
        list_episodes(state, pid), key=lambda e: (e.imported_at, e.episode_id), reverse=True
    ):
        key = ObjectRef(problem_id=pid, kind="episode", object_id=episode.episode_id).qualified_id
        episode_view = views.get(key)
        if (
            not episode_view
            or episode_view.object.integrity != "VERIFIED"
            or (episode.provenance or "").startswith("SOURCE_DIGEST:")
        ):
            continue
        rows = [
            c for c in candidates if c.episode_id == episode.episode_id and c.kind != "relation"
        ]
        local_ids = [c.local_id for c in rows if c.local_id]
        if len(set(local_ids)) != len(local_ids) or not (
            any(c.body.strip() for c in rows) or episode.state_delta
        ):
            continue
        produced = {resolve(c.candidate_id) for c in rows}
        references = [d.reference for d in episode.state_delta]
        references += [r for c in rows for r in [c.target_id, *c.uses] if r]
        linked = target.qualified_id in produced or any(
            resolve(r, episode.episode_id) == target.qualified_id for r in references
        )
        linked = linked or any(k in views and attached(views[k]) for k in produced if k)
        if not linked:
            continue
        reasons[key] = "latest_target_checkpoint_advisory"
        excerpts[key] = json.dumps(
            {
                "state_delta_total": len(episode.state_delta),
                "state_delta_truncated": len(episode.state_delta) > 6
                or any(len(d.statement) > 300 for d in episode.state_delta[:6]),
                "state_delta": [
                    {"action": d.action, "reference": d.reference, "statement": d.statement[:300]}
                    for d in episode.state_delta[:6]
                ],
                "next_directions_advisory": True,
            },
            ensure_ascii=False,
        )
        for produced_key in sorted(k for k in produced if k in views):
            reasons[produced_key] = "latest_checkpoint_produced_object"
            for dep in views[produced_key].object.dependencies:
                if dep.target.qualified_id in views:
                    reasons.setdefault(dep.target.qualified_id, "produced_object_direct_dependency")
        for delta in episode.state_delta:
            resolved = resolve(delta.reference, episode.episode_id)
            if resolved in views:
                reasons.setdefault(resolved, "checkpoint_state_assertion")
        break
    return reasons, excerpts
