"""Strict bounded advisory source schemas, separate from mathematical authority."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from math_research.agent.critique.models import CritiqueSettings
from math_research.ledger.episodes import RelationKind


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DigestSettings(CritiqueSettings):
    """Existing provider capabilities with independent digest settings."""

    model: str = Field(default="gpt-6.1-sol", pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
    max_chunks: int = Field(default=4, ge=1, le=4)


class Locator(Strict):
    page: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    line_start: int | None = Field(default=None, ge=1)
    line_end: int | None = Field(default=None, ge=1)
    heading: str | None = Field(default=None, max_length=200)


class SourceChunk(Strict):
    chunk_id: str
    page: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    text: str
    truncated: bool = False


class SourceDigestContext(Strict):
    problem_id: str
    problem_statement: str
    primary_target_id: str | None
    primary_target_statement: str
    accepted_terminology: list[dict[str, str]]
    source_id: str
    source_filename: str
    source_sha256: str
    format: Literal["PDF", "MARKDOWN", "TXT"]
    total_units: int
    unit: Literal["page", "line"]
    chunks: list[SourceChunk]
    limitations: list[str]


class StructureOutput(Strict):
    summary: str = Field(max_length=4000)
    relevant_chunk_ids: list[str] = Field(max_length=4)


class ExtractedProposal(Strict):
    proposal_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    proposal_type: Literal[
        "claim", "evidence", "gap", "counterexample", "failed_attempt", "relation"
    ]
    title: str = Field(min_length=1, max_length=300)
    statement: str = Field(min_length=1, max_length=10000)
    locator: Locator | None = None
    supporting_span: str = Field(default="", max_length=350)
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    relation_to_problem: Literal["DIRECT", "SUPPORTING", "BACKGROUND", "POSSIBLE"]
    citation_kind: Literal["SOURCE_PRIMARY", "SOURCE_CITES_EXTERNAL"]
    target_id: str | None = Field(default=None, max_length=128)
    source_candidate_id: str | None = Field(default=None, max_length=128)
    relation: RelationKind | None = None
    notes: str = Field(default="", max_length=3000)


class ExtractionOutput(Strict):
    summary: str = Field(max_length=4000)
    notation: list[str] = Field(max_length=30)
    definitions: list[str] = Field(max_length=30)
    results: list[str] = Field(max_length=30)
    methods: list[str] = Field(max_length=30)
    assumptions: list[str] = Field(max_length=30)
    limitations: list[str] = Field(max_length=30)
    # Individual validation quarantines a malformed item without discarding valid neighbors.
    proposals: list[dict] = Field(max_length=40)


class Support(Strict):
    locator: Locator | None
    supporting_span: str


class LocationConfirmation(Strict):
    proposal_id: str
    locator: Locator
    supporting_span: str = Field(min_length=1, max_length=350)
    confirmed_at: datetime


class SourceProposal(ExtractedProposal):
    proposal_id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,127}$")
    source_id: str
    source_filename: str
    digest_id: str
    candidate_id: str
    provenance_status: Literal["VALID", "PROVENANCE_INCOMPLETE", "INVALID"]
    possible_duplicate_ids: list[str] = Field(default_factory=list)
    additional_support: list[Support] = Field(default_factory=list)
    review_decision: str | None = None
    mapped_id: str | None = None


class SourceDigest(Strict):
    digest_id: str
    source_id: str
    source_filename: str
    source_sha256: str
    problem_id: str
    created_at: datetime
    model: str
    reasoning_effort: str | None
    summary: str
    notation: list[str]
    definitions: list[str]
    results: list[str]
    methods: list[str]
    assumptions: list[str]
    limitations: list[str]
    proposals: list[SourceProposal]
    coverage_complete: bool
    processed_ranges: list[Locator]
    omitted_ranges: list[Locator]
    validation_warnings: list[str]
    authority: Literal["ADVISORY"] = "ADVISORY"


class DigestRun(Strict):
    digest_id: str
    problem_id: str
    source_id: str
    source_sha256: str
    created_at: datetime
    settings: DigestSettings
    context_sha256: str
    session_id: str
    status: Literal["RUNNING", "COMPLETED", "PARTIAL", "FAILED"] = "RUNNING"
    digest: SourceDigest | None = None
    error: str | None = None
    source_changed: bool = False
    authority: Literal["ADVISORY"] = "ADVISORY"
