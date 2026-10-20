"""Canonical Claim/Gap target shared by context and Research Agent."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from math_research.core.errors import ResearchError
from math_research.ledger.records import store
from math_research.ledger.records.models import ClaimRecord


class ResearchTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["claim"]
    problem_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def check_ids(self) -> ResearchTarget:
        if not self.problem_id.strip() or not self.node_id.strip():
            raise ValueError("target IDs cannot be blank")
        return self


def validate_research_target(ot_dir: Path, target: ResearchTarget) -> ClaimRecord:
    store.require_dossier(ot_dir, target.problem_id)
    claim = store.get_claim(ot_dir, target.problem_id, target.node_id)
    if claim is None:
        from math_research.ledger.episodes import list_candidates
        from math_research.ledger.state import KnowledgeStateResolver

        candidate = next(
            (
                c
                for c in list_candidates(ot_dir, target.problem_id)
                if c.object_id == target.node_id and c.kind in {"claim", "gap"}
            ),
            None,
        )
        if candidate is None:
            raise ResearchError(f"No Claim '{target.node_id}' in '{target.problem_id}'.")
        state = KnowledgeStateResolver(ot_dir).resolve(target.problem_id)[target.node_id]
        if state.authority == "REJECTED/HISTORICAL" or state.research_state in {
            "REVISED",
            "REFUTED",
            "SUPERSEDED",
            "HISTORICAL",
            "INVALIDATED",
        }:
            raise ResearchError("Research target is no longer current.")
        if state.canonical_id:
            accepted = store.get_claim(ot_dir, target.problem_id, state.canonical_id)
            if accepted:
                return accepted.model_copy(update={"id": target.node_id})
        return ClaimRecord(
            id=target.node_id,
            problem_id=target.problem_id,
            type="OPEN_GAP" if candidate.kind == "gap" else "CLAIM",
            statement=candidate.body,
            status="unverified",
            source_artifacts=[candidate.episode_id, candidate.candidate_id],
            depends_on=state.dependencies,
        )
    return claim
