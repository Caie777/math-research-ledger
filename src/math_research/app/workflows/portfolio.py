"""Deterministic read-only portfolio. Run completion is never mathematical truth."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from math_research.agent.progress import ResearchRunProgress, read_progress
from math_research.agent.runtime import read_run
from math_research.memory.episodes import list_candidates, list_episodes, list_reviews
from math_research.memory.handoff import resolved_work_ids
from math_research.memory.records import store
from math_research.memory.state import KnowledgeState, KnowledgeStateResolver


class TargetSummary(BaseModel):
    problem_id: str
    target_id: str
    title: str
    state: KnowledgeState


class ProblemPortfolio(BaseModel):
    problem_id: str
    title: str
    primary_target_id: str | None
    research_state: str | None
    target_state: KnowledgeState | None
    latest_episode: str | None
    latest_episode_time: datetime | None
    latest_run_id: str | None
    latest_run_status: str | None
    latest_run_stop_reason: str | None
    latest_run_updated_at: datetime | None
    open_gap_count: int
    candidate_result_count: int
    human_review_summary: dict[str, int]
    last_research_activity: datetime | None
    # Internal resolution view. Queries expose targets once under their own key,
    # rather than duplicate all per-target provenance in each portfolio row/prompt.
    unresolved_targets: list[TargetSummary] = Field(default_factory=list, exclude=True)
    authority_note: str = (
        "Run status is operational. Target state comes from KnowledgeStateResolver; "
        "candidates remain provisional until Human Review. Resolution is not verification."
    )


def saved_progress(ot_dir: Path) -> list[ResearchRunProgress]:
    result = []
    for path in sorted((ot_dir / "research_runs").glob("*/run.json")):
        result.append(read_progress(path.parent, read_run(ot_dir, path.parent.name)))
    return sorted(result, key=lambda p: (p.started_at, p.run_id), reverse=True)


def research_portfolio(ot_dir: Path, problem_id: str | None = None) -> list[ProblemPortfolio]:
    """Unknown facts stay null. No LLM, cached truth, log scraping, or writes."""
    progress = saved_progress(ot_dir)
    rows = []
    for problem in store.list_dossiers(ot_dir):
        if problem_id and problem.id != problem_id:
            continue
        states = KnowledgeStateResolver(ot_dir).resolve(problem.id)
        closed = resolved_work_ids(states)
        candidates = list_candidates(ot_dir, problem.id)
        reviews = {r.candidate_id: r for r in list_reviews(ot_dir, problem.id)}
        counts = Counter(
            reviews[c.candidate_id].decision if c.candidate_id in reviews else "pending"
            for c in candidates
        )
        episodes = sorted(
            list_episodes(ot_dir, problem.id),
            key=lambda e: (e.imported_at, e.episode_id),
            reverse=True,
        )
        latest = episodes[0] if episodes else None
        runs = [p for p in progress if p.problem_id == problem.id]
        run = runs[0] if runs else None
        unresolved = []
        for claim in store.list_claims(ot_dir, problem.id):
            state = states[claim.id]
            if claim.id not in closed and state.research_state not in {
                "RESOLVED",
                "REFUTED",
                "SUPERSEDED",
                "HISTORICAL",
                "INVALIDATED",
                "REVISED",
            }:
                unresolved.append(
                    TargetSummary(
                        problem_id=problem.id,
                        target_id=claim.id,
                        title=claim.statement[:300],
                        state=state,
                    )
                )
        for candidate in candidates:
            candidate_state = states.get(candidate.object_id or "")
            if (
                candidate.kind in {"claim", "gap"}
                and candidate.object_id
                and candidate_state
                and (
                    candidate_state.authority == "PROVISIONAL"
                    and candidate_state.review != "REJECTED"
                    and candidate.object_id not in closed
                    and candidate_state.research_state
                    not in {
                        "RESOLVED",
                        "REFUTED",
                        "REVISED",
                        "SUPERSEDED",
                        "HISTORICAL",
                        "INVALIDATED",
                    }
                )
            ):
                unresolved.append(
                    TargetSummary(
                        problem_id=problem.id,
                        target_id=candidate.object_id,
                        title=candidate.title[:300],
                        state=candidate_state,
                    )
                )
        target_state = states.get(problem.primary_claim_id or "")
        activity = [e.imported_at for e in episodes]
        activity.extend(p.last_activity_at for p in runs)
        activity.extend(r.decided_at for r in reviews.values())
        rows.append(
            ProblemPortfolio(
                problem_id=problem.id,
                title=problem.title,
                primary_target_id=problem.primary_claim_id,
                research_state=target_state.research_state if target_state else None,
                target_state=target_state,
                latest_episode=latest.episode_id if latest else None,
                latest_episode_time=latest.imported_at if latest else None,
                latest_run_id=run.run_id if run else None,
                latest_run_status=run.status if run else None,
                latest_run_stop_reason=run.stop_reason if run else None,
                latest_run_updated_at=run.updated_at if run else None,
                open_gap_count=sum(t.state.kind in {"OPEN_GAP", "gap"} for t in unresolved),
                candidate_result_count=sum(c.kind == "claim" for c in candidates),
                human_review_summary={
                    key: counts[key] for key in ("pending", "accept", "reject", "defer")
                },
                last_research_activity=max(activity) if activity else None,
                unresolved_targets=unresolved,
            )
        )
    return rows
