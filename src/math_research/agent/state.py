"""Operational metadata for one bounded research run; mathematics stays in Episode V4."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from math_research.ledger.target import ResearchTarget

StopReason = Literal[
    "COMPLETED", "BUDGET_EXHAUSTED", "USER_STOP", "TOOL_FAILURE", "MODEL_FAILURE", "NO_PROGRESS"
]


class AgentBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_agent_steps: int = Field(default=64, ge=1, le=1000)
    max_model_calls: int = Field(default=64, ge=1, le=1000)
    max_context_tokens: int = Field(default=128000, ge=2048, le=200000)
    max_tool_calls: int = Field(default=128, ge=0, le=1000)
    max_web_calls: int = Field(default=24, ge=0, le=100)
    max_python_calls: int = Field(default=64, ge=0, le=1000)
    max_wall_time: int = Field(default=14400, ge=5, le=14400)
    checkpoint_seconds: int = Field(default=60, ge=1, le=300)
    no_progress_steps: int = Field(default=3, ge=1, le=100)


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: ResearchTarget
    task: str = Field(default="", max_length=8000)
    provider: str = "codex"
    model: str | None = "gpt-6.1-sol"
    effort: str | None = "high"
    tool_policy: Literal["research_standard"] = "research_standard"
    context_tokens: int = Field(default=30000, ge=128, le=200000)
    include_provisional: bool = True
    thread_id: str | None = None
    budget: AgentBudget = Field(default_factory=AgentBudget)
    checkpoint_every_effective_steps: int = Field(default=3, ge=1, le=100)


class AgentRun(BaseModel):
    run_id: str
    request: AgentRequest
    status: Literal["running", "finished"] = "running"
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    stop_reason: StopReason | None = None
    context_version: str = ""
    steps: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    consecutive_tool_failures: int = Field(default=0, ge=0)
    web_calls: int = 0
    python_calls: int = 0
    usage: dict = Field(default_factory=dict)
    current_action: str = "context"
    artifacts: list[str] = Field(default_factory=list)
    checkpoint_path: str | None = None
    episode_id: str | None = None
    candidate_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    availability: dict[str, str] = Field(default_factory=dict)
    executor_attached: bool | None = None
    effective_steps: int = 0
    latest_checkpoint: str | None = None
    last_checkpoint_step: int = 0
    uncheckpointed_public_events: int = 0
    resume_available: bool = False
    resume_unavailable_reason: str | None = None
    attempt: int = 0
    active_seconds: float = 0
    pending_wall_seconds: float = 0
    episode_history: list[str] = Field(default_factory=list)
    research_decisions: int = 0
    last_reflection_decision: int = 0


class ResearchStop(RuntimeError):
    def __init__(self, reason: StopReason):
        self.reason = reason
        super().__init__(reason)
