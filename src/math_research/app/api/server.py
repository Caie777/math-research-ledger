"""Local Research Web API over structured mathematical memory services.

This module owns transport schemas and task state, never mathematical truth.
The maintenance CLI serves this API and the built React application.
"""

from __future__ import annotations

import json
import os
import threading
from collections import Counter
from collections.abc import AsyncIterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal, TypedDict
from uuid import uuid4

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError

from math_research.app.workflows.episodes import (
    candidates_with_reviews,
    current_object_rows,
    episode_source,
    read_full_proof,
    recent_episodes,
    review_episode_candidate,
)
from math_research.core.errors import ResearchError
from math_research.memory.episodes import (
    DecisionKind,
    Proposal,
    ResearchEpisode,
    ReviewDecision,
    list_episodes,
    list_reviews,
)
from math_research.memory.records import store
from math_research.memory.records.evidence_content import render_evidence
from math_research.memory.relations.ledger import (
    active_relations,
    decision_history,
    enroll_explicit,
    get_policy,
    human_adjudicate,
    list_adjudication_runs,
    list_pool,
    list_scout_runs,
    set_policy,
)
from math_research.memory.relations.models import (
    AdjudicationOutput,
    AdjudicationPolicy,
    AdjudicationRun,
    PoolItem,
    RelationDecision,
    RelationProposal,
    ScoutRun,
)
from math_research.memory.relations.review import adjudicate_selected, select_adjudication_proposals
from math_research.memory.relations.scout import scout_episode, select_scout_candidates
from math_research.memory.state import KnowledgeState, KnowledgeStateResolver
from math_research.memory.target import ResearchTarget
from math_research.retrieval.context import QueryPurpose, ResearchContextBundle
from math_research.retrieval.index import IndexDoc
from math_research.retrieval.recall import FileSearchResult, HistoryCheckResult, ResearchRecall
from math_research.retrieval.related_research import (
    RelatedResearch,
    memory_document,
    rerank_related_memory,
    retrieve_related_memory,
)
from math_research.retrieval.research_map import ResearchMap, build_research_map
from math_research.retrieval.selection import build_claim_detail

ObjectKind = Literal["claim", "proof", "counterexample", "gap", "evidence", "failed_attempt"]


class SourceReviewFields(TypedDict):
    state: KnowledgeState | None
    source_reported_status: str | None
    human_review: str | None
    source_episode_id: str | None
    summary: str | None


class ProblemOut(BaseModel):
    id: str
    title: str
    primary_claim_id: str | None = None


class ObjectOut(BaseModel):
    state: KnowledgeState | None = None
    id: str
    kind: ObjectKind
    title: str
    status: str
    body: str
    metadata: dict[str, object] = Field(default_factory=dict)
    provenance: list[str] = Field(default_factory=list)
    source_reported_status: str | None = None
    human_review: str | None = None
    source_episode_id: str | None = None
    summary: str | None = None


class ProposalOut(BaseModel):
    state: KnowledgeState | None = None
    candidate: Proposal
    review: ReviewDecision | None = None


class EpisodeOut(BaseModel):
    episode: ResearchEpisode
    raw_markdown: str
    parse_summary: dict[str, int]
    candidate_count: int


class EpisodeListOut(BaseModel):
    episode: ResearchEpisode
    candidate_count: int
    accepted: int
    rejected: int
    deferred: int
    pending: int


class ReviewIn(BaseModel):
    decision: DecisionKind
    edits: dict[str, object] | None = None


class ContinueResearchIn(BaseModel):
    target: ResearchTarget
    purpose: QueryPurpose = "CONTINUE_RESEARCH"
    token_budget: int = Field(default=8000, ge=128, le=200000)
    thread_id: str | None = Field(default=None, min_length=1, max_length=128)
    include_provisional: bool = True
    query: str = Field(default="", max_length=4000)
    related_memory: RelatedResearch | None = None


class BatchReviewItem(ReviewIn):
    candidate_id: str


class BatchReviewIn(BaseModel):
    items: list[BatchReviewItem] = Field(min_length=1, max_length=100)


