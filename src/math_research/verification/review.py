"""External independent review contracts. NO_GAP_FOUND confers no authority."""

from enum import StrEnum
from typing import Literal

from pydantic import Field

from math_research.verification.models import Strict, VersionPin


class ReviewVerdict(StrEnum):
    GAP_FOUND = "GAP_FOUND"
    DEPENDENCY_GAP = "DEPENDENCY_GAP"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    INCONCLUSIVE = "INCONCLUSIVE"
    NO_GAP_FOUND = "NO_GAP_FOUND"


class ReviewPacket(Strict):
    target: VersionPin
    claim: dict
    definitions: tuple[dict, ...]
    assumptions: tuple[dict, ...]
    proofs: tuple[dict, ...]
    dependencies: tuple[dict, ...]
    referenced_results: tuple[dict, ...]
    provenance: tuple[str, ...]
    source_version: str


class ReviewReport(Strict):
    id: str
    target: VersionPin
    reviewer: str = Field(min_length=1)
    verdict: ReviewVerdict
    findings: tuple[str, ...] = ()
    packet_version: str
    authority: Literal["ADVISORY"] = "ADVISORY"
