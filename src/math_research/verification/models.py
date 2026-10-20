"""Verification evidence is immutable; currentness and authority are projections."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from math_research.core.refs import ObjectRef
from math_research.ledger.records.models import utcnow


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VerificationKind(StrEnum):
    FORMAL = "formal"
    EXACT = "exact"
    VALIDATED_COMPUTATION = "validated_computation"


class VersionPin(Strict):
    ref: ObjectRef
    version: str = Field(pattern=r"^[a-f0-9]{64}$")


class ArtifactRef(Strict):
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    role: str


class CheckOutcome(Strict):
    status: Literal["PASSED", "FAILED", "INCONCLUSIVE"]
    summary: str
    details: dict = Field(default_factory=dict)


class VerificationReceipt(Strict):
    id: str
    kind: VerificationKind
    target: VersionPin
    checker: str
    outcome: CheckOutcome
    dependencies: tuple[VersionPin, ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()
    created_at: datetime = Field(default_factory=utcnow)
    authority: Literal["NONE"] = "NONE"


class ExactCertificate(Strict):
    checker: str
    inputs: dict
    environment: dict = Field(default_factory=dict)
    scripts: tuple[ArtifactRef, ...] = ()
    outputs: tuple[ArtifactRef, ...] = ()
    scope: str = Field(min_length=1)


class ValidatedComputation(ExactCertificate):
    """Extension contract; reproducibility alone does not imply rigorous verification."""

    validation_method: str = Field(min_length=1)
    limitations: tuple[str, ...] = ()


class AcceptanceRequest(Strict):
    id: str
    target: VersionPin
    verification_id: str
    dependencies: tuple[VersionPin, ...] = ()
    created_at: datetime = Field(default_factory=utcnow)


class HumanCorrespondence(Strict):
    rationale: str = Field(min_length=1)
    informal: VersionPin
    formal: VersionPin


class AcceptanceReceipt(Strict):
    id: str
    request_id: str
    target: VersionPin
    verification_id: str
    dependencies: tuple[VersionPin, ...] = ()
    actor: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    correspondence: HumanCorrespondence | None = None
    created_at: datetime = Field(default_factory=utcnow)
    authority: Literal["HUMAN_ACCEPTED"] = "HUMAN_ACCEPTED"
