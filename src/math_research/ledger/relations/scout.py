"""Stage 1 only: model recall proposals into a persistent, non-authoritative pool."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from uuid import uuid4

from math_research.agent.model import SemanticModel
from math_research.agent.providers.base import BaseProvider, TokenUsage
from math_research.agent.session import SessionMessage
from math_research.agent.transport import CodexCLIExecutor
from math_research.core.errors import ResearchError
from math_research.ledger.archive import source_path
from math_research.ledger.episodes import Proposal, list_candidates, list_episodes
from math_research.ledger.records.write_boundary import automated_research
from math_research.ledger.relations.ledger import (
    add_proposal,
    append_workflow,
    canonical_ids,
    list_scout_runs,
)
from math_research.ledger.relations.models import RelationProposal, ScoutResult, ScoutRun
from math_research.ledger.relations.suggestions import (
    SEMANTIC_BATCH_SCHEMA,
    _validate_proposals,
    retrieve_history,
)

SCOUT_PROMPT = (
    "You are Relation Scout. Return one proposal per source in the JSON schema. "
    "Use only its allowed_existing_object_ids. Propose only a clear logical hard relation; "
    "topic, common 1/6 bounds, methods and similar parameters are soft relevance only. "
    "Return NO_HARD_RELATION or UNCERTAIN when appropriate. Qualification is SCOUT_CANDIDATE, "
    "never confirmation, Human Acceptance or theorem verification. Finite Evidence cannot PROVES "
    "a universal statement. REFUTES attacks a Statement; INVALIDATES attacks Proof/Approach."
)


def select_scout_candidates(
    ot_dir: Path,
    pid: str,
    episode_id: str,
    candidate_ids: list[str] | None = None,
    rerun: bool = False,
) -> list[Proposal]:
    candidates = list_candidates(ot_dir, pid, episode_id)
    objects = {c.candidate_id: c for c in candidates if c.kind != "relation"}
    if candidate_ids is not None:
        if (
            not candidate_ids
            or len(set(candidate_ids)) != len(candidate_ids)
            or not set(candidate_ids) <= objects.keys()
        ):
            raise ResearchError(
                "Select unique object Proposal IDs from this Episode; explicit relations excluded."
            )
        candidates = [objects[i] for i in candidate_ids]
    else:
        candidates = list(objects.values())
    if not rerun:
        done = {
            x.source_candidate_id
            for r in list_scout_runs(ot_dir, pid, episode_id)
            for x in r.results
            if x.validator_status in {"SCOUT_CANDIDATE", "no_hard_relation", "uncertain"}
        }
        candidates = [c for c in candidates if c.candidate_id not in done]
    if not candidates:
        raise ResearchError("No unresolved Scout candidates; explicitly rerun a selection.")
    return candidates


@automated_research
def scout_episode(
    ot_dir: Path,
    pid: str,
    episode_id: str,
    *,
    provider: BaseProvider | None = None,
    provider_name: str | None = None,
    model: str | None = None,
    reasoning_effort: str | None = None,
    candidate_ids: list[str] | None = None,
    rerun: bool = False,
    codex_executor: CodexCLIExecutor | None = None,
    batch_size: int = 8,
) -> ScoutRun:
    episode = next((e for e in list_episodes(ot_dir, pid) if e.episode_id == episode_id), None)
    if episode is None:
        raise ResearchError("Episode unavailable in this Problem.")
    path = source_path(ot_dir, episode.archive_path)
    if (
        not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != episode.content_sha256
    ):
        raise ResearchError("Archived Episode changed; Scout refused.")
    if not 1 <= batch_size <= 30:
        raise ResearchError("Scout batch size must be 1..30.")
    candidates = select_scout_candidates(ot_dir, pid, episode_id, candidate_ids, rerun)
    transport = SemanticModel(
        ot_dir,
        provider=provider,
        provider_name=provider_name,
        model=model,
        reasoning_effort=reasoning_effort,
        codex_executor=codex_executor,
    )
    run = ScoutRun(
        run_id="SCOUT-" + uuid4().hex,
        problem_id=pid,
        episode_id=episode_id,
        provider=transport.name,
        requested_model=transport.requested_model,
        reasoning_effort=reasoning_effort,
    )
    start = time.monotonic()
    ids = canonical_ids(ot_dir, pid)
    usage = TokenUsage()
    for offset in range(0, len(candidates), batch_size):
        batch = candidates[offset : offset + batch_size]
        recall = {
            c.candidate_id: [
                h for h in retrieve_history(ot_dir, c, limit=12) if h.object_id in ids
            ][:4]
            for c in batch
        }
        allowed = {key: {h.object_id for h in hits} for key, hits in recall.items()}
        payload = [
            {
                "candidate_id": c.candidate_id,
                "kind": c.kind,
                "body": c.body,
                "conditions_and_provenance": c.model_dump(mode="json"),
                "historical_candidates": [h.model_dump() for h in recall[c.candidate_id]],
                "allowed_existing_object_ids": sorted(allowed[c.candidate_id]),
            }
            for c in batch
        ]
        try:
            response = transport.generate(
                [
                    SessionMessage(role="system", content=SCOUT_PROMPT),
                    SessionMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
                ],
                SEMANTIC_BATCH_SCHEMA,
            )
            run.raw_responses.append(response.content)
            if response.usage:
                usage.prompt_tokens += response.usage.prompt_tokens
                usage.completion_tokens += response.usage.completion_tokens
                usage.thinking_tokens += response.usage.thinking_tokens
                run.usage = usage
            if response.kind != "message" or response.truncated:
                raise ResearchError("Scout output was truncated or a tool call.")
            items, issues = _validate_proposals(response.content, batch, allowed, ids)
            run.diagnostics.extend(i.model_dump_json() for i in issues)
            for item in items:
                result = ScoutResult(
                    source_candidate_id=item.candidate_id,
                    proposed_relation=item.proposed_relation,
                    target_id=item.target_existing_object,
                    confidence=item.confidence,
                    rationale=item.short_rationale,
                    validator_status=item.validation_status,
                    validator_reason=item.validation_reason,
                )
                if (
                    item.validation_status == "accepted_by_validator"
                    and item.target_existing_object
                ):
                    try:
                        proposal = add_proposal(
                            ot_dir,
                            RelationProposal(
                                proposal_id="",
                                problem_id=pid,
                                episode_id=episode_id,
                                source_candidate_id=item.candidate_id,
                                proposed_relation=item.proposed_relation,
                                target_id=item.target_existing_object,
                                confidence=item.confidence,
                                rationale=item.short_rationale,
                                origin="model_scout",
                                scout_provider=transport.name,
                                scout_model=transport.actual_models[-1],
                                scout_reasoning_effort=transport.actual_effort,
                                scout_run_id=run.run_id,
                                validator_status="SCOUT_CANDIDATE",
                                allowed_target_ids=sorted(allowed[item.candidate_id]),
                            ),
                        )
                        result.proposal_id = proposal.proposal_id
                        result.validator_status = "SCOUT_CANDIDATE"
                        result.validator_reason = (
                            "Validator-qualified scout candidate; awaiting adjudication."
                        )
                    except ResearchError as exc:
                        result.validator_status = "invalid"
                        result.validator_reason = str(exc)
                run.results.append(result)
        except ResearchError as exc:
            run.diagnostics.append(str(exc))
    run.actual_models = transport.actual_models
    run.reasoning_effort = transport.actual_effort
    run.elapsed_seconds = time.monotonic() - start
    if run.diagnostics or any(
        r.validator_status in {"invalid", "out_of_scope_target"} for r in run.results
    ):
        run.status = "partial" if run.results else "failed"
    append_workflow(ot_dir, pid, "scout_runs.jsonl", run)
    return run
