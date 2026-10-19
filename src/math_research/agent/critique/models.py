"""Bounded critique input, output and advisory provenance schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TargetType = Literal["claim", "proof", "counterexample", "evidence"]
Verdict = Literal["NO_CLEAR_ISSUE", "ISSUE_FOUND", "INCONCLUSIVE"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextItem(StrictModel):
    record_id: str
    record_type: str
    authority: str
    status: str
    reason_included: str
    content: str
    sha256: str


class CritiqueBundle(StrictModel):
    problem_id: str
    target: ContextItem
    problem: ContextItem
    context: list[ContextItem]
    relations: list[ContextItem]
    limitations: list[str]
    continuation_target_id: str | None = None
    computation_available: Literal[False] = False


class CritiqueIssue(StrictModel):
    issue_id: str = Field(min_length=1, max_length=128)
    category: Literal[
        "LOGICAL_GAP",
        "MISSING_ASSUMPTION",
        "QUANTIFIER_MISMATCH",
        "CIRCULAR_REASONING",
        "CASE_SPLIT",
        "BOUNDARY_CASE",
        "DOMAIN_SCOPE",
        "ALGEBRA",
        "EVIDENCE_AS_PROOF",
        "COUNTEREXAMPLE_WITNESS",
        "DEPENDENCY_SCOPE",
        "AMBIGUITY",
    ]
    severity: Literal["CRITICAL", "MAJOR", "MINOR", "NOTE"]
    location: str = Field(min_length=1, max_length=2000)
    explanation: str = Field(min_length=1, max_length=10000)
    mathematical_consequence: str = Field(min_length=1, max_length=5000)
    suggested_check: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def located_issue(self) -> CritiqueIssue:
        for field in (
            self.issue_id,
            self.location,
            self.explanation,
            self.mathematical_consequence,
            self.suggested_check,
        ):
            if not field.strip():
                raise ValueError("Critique issues require nonblank mathematical details.")
        return self


class CritiqueOutput(StrictModel):
    verdict: Verdict
    summary: str = Field(min_length=1, max_length=10000)
    issues: list[CritiqueIssue] = Field(max_length=40)
    suggested_checks: list[str] = Field(max_length=40)
    limitations: list[str] = Field(max_length=40)
    requires_computation: bool

    @model_validator(mode="after")
    def valid_verdict(self) -> CritiqueOutput:
        if not self.summary.strip():
            raise ValueError("Critique summary must not be blank.")
        serious = any(issue.severity in {"CRITICAL", "MAJOR"} for issue in self.issues)
        if self.verdict == "ISSUE_FOUND" and not serious:
            raise ValueError("ISSUE_FOUND requires a located CRITICAL or MAJOR issue.")
        if self.verdict == "NO_CLEAR_ISSUE" and serious:
            raise ValueError("NO_CLEAR_ISSUE cannot contain a CRITICAL or MAJOR issue.")
        if len({issue.issue_id for issue in self.issues}) != len(self.issues):
            raise ValueError("Issue IDs must be unique within one report.")
        return self


class CritiqueSettings(StrictModel):
    provider: Literal["codex", "openai", "anthropic", "ollama", "mistral"] = "codex"
    model: str = Field(default="gpt-6.1-sol", pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "high"

    @model_validator(mode="after")
    def compatible_effort(self) -> CritiqueSettings:
        if self.provider not in {"codex", "openai"} and self.reasoning_effort is not None:
            raise ValueError("Select provider-default reasoning for this provider.")
        if self.provider == "openai" and self.reasoning_effort in {"xhigh", "max"}:
            raise ValueError("The existing OpenAI transport supports low/medium/high.")
        return self


class CritiqueReport(CritiqueOutput):
    limitations: list[str] = Field(max_length=100)
    critique_id: str
    target_id: str
    target_type: TargetType
    created_at: datetime
    provider: str
    model: str
    reasoning_effort: str | None
    context_manifest: list[ContextItem]
    bundle_sha256: str
    session_id: str
    authority: Literal["ADVISORY"] = "ADVISORY"


class CritiqueRun(StrictModel):
    critique_id: str
    problem_id: str
    target_id: str
    target_type: TargetType
    created_at: datetime
    settings: CritiqueSettings
    bundle_sha256: str
    session_id: str
    continuation_target_id: str | None
    status: Literal["RUNNING", "COMPLETED", "FAILED"] = "RUNNING"
    report: CritiqueReport | None = None
    error: str | None = None
    authority: Literal["ADVISORY"] = "ADVISORY"
