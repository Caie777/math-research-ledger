"""Two-stage relation workflow records, never mathematical object acceptance."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from math_research.agent.providers.base import TokenUsage
from math_research.memory.records.models import utcnow

AdjudicationChoice = Literal["CONFIRM", "REJECT", "UNCERTAIN", "CORRECT"]


class AdjudicationPolicy(BaseModel):
    mode: Literal["HUMAN_ONLY", "MODEL_OR_HUMAN"] = "HUMAN_ONLY"
    require_human_for_state_changing: bool = True


class RelationProposal(BaseModel):
    proposal_id: str
    problem_id: str
    episode_id: str
    source_candidate_id: str
    proposed_relation: str
    target_id: str
    confidence: float = Field(ge=0, le=1)
    rationale: str
    origin: Literal["model_scout", "episode_explicit"]
    scout_provider: str | None = None
    scout_model: str | None = None
    scout_reasoning_effort: str | None = None
    scout_run_id: str | None = None
    validator_status: Literal["SCOUT_CANDIDATE", "EPISODE_EXPLICIT"]
    allowed_target_ids: list[str] = Field(default_factory=list)
    explicit_candidate_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    status: Literal["pending_adjudication"] = "pending_adjudication"


class AdjudicationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: AdjudicationChoice
    rationale: str = Field(min_length=1, max_length=6000)
    corrected_relation: str | None = None
    corrected_target_id: str | None = None


class RelationDecision(BaseModel):
    decision_id: str
    proposal_id: str
    problem_id: str
    decision: AdjudicationChoice
    confirmed_by: Literal["human", "model"]
    rationale: str
    corrected_relation: str | None = None
    corrected_target_id: str | None = None
    provider: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None
    adjudication_run_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    source_sha256: str | None = None
    target_sha256: str | None = None


class PoolItem(RelationProposal):
    current_status: str = "pending_adjudication"
    confirmation: Literal["HUMAN_CONFIRMED", "MODEL_CONFIRMED"] | None = None
    confirmed_by: Literal["human", "model"] | None = None
    active: bool = False
    source_id: str | None = None
    effective_relation: str | None = None
    effective_target_id: str | None = None
    latest_decision: RelationDecision | None = None
    scout_run_ids: list[str] = Field(default_factory=list)
    inactive_reason: str | None = None


class ConfirmedRelation(BaseModel):
    """Read-only operational projection; never a Human ReviewDecision imitation."""

    decision_id: str
    proposal_id: str | None = None
    episode_id: str
    source_id: str
    target_id: str
    relation: str
    confirmed_by: Literal["human", "model"]
    provider: str | None = None
    model: str | None = None
    reasoning_effort: str | None = None

    @property
    def label(self) -> str:
        if self.confirmed_by == "human":
            return "confirmed: human"
        return (
            f"confirmed: model · {self.model or 'unknown'} · {self.reasoning_effort or 'default'}"
        )


class ScoutResult(BaseModel):
    source_candidate_id: str
    proposed_relation: str
    target_id: str | None
    confidence: float
    rationale: str
    validator_status: str
    validator_reason: str
    proposal_id: str | None = None


class ScoutRun(BaseModel):
    run_id: str
    problem_id: str
    episode_id: str
    created_at: datetime = Field(default_factory=utcnow)
    provider: str
    requested_model: str
    actual_models: list[str] = Field(default_factory=list)
    reasoning_effort: str | None = None
    status: Literal["completed", "partial", "failed"] = "completed"
    results: list[ScoutResult] = Field(default_factory=list)
    raw_responses: list[str] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    usage: TokenUsage | None = None
    elapsed_seconds: float = 0


class AdjudicationRun(BaseModel):
    run_id: str
    problem_id: str
    proposal_id: str
    created_at: datetime = Field(default_factory=utcnow)
    provider: str
    requested_model: str
    actual_models: list[str] = Field(default_factory=list)
    reasoning_effort: str | None = None
    status: Literal["completed", "failed"]
    input_context: str
    context_token_estimate: int
    token_budget: int
    raw_response: str = ""
    error: str | None = None
    decision_id: str | None = None
    usage: TokenUsage | None = None
    elapsed_seconds: float = 0
