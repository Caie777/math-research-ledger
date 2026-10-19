"""V0 artifacts are deliberately separate from canonical Claim records."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FormalState(StrEnum):
    PROVISIONAL = "provisional_formal"
    CHECKED = "checked"
    ACCEPTED = "accepted"


class Artifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FrozenSource(Artifact):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class FrozenManifest(Artifact):
    statement_version: int = Field(ge=1)
    reason: str
    frozen_at: str
    statement: FrozenSource
    local_definitions: tuple[FrozenSource, ...] = ()
    dependencies: tuple[FrozenSource, ...]
    lean_toolchain: str
    mathlib_ref: str
    mathlib_commit: str


class FormalCheckResult(Artifact):
    checked_at: str
    build_exit_code: int | None = None
    target_exit_code: int | None = None
    target_exists: bool = False
    hashes_match: bool = False
    axioms_parsed: bool = False
    axioms: tuple[str, ...] = ()
    sorry_ax: bool = False
    custom_axioms: tuple[str, ...] = ()
    source_violations: tuple[str, ...] = ()
    native_decide: bool = False
    timed_out: bool = False
    reasons: tuple[str, ...] = ()
    output_tail: str = ""
    log: str

    @property
    def status(self) -> FormalState:
        """A result cannot request acceptance or bypass the clean-check conditions."""
        clean = (
            self.build_exit_code == 0
            and self.target_exit_code == 0
            and self.target_exists
            and self.hashes_match
            and self.axioms_parsed
            and not self.sorry_ax
            and not self.custom_axioms
            and not self.source_violations
            and not self.timed_out
            and not self.reasons
        )
        return FormalState.CHECKED if clean else FormalState.PROVISIONAL


class FormalBundle(Artifact):
    id: str
    formal_repo: str
    formal_repo_commit: str
    declaration: str
    frozen: FrozenManifest
    problem_id: str | None = None
    check: FormalCheckResult | None = None
    correspondence_status: Literal["PENDING"] = "PENDING"
    usable_as_premise: Literal[False] = False
    human_accepted: Literal[False] = False
    promotes_claim: Literal[False] = False

    @property
    def status(self) -> FormalState:
        return self.check.status if self.check else FormalState.PROVISIONAL
