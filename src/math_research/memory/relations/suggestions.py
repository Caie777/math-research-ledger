"""Scoped prior-research recall and batch Logical Relation proposals."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from math_research.core.errors import ResearchError
from math_research.memory.episodes import Proposal
from math_research.memory.relations.policy import HARD_CONFIDENCE_THRESHOLD, LOGICAL_RELATIONS
from math_research.retrieval.index import IndexDoc, gather_documents, search_documents

SemanticRelation = Literal[
    "NEW",
    "SAME_AS",
    "REVISES",
    "SUPERSEDES",
    "STRENGTHENS",
    "WEAKENS",
    "SPECIAL_CASE_OF",
    "GENERALIZES",
    "USES",
    "DEPENDS_ON",
    "REFUTES",
    "INVALIDATES",
    "RELATED_TO",
    "NO_LINK",
    "PROVES",
    "NO_HARD_RELATION",
    "UNCERTAIN",
]

ValidationStatus = Literal[
    "legacy",
    "accepted_by_validator",
    "no_hard_relation",
    "uncertain",
    "out_of_scope_target",
    "invalid",
]


class HistoricalHit(BaseModel):
    object_id: str
    object_type: str
    title: str
    excerpt: str
    score: float
    basis: Literal["textual"] = "textual"
    record_status: str | None = None
    caveats: list[str] = Field(default_factory=list)


class SemanticProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    candidate_id: str
    proposed_relation: SemanticRelation
    target_existing_object: str | None
    confidence: float = Field(ge=0, le=1)
    short_rationale: str = Field(min_length=1, max_length=1200)
    validation_status: ValidationStatus = "legacy"
    validation_reason: str = ""
    relation_candidate_id: str | None = None


class _BatchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    proposals: list[object]


class ProposalDiagnostic(BaseModel):
    candidate_id: str | None = None
    validation_status: Literal["invalid", "missing", "batch_error"]
    reason: str
    raw_proposal: object = None


_PROPOSAL_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "candidate_id": {"type": "string"},
        "proposed_relation": {
            "type": "string",
            "enum": sorted(LOGICAL_RELATIONS | {"NO_HARD_RELATION", "UNCERTAIN"}),
        },
        "target_existing_object": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "short_rationale": {"type": "string"},
    },
    "required": [
        "candidate_id",
        "proposed_relation",
        "target_existing_object",
        "confidence",
        "short_rationale",
    ],
}
SEMANTIC_BATCH_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"proposals": {"type": "array", "items": _PROPOSAL_SCHEMA}},
    "required": ["proposals"],
}


def _validate_proposals(
    raw: str,
    batch: list[Proposal],
    allowed: dict[str, set[str]],
    scoped_objects: set[str],
) -> tuple[list[SemanticProposal], list[ProposalDiagnostic]]:
    """Keep each item for diagnosis; only qualified hard items can be staged."""
    parsed = _parse_response(raw)
    valid: list[SemanticProposal] = []
    diagnostics: list[ProposalDiagnostic] = []
    for value in parsed.proposals:
        try:
            # Validation metadata is generated locally, never accepted from the model.
            if isinstance(value, dict) and set(value) - {
                "candidate_id",
                "proposed_relation",
                "target_existing_object",
                "confidence",
                "short_rationale",
            }:
                raise ValueError("Unexpected model fields.")
            item = SemanticProposal.model_validate(value)
        except (ValidationError, ValueError) as exc:
            candidate_id = value.get("candidate_id") if isinstance(value, dict) else None
            diagnostics.append(
                ProposalDiagnostic(
                    candidate_id=candidate_id if isinstance(candidate_id, str) else None,
                    validation_status="invalid",
                    reason=str(exc),
                    raw_proposal=value,
                )
            )
            continue
        valid.append(item)
    counts: dict[str, int] = {}
    for item in valid:
        counts[item.candidate_id] = counts.get(item.candidate_id, 0) + 1
    for item in valid:
        if item.candidate_id not in allowed or counts[item.candidate_id] > 1:
            item.validation_status = "invalid"
            item.validation_reason = "Unknown or duplicated source candidate ID."
        elif item.proposed_relation in {"NEW", "NO_LINK", "NO_HARD_RELATION", "RELATED_TO"}:
            item.validation_status = "no_hard_relation"
            item.validation_reason = "No hard edge; relevance belongs to query-time retrieval."
        elif item.proposed_relation == "UNCERTAIN":
            item.validation_status = "uncertain"
            item.validation_reason = "Model reported uncertainty; no hard candidate staged."
        elif (
            item.target_existing_object not in allowed[item.candidate_id]
            or item.target_existing_object not in scoped_objects
        ):
            item.validation_status = "out_of_scope_target"
            item.validation_reason = "Target not in this candidate's scoped historical recall."
        elif item.confidence < HARD_CONFIDENCE_THRESHOLD:
            item.validation_status = "uncertain"
            item.validation_reason = (
                f"Hard proposal confidence is below {HARD_CONFIDENCE_THRESHOLD}."
            )
        else:
            item.validation_status = "accepted_by_validator"
            item.validation_reason = "Scoped high-confidence proposal; human review still required."
    for candidate in batch:
        if candidate.candidate_id not in counts:
            diagnostics.append(
                ProposalDiagnostic(
                    candidate_id=candidate.candidate_id,
                    validation_status="missing",
                    reason="No schema-valid proposal for this candidate.",
                )
            )
    return valid, diagnostics


def retrieve_history(
    ot_dir: Path,
    candidate: Proposal,
    *,
    limit: int = 4,
    documents: list[IndexDoc] | None = None,
) -> list[HistoricalHit]:
    """Textual recall is not a logical edge. Never include the source Episode itself."""
    query = (
        candidate.source_fields.get("旧对象")
        or candidate.source_fields.get("阻碍对象")
        or candidate.source_fields.get("针对对象")
        or candidate.summary
        or candidate.body[:500]
        or candidate.title
    )
    scoped_docs = (
        gather_documents(ot_dir, problem_id=candidate.problem_id)
        if documents is None
        else [doc for doc in documents if doc.problem_id == candidate.problem_id]
    )
    docs = search_documents(scoped_docs, query, k=max(limit * 12, 50))
    return [
        HistoricalHit(
            object_id=doc.artifact_id,
            object_type=doc.artifact_type,
            title=doc.title[:160],
            excerpt=doc.text[:700],
            score=score,
            record_status=doc.record_status,
            caveats=doc.caveats,
        )
        for doc, score in docs
        if doc.artifact_type.startswith("dossier:")
        and doc.artifact_id != candidate.episode_id
        and not doc.artifact_type.endswith(":episode")
    ][:limit]


def _parse_response(raw: str) -> _BatchOutput:
    try:
        return _BatchOutput.model_validate_json(raw)
    except ValidationError as exc:
        raise ResearchError(f"Semantic reconciliation returned invalid JSON/schema: {exc}") from exc