class BatchReviewResult(BaseModel):
    candidate_id: str
    review: ReviewDecision | None = None
    error: str | None = None


class ScoutIn(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    candidate_ids: list[str] | None = None
    rerun: bool = False


class AdjudicateIn(BaseModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    proposal_ids: list[str] | None = None
    episode_id: str | None = None
    token_budget: int = Field(default=16000, ge=128, le=200000)


class HardJobOut(BaseModel):
    job_id: str
    status: Literal["running", "completed", "failed"]
    result: ScoutRun | list[AdjudicationRun] | None = None
    error: str | None = None


class RerankIn(BaseModel):
    target_id: str = Field(min_length=1)
    query: str | None = None
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    recall_limit: int = Field(default=24, ge=1, le=100)
    expansion_ids: list[str] | None = None


class MemoryJobOut(BaseModel):
    job_id: str
    status: Literal["running", "completed", "failed"]
    result: RelatedResearch | None = None
    error: str | None = None


def _summary(candidates: list[Proposal]) -> dict[str, int]:
    # A saved model proposal is not another deterministic source relation.
    return dict(
        Counter(
            candidate.kind
            for candidate in candidates
            if candidate.semantic_validation_status is None
        )
    )


def _write_header(x_research_ide: Annotated[str | None, Header()] = None) -> None:
    # Cross-site forms cannot set this header; Vite's same-origin proxy can.
    if x_research_ide != "1":
        raise HTTPException(status_code=403, detail="Research IDE mutation header required.")


def create_app(ot_dir: Path) -> FastAPI:
    """Build one local API instance against an existing workspace."""
    if not ot_dir.is_dir():
        raise ResearchError(f"Workspace not found: {ot_dir}")
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research-relations")
    hard_jobs: dict[str, Future[ScoutRun | list[AdjudicationRun]]] = {}
    hard_scopes: dict[tuple[str, str], str] = {}
    soft_jobs: dict[str, Future[RelatedResearch]] = {}
    active_soft_scopes: dict[tuple[str, str], str] = {}
    jobs_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            agent_shutdown()
            critique_shutdown()
            digest_shutdown()
            executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Structured Mathematical Research", version="0.1.0", lifespan=lifespan)
    from math_research.app.api.runs import install_agent_routes

    agent_shutdown = install_agent_routes(app, ot_dir, _write_header)
    from math_research.app.api.assets import install_asset_routes

    install_asset_routes(app, ot_dir)
    from math_research.app.api.critiques import install_critique_routes

    critique_shutdown = install_critique_routes(app, ot_dir, _write_header)
    from math_research.app.api.source_digests import install_source_digest_routes

    digest_shutdown = install_source_digest_routes(app, ot_dir, _write_header)
    from math_research.app.workflows.actions import install_action_routes

    install_action_routes(app, ot_dir, _write_header)
    from math_research.app.model_settings import install_model_settings_routes

    install_model_settings_routes(app, ot_dir, _write_header)
    from math_research.agent.model import ModelConfigurationRequired

    @app.exception_handler(ModelConfigurationRequired)
    async def _handle_missing_model(_request, exc):
        from fastapi.responses import JSONResponse

        role = "research" if str(exc) == "research" else "coordinator"
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "kind": "CONFIG_REQUIRED",
                    "role": role,
                    "message": f"{role} model is not configured. Settings → Models",
                }
            },
        )

    from math_research.app.api.problems import install_problem_routes

    install_problem_routes(app, ot_dir, _write_header)

    @app.exception_handler(ResearchError)
    async def _handle_math_research(_request: object, exc: ResearchError) -> object:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(PermissionError)
    async def _handle_permission(_request: object, _exc: PermissionError) -> object:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=403,
            content={
                "detail": "Workspace access denied. Check local filesystem permissions; "
                "no repair was attempted."
            },
        )

    @app.exception_handler(ValidationError)
    @app.exception_handler(json.JSONDecodeError)
    @app.exception_handler(yaml.YAMLError)
    async def _handle_stored_state(_request: object, _exc: Exception) -> object:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=409,
            content={
                "detail": "Stored state is invalid. Run workspace doctor; no repair was attempted."
            },
        )

    def scoped(problem_id: str) -> None:
        if not any(d.id == problem_id for d in store.list_dossiers(ot_dir)):
            raise HTTPException(status_code=404, detail=f"Problem {problem_id} not found.")

    def episode_for(problem_id: str, episode_id: str) -> ResearchEpisode:
        scoped(problem_id)
        episode = next(
            (item for item in list_episodes(ot_dir, problem_id) if item.episode_id == episode_id),
            None,
        )
        if episode is None:
            raise HTTPException(status_code=404, detail="Episode not found in this Problem.")
        return episode

    @app.get("/api/problems/{problem_id}/relations/policy")
    def hard_policy(problem_id: str) -> AdjudicationPolicy:
        scoped(problem_id)
        return get_policy(ot_dir, problem_id)

    @app.put("/api/problems/{problem_id}/relations/policy", dependencies=[Depends(_write_header)])
    def hard_policy_write(problem_id: str, request: AdjudicationPolicy) -> AdjudicationPolicy:
        scoped(problem_id)
        return set_policy(ot_dir, problem_id, request)

    @app.get("/api/problems/{problem_id}/relations/pool")
    def hard_pool(
        problem_id: str,
        episode_id: str | None = None,
        source_id: str | None = None,
        status: str | None = None,
    ) -> list[PoolItem]:
        scoped(problem_id)
        return list_pool(
            ot_dir, problem_id, episode_id=episode_id, source_id=source_id, status=status
        )

    @app.get("/api/problems/{problem_id}/relations/scout-runs")
    def scout_runs(problem_id: str, episode_id: str | None = None) -> list[ScoutRun]:
        scoped(problem_id)
        return list_scout_runs(ot_dir, problem_id, episode_id)

    @app.get("/api/problems/{problem_id}/relations/adjudication-runs")
    def adjudication_runs(problem_id: str) -> list[AdjudicationRun]:
        scoped(problem_id)
        return list_adjudication_runs(ot_dir, problem_id)

    @app.get("/api/problems/{problem_id}/relations/history")
    def hard_history(problem_id: str, proposal_id: str | None = None) -> list[RelationDecision]:
        scoped(problem_id)
        return decision_history(ot_dir, problem_id, proposal_id)

    @app.post(
        "/api/problems/{problem_id}/relations/{proposal_id}/human",
        dependencies=[Depends(_write_header)],
    )
    def hard_human(
        problem_id: str, proposal_id: str, request: AdjudicationOutput
    ) -> RelationDecision:
        scoped(problem_id)
        return human_adjudicate(ot_dir, problem_id, proposal_id, request)

    @app.post(
        "/api/problems/{problem_id}/episodes/{episode_id}/relations/enroll-explicit",
        dependencies=[Depends(_write_header)],
    )
    def hard_explicit(problem_id: str, episode_id: str) -> list[RelationProposal]:
        episode_for(problem_id, episode_id)
        return enroll_explicit(ot_dir, problem_id, episode_id)

    @app.post(
        "/api/problems/{problem_id}/episodes/{episode_id}/relation-scout",
        dependencies=[Depends(_write_header)],
    )
    def hard_scout(problem_id: str, episode_id: str, request: ScoutIn) -> HardJobOut:
        episode_for(problem_id, episode_id)
        select_scout_candidates(
            ot_dir, problem_id, episode_id, request.candidate_ids, request.rerun
        )
        key = (problem_id, "scout:" + episode_id)
        with jobs_lock:
            previous = hard_scopes.get(key)
            if previous and not hard_jobs[previous].done():
                raise HTTPException(409, "Scout already running in this Episode.")
            job_id = uuid4().hex
            hard_scopes[key] = job_id
            hard_jobs[job_id] = executor.submit(
                scout_episode,
                ot_dir,
                problem_id,
                episode_id,
                provider_name=request.provider,
                model=request.model,
                reasoning_effort=request.reasoning_effort,
                candidate_ids=request.candidate_ids,
                rerun=request.rerun,
            )
        return HardJobOut(job_id=job_id, status="running")

    @app.post(
        "/api/problems/{problem_id}/relations/adjudicate",
        dependencies=[Depends(_write_header)],
    )
    def hard_adjudicate(problem_id: str, request: AdjudicateIn) -> HardJobOut:
        scoped(problem_id)
        if get_policy(ot_dir, problem_id).mode == "HUMAN_ONLY":
            raise ResearchError("Select Model or Human policy before model adjudication.")
        if not select_adjudication_proposals(
            ot_dir, problem_id, request.proposal_ids, request.episode_id
        ):
            raise ResearchError("No pending proposals.")
        key = (problem_id, "adjudication")
        with jobs_lock:
            previous = hard_scopes.get(key)
            if previous and not hard_jobs[previous].done():
                raise HTTPException(409, "Adjudication already running in this Problem.")
            job_id = uuid4().hex
            hard_scopes[key] = job_id
            hard_jobs[job_id] = executor.submit(
                adjudicate_selected,
                ot_dir,
                problem_id,
                proposal_ids=request.proposal_ids,
                episode_id=request.episode_id,
                provider_name=request.provider,
                model=request.model,
                reasoning_effort=request.reasoning_effort,
                token_budget=request.token_budget,
            )
        return HardJobOut(job_id=job_id, status="running")

    @app.get("/api/relation-jobs/{job_id}")
    def hard_job(job_id: str) -> HardJobOut:
        with jobs_lock:
            future = hard_jobs.get(job_id)
        if future is None:
            raise HTTPException(404, "Hard relation job not found.")
        if not future.done():
            return HardJobOut(job_id=job_id, status="running")
        try:
            return HardJobOut(job_id=job_id, status="completed", result=future.result())
        except Exception as exc:
            return HardJobOut(job_id=job_id, status="failed", error=str(exc))

    @app.get("/api/health")
    def health(metadata_only: bool = False) -> dict:
        if metadata_only:
            from math_research.app.api.runs import workspace_identity

            return {
                "status": "ok",
                "workspace_identity": workspace_identity(ot_dir),
                "process_id": os.getpid(),
                "metadata_protocol": 1,
            }
        return {"status": "ok"}

    # Context assembly is read-only; starting research uses Research runs.
    @app.post("/api/problems/{problem_id}/recall/context", response_model=ResearchContextBundle)
    def continue_research(problem_id: str, request: ContinueResearchIn) -> ResearchContextBundle:
        scoped(problem_id)
        if request.target.problem_id != problem_id:
            raise HTTPException(status_code=400, detail="Target differs from Problem scope.")
        return ResearchRecall(ot_dir, problem_id).build_context(
            request.target,
            purpose=request.purpose,
            token_budget=request.token_budget,
            thread_id=request.thread_id,
            include_provisional=request.include_provisional,
            query=request.query,
            related_memory=request.related_memory,
        )

    @app.get("/api/problems/{problem_id}/recall/find-files", response_model=FileSearchResult)
    def navigator_files(
        problem_id: str,
        target_id: str | None = None,
        q: str = "",
        thread_id: str | None = None,
        cross_problem: bool = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> FileSearchResult:
        scoped(problem_id)
        return ResearchRecall(ot_dir, problem_id).find_files(
            target_id,
            query=q,
            thread_id=thread_id,
            cross_problem=cross_problem,
            limit=limit,
        )

    @app.get("/api/problems/{problem_id}/recall/check-history", response_model=HistoryCheckResult)
    def navigator_history(
        problem_id: str,
        target_id: str | None = None,
        q: str = "",
        thread_id: str | None = None,
        cross_problem: bool = False,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
    ) -> HistoryCheckResult:
        scoped(problem_id)
        return ResearchRecall(ot_dir, problem_id).check_history(
            target_id,
            query=q,
            thread_id=thread_id,
            cross_problem=cross_problem,
            limit=limit,
        )

    @app.get("/api/problems/{problem_id}/recall/file")
    def navigator_file(
        problem_id: str, artifact_id: str, kind: str, cross_problem: bool = False
    ) -> Response:
        scoped(problem_id)
        # Resolve by scoped ID/type, never accept a client-provided filesystem path.
        file, content = ResearchRecall(ot_dir, problem_id).read_original_file(
            artifact_id, kind, cross_problem=cross_problem
        )
        assert file.path is not None
        path = Path(file.path)
        return Response(
            content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{artifact_id}{path.suffix}"'},
        )

    @app.post(
        "/api/problems/{problem_id}/reviews/batch",
        response_model=list[BatchReviewResult],
        dependencies=[Depends(_write_header)],
    )
    def batch_review(problem_id: str, request: BatchReviewIn) -> list[BatchReviewResult]:
        scoped(problem_id)
        results = []
        for item in request.items:
            try:
                decision = review_episode_candidate(
                    ot_dir,
                    problem_id,
                    item.candidate_id,
                    item.decision,
                    edits=item.edits,
                )
                results.append(BatchReviewResult(candidate_id=item.candidate_id, review=decision))
            except ResearchError as exc:
                results.append(BatchReviewResult(candidate_id=item.candidate_id, error=str(exc)))
        return results

    @app.get("/api/problems", response_model=list[ProblemOut])
    def problems() -> list[ProblemOut]:
        return [
            ProblemOut(id=d.id, title=d.title, primary_claim_id=d.primary_claim_id)
            for d in store.list_dossiers(ot_dir)
        ]

    @app.get("/api/problems/{problem_id}/research-map", response_model=ResearchMap)
    def research_map(problem_id: str) -> ResearchMap:
        scoped(problem_id)
        from math_research.agent.critique.store import list_runs

        data = build_research_map(ot_dir, problem_id)
        counts = Counter(
            run.target_id for run in list_runs(ot_dir, problem_id) if run.status == "COMPLETED"
        )
        for node in data.nodes:
            node.critique_count = counts[node.id]
        return data

    @app.get("/api/problems/{problem_id}/records", response_model=list[ObjectOut])
    def objects(problem_id: str, kind: ObjectKind) -> list[ObjectOut]:
        scoped(problem_id)
        label = {
            "claim": "Claim",
            "proof": "Proof",
            "counterexample": "Counterexample",
            "gap": "Gap",
            "evidence": "Evidence",
            "failed_attempt": "Failed Attempt",
        }[kind]
        return [
            object_view(problem_id, kind, object_id)
            for object_id, _ in current_object_rows(ot_dir, problem_id, label)
        ]

    def object_view(problem_id: str, kind: ObjectKind, object_id: str) -> ObjectOut:
        scoped(problem_id)
        accepted = next(
            (
                review
                for review in reversed(list_reviews(ot_dir, problem_id))
                if review.decision == "accept"
                and review.mapped_id == object_id
                and review.reviewed_candidate is not None
                and review.reviewed_candidate.kind != "relation"
            ),
            None,
        )
        source_candidate = accepted.reviewed_candidate if accepted is not None else None
        states = KnowledgeStateResolver(ot_dir).resolve(problem_id)
        source_fields: SourceReviewFields = {
            "state": states.get(object_id),
            "source_reported_status": (source_candidate.source_reported_status or None)
            if source_candidate
            else None,
            "human_review": "accepted" if accepted is not None else None,
            "source_episode_id": source_candidate.episode_id if source_candidate else None,
            "summary": source_candidate.summary or None if source_candidate else None,
        }
        if kind in {"claim", "gap"}:
            claim = store.get_claim(ot_dir, problem_id, object_id)
            if claim is None or (kind == "gap") != (claim.type == "OPEN_GAP"):
                raise HTTPException(status_code=404, detail="Claim/Gap not found in this Problem.")
            detail = build_claim_detail(ot_dir, problem_id, object_id)
            neighbor_ids = (
                {p.id for p in detail.proofs}
                | {g.id for g in detail.gaps}
                | {b.id for b in detail.branches}
            )
            return ObjectOut(
                id=claim.id,
                kind=kind,
                title=claim.statement[:120],
                status=claim.status,
                body=claim.statement,
                metadata={
                    **detail.model_dump(mode="json"),
                    "neighbor_states": {
                        ident: states[ident].model_dump(mode="json")
                        for ident in neighbor_ids
                        if ident in states
                    },
                },
                provenance=[*claim.source_artifacts, claim.notes],
                **source_fields,
            )
        if kind == "proof":
            proof = next(
                (p for p in store.list_proof_attempts(ot_dir, problem_id) if p.id == object_id),
                None,
            )
            if proof is None:
                raise HTTPException(status_code=404, detail="Proof not found in this Problem.")
            body, path = read_full_proof(ot_dir, problem_id, object_id)
            return ObjectOut(
                id=proof.id,
                kind=kind,
                title=proof.title,
                status=proof.status,
                body=body,
                metadata=proof.model_dump(mode="json"),
                provenance=[str(path), *proof.claim_links],
                **source_fields,
            )
        if kind == "counterexample":
            from math_research.memory.records.counterexamples import (
                get_counterexample,
                read_counterexample,
            )

            record = get_counterexample(ot_dir, problem_id, object_id)
            if record is None:
                raise HTTPException(
                    status_code=404, detail="Counterexample not found in this Problem."
                )
            body, path = read_counterexample(ot_dir, record)
            relations = [
                r.model_dump(mode="json") | {"confirmation_label": r.label}
                for r in active_relations(ot_dir, problem_id)
                if r.source_id == object_id
            ]
            return ObjectOut(
                id=record.id,
                kind=kind,
                title=record.title or record.id,
                status=record.status,
                body=body,
                metadata={**record.model_dump(mode="json"), "relations": relations},
                provenance=[str(path), *record.source_artifacts],
                **source_fields,
            )
        if kind == "evidence":
            evidence = next(
                (item for item in store.list_evidence(ot_dir, problem_id) if item.id == object_id),
                None,
            )
            if evidence is None:
                raise HTTPException(status_code=404, detail="Evidence not found in this Problem.")
            return ObjectOut(
                id=evidence.id,
                kind=kind,
                title=evidence.summary[:120],
                status="recorded",
                body=render_evidence(evidence),
                metadata=evidence.model_dump(mode="json"),
                provenance=evidence.source_artifacts,
                **source_fields,
            )
        failed = next(
            (
                item
                for item in store.list_failed_attempts(ot_dir, problem_id)
                if item.id == object_id
            ),
            None,
        )
        if failed is None:
            raise HTTPException(status_code=404, detail="Failed Attempt not found in this Problem.")
        return ObjectOut(
            id=failed.id,
            kind=kind,
            title=failed.attempted_method,
            status="failed_route",
            body=failed.summary + "\n\n" + failed.reason_failed,
            metadata=failed.model_dump(mode="json"),
            provenance=failed.artifacts,
            **source_fields,
        )

    @app.get("/api/problems/{problem_id}/records/{kind}/{object_id}", response_model=ObjectOut)
    def get_object(problem_id: str, kind: ObjectKind, object_id: str) -> ObjectOut:
        return object_view(problem_id, kind, object_id)

    @app.get("/api/problems/{problem_id}/episodes", response_model=list[EpisodeListOut])
    def episodes(problem_id: str) -> list[EpisodeListOut]:
        scoped(problem_id)
        return [EpisodeListOut(**row.__dict__) for row in recent_episodes(ot_dir, problem_id)]

    @app.get("/api/problems/{problem_id}/episodes/{episode_id}", response_model=EpisodeOut)
    def get_episode(problem_id: str, episode_id: str) -> EpisodeOut:
        episode = episode_for(problem_id, episode_id)
        rows = candidates_with_reviews(ot_dir, problem_id, episode_id)
        return EpisodeOut(
            episode=episode,
            raw_markdown=episode_source(ot_dir, problem_id, episode_id),
            parse_summary=_summary([row.candidate for row in rows]),
            candidate_count=len(rows),
        )

    @app.get(
        "/api/problems/{problem_id}/episodes/{episode_id}/proposals",
        response_model=list[ProposalOut],
    )
    def candidates(problem_id: str, episode_id: str) -> list[ProposalOut]:
        episode_for(problem_id, episode_id)
        states = KnowledgeStateResolver(ot_dir).resolve(problem_id)
        return [
            ProposalOut(
                candidate=row.candidate,
                review=row.review,
                state=states.get(row.candidate.candidate_id),
            )
            for row in candidates_with_reviews(ot_dir, problem_id, episode_id)
        ]

    @app.post(
        "/api/problems/{problem_id}/reviews/{candidate_id}",
        response_model=ReviewDecision,
        dependencies=[Depends(_write_header)],
    )
    def review(problem_id: str, candidate_id: str, request: ReviewIn) -> ReviewDecision:
        scoped(problem_id)
        return review_episode_candidate(
            ot_dir, problem_id, candidate_id, request.decision, edits=request.edits
        )

    @app.get("/api/problems/{problem_id}/recall/related", response_model=RelatedResearch)
    def related_memory(
        problem_id: str,
        target_id: str,
        q: str | None = None,
        recall_limit: Annotated[int, Query(ge=1, le=100)] = 24,
    ) -> RelatedResearch:
        scoped(problem_id)
        return retrieve_related_memory(
            ot_dir, problem_id, target_id, query=q, recall_limit=recall_limit
        )

    @app.get("/api/problems/{problem_id}/recall/record/{object_id}", response_model=IndexDoc)
    def get_memory_object(problem_id: str, object_id: str, object_type: str) -> IndexDoc:
        scoped(problem_id)
        return memory_document(ot_dir, problem_id, object_type, object_id)

    @app.post(
        "/api/problems/{problem_id}/recall/related/rerank",
        response_model=MemoryJobOut,
        dependencies=[Depends(_write_header)],
    )
    def rerank(problem_id: str, request: RerankIn) -> MemoryJobOut:
        scoped(problem_id)
        retrieve_related_memory(
            ot_dir,
            problem_id,
            request.target_id,
            query=request.query,
            recall_limit=request.recall_limit,
            expansion_ids=request.expansion_ids,
        )
        with jobs_lock:
            scope_key = (problem_id, request.target_id)
            previous = active_soft_scopes.get(scope_key)
            if previous is not None and not soft_jobs[previous].done():
                raise HTTPException(
                    status_code=409, detail="This memory rerank is already running."
                )
            job_id = uuid4().hex
            soft_jobs[job_id] = executor.submit(
                rerank_related_memory,
                ot_dir,
                problem_id,
                request.target_id,
                query=request.query,
                provider_name=request.provider,
                model=request.model,
                reasoning_effort=request.reasoning_effort,
                recall_limit=request.recall_limit,
                expansion_ids=request.expansion_ids,
            )
            active_soft_scopes[scope_key] = job_id
        return MemoryJobOut(job_id=job_id, status="running")

    @app.get("/api/recall-jobs/{job_id}", response_model=MemoryJobOut)
    def memory_job(job_id: str) -> MemoryJobOut:
        with jobs_lock:
            future = soft_jobs.get(job_id)
        if future is None:
            raise HTTPException(status_code=404, detail="Memory rerank job not found.")
        if not future.done():
            return MemoryJobOut(job_id=job_id, status="running")
        try:
            return MemoryJobOut(job_id=job_id, status="completed", result=future.result())
        except Exception as exc:  # noqa: BLE001 - read-only model job diagnostics
            return MemoryJobOut(job_id=job_id, status="failed", error=str(exc))

    from fastapi.staticfiles import StaticFiles

    frontend = Path(__file__).resolve().parents[1] / "static"
    if not (frontend / "index.html").is_file():
        frontend = Path(__file__).resolve().parents[4] / "web" / "dist"
    if (frontend / "index.html").is_file():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="web-app")
    return app
