"""Bounded, deterministic session orientation; never a research planner or writer."""

from collections import Counter
from pathlib import Path

from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash
from math_research.core.refs import ObjectRef
from math_research.ledger.archive import episode_text
from math_research.ledger.episodes import list_candidates, list_episodes
from math_research.ledger.handoff import read_handoff
from math_research.ledger.identity import ScopedIdentityResolver
from math_research.ledger.projection import ObjectView
from math_research.ledger.publication import publication_navigation
from math_research.ledger.records import store


def navigation(view: ObjectView) -> dict:
    entry = view.object
    return {
        "ref": entry.qualified_id,
        "version": entry.version,
        "research_state": entry.research_state,
        "authority": view.authority,
        "verification": view.verification,
        "freshness": view.freshness,
        "integrity": entry.integrity,
        "premise_eligibility": view.premise_eligibility,
        "usable_working_premise": view.usable_working_premise,
        "trusted_formal_premise": view.trusted_formal_premise,
        "conditional_premise": view.conditional_premise,
    }


def fingerprint(view: ObjectView) -> str:
    return content_hash(navigation(view))


def continuation_state(
    state: Path, problem_id: str, views: list[ObjectView], *, since: dict[str, str] | None = None
) -> dict:
    problem = store.require_dossier(state, problem_id)
    selected = [v for v in views if v.object.ref.problem_id == problem_id]
    by_ref = {v.object.qualified_id: v for v in selected}
    candidates = list_candidates(state, problem_id)
    from math_research.ledger.episodes import list_reviews

    identity = ScopedIdentityResolver(
        (v.object.ref for v in selected), candidates, list_reviews(state, problem_id)
    )
    main = (
        identity.resolve(problem.primary_claim_id, problem_id=problem_id)
        if problem.primary_claim_id
        else None
    )
    main_view = by_ref.get(main.ref.qualified_id) if main and main.ref else None
    gaps = [
        v
        for v in selected
        if v.object.ref.kind == "gap"
        and v.object.research_state == "OPEN"
        and v.authority != "REJECTED/HISTORICAL"
    ]
    failures = [v for v in selected if v.object.ref.kind == "failed_attempt"]
    boundaries = [
        v
        for v in selected
        if v.object.ref.kind in {"counterexample", "refutation"}
        or v.object.record.get("conclusion_relation") == "REFUTES"
    ]
    risks = [v for v in selected if v.freshness != "CURRENT" or v.object.integrity == "FAILED"]
    latest: dict | None = None
    handoff = None
    excluded: Counter[str] = Counter()
    for episode in sorted(
        list_episodes(state, problem_id), key=lambda e: (e.imported_at, e.episode_id), reverse=True
    ):
        key = ObjectRef(
            problem_id=problem_id, kind="episode", object_id=episode.episode_id
        ).qualified_id
        view = by_ref.get(key)
        if view is None or view.object.integrity != "VERIFIED":
            excluded["integrity_failed"] += 1
            continue
        if (episode.provenance or "").startswith("SOURCE_DIGEST:"):
            excluded["source_digest_advisory"] += 1
            continue
        rows = [
            c for c in candidates if c.episode_id == episode.episode_id and c.kind != "relation"
        ]
        locals_ = [c.local_id for c in rows if c.local_id]
        if len(set(locals_)) != len(locals_):
            excluded["duplicate_local_id"] += 1
            continue
        descriptor = {
            "ref": key,
            "imported_at": episode.imported_at.isoformat(),
            "authority": "ADVISORY",
            "usable_working_premise": False,
            "integrity": "VERIFIED",
            "load_original_to_restore": True,
        }
        if latest is None and (any(c.body.strip() for c in rows) or episode.state_delta):
            latest = {
                **descriptor,
                "source_assertion_count": len(episode.state_delta),
                "meaningful_basis": "published_objects_or_source_assertions",
            }
        if handoff is None:
            target_id, fields = read_handoff(episode_text(state, episode))
            matches = target_id is None or main_view and target_id == main_view.object.ref.object_id
            if fields and matches:
                handoff = {
                    **descriptor,
                    "field_names": sorted(fields),
                    "recheck_referenced_objects": True,
                }
            elif episode.next_research_directions:
                handoff = {
                    **descriptor,
                    "field_names": ["Next Research Directions"],
                    "recheck_referenced_objects": True,
                }
        if not rows and not episode.state_delta:
            excluded["advisory_or_raw_only"] += 1
        if latest and handoff:
            break
    groups = {
        "open_gaps": gaps,
        "failed_routes": failures,
        "counterexamples_refutations": boundaries,
        "risk_objects": risks,
    }
    premise_groups = {
        "trusted_formal": [v for v in selected if v.trusted_formal_premise],
        "conditional": [v for v in selected if v.conditional_premise],
        "historical_only": [
            v
            for v in selected
            if v.authority == "REJECTED/HISTORICAL"
            or v.object.research_state in {"HISTORICAL", "REVISED", "REFUTED", "SUPERSEDED"}
        ],
        "blocked_positive": [v for v in selected if v.premise_eligibility == "BLOCKED"],
    }
    snapshot_views = [main_view] if main_view else []
    if latest and latest["ref"] in by_ref:
        snapshot_views.append(by_ref[latest["ref"]])
    snapshot_views += gaps + failures + boundaries + risks
    unique_views = {v.object.qualified_id: v for v in snapshot_views}
    snapshot = {key: fingerprint(v) for key, v in list(unique_views.items())[:16]}
    changes: dict = {
        "status": "COMPARED" if since is not None else "NO_BASELINE",
        "scope": "caller_supplied_refs_only",
        "changed": [],
        "unchanged_count": 0,
        "not_a_global_change_log": True,
    }
    if since is not None:
        if len(since) > 32:
            raise ResearchError("Continuation baseline is limited to 32 qualified refs.")
        for key, previous in sorted(since.items()):
            ref = ObjectRef.parse(key)
            if ref.problem_id != problem_id:
                raise ResearchError("Continuation baseline conflicts with selected Problem.")
            view = by_ref.get(key)
            current = fingerprint(view) if view else None
            if current == previous:
                changes["unchanged_count"] += 1
            else:
                changes["changed"].append(
                    {
                        "ref": key,
                        "change": "STATE_OR_VERSION_CHANGED" if view else "ABSENT_OR_ALIASED",
                        "current": navigation(view) if view else None,
                    }
                )
    hints = (
        [
            {"tool": "research_get_object", "arguments": {"ref": main_view.object.qualified_id}},
            {
                "tool": "research_context_packet",
                "arguments": {"ref": main_view.object.qualified_id},
            },
        ]
        if main_view
        else []
    )
    if latest:
        latest.update(
            publication_navigation(
                state, problem_id, ObjectRef.parse(latest["ref"]).object_id, selected
            )
        )
    return {
        "problem_id": problem_id,
        "selection_source": "explicit_problem_id",
        "problem_status": problem.status,
        "lifecycle_status": problem.lifecycle_status,
        "primary_target_statement": problem.primary_target,
        "primary_target": navigation(main_view) if main_view else None,
        "primary_target_diagnostic": main.reason
        if main and main.ref is None
        else "NOT_DESIGNATED"
        if main is None
        else None,
        "object_count": len(selected),
        "counts": {
            **{name: len(values) for name, values in groups.items()},
            "freshness": dict(Counter(v.freshness for v in selected)),
            "integrity_failed": sum(v.object.integrity == "FAILED" for v in selected),
            "premise_eligibility": dict(Counter(v.premise_eligibility for v in selected)),
            "trusted_formal_premises": sum(v.trusted_formal_premise for v in selected),
        },
        **{name: [navigation(v) for v in values[:4]] for name, values in groups.items()},
        "navigation_omitted": {name: max(0, len(values) - 4) for name, values in groups.items()},
        "latest_meaningful_checkpoint": latest,
        "latest_advisory_handoff": handoff,
        "checkpoint_selection_exclusions": dict(excluded),
        "checkpoint_scan_scope": "newest_prefix_until_checkpoint_and_handoff_found",
        "premise_categories": {
            name: {
                "count": len(values),
                "refs": [v.object.qualified_id for v in values[:4]],
                "omitted": max(0, len(values) - 4),
            }
            for name, values in premise_groups.items()
        },
        "continuation_snapshot": snapshot,
        "snapshot_omitted": max(0, len(unique_views) - 16),
        "snapshot_scope": "up_to_16_prioritized_refs_only",
        "changes": changes,
        "recommended_next_calls": hints,
        "memory_policy": "Restore once; free local reasoning; retrieve on relevant events.",
        "semantic_scope": "bounded_navigation_not_full_research_context",
    }
