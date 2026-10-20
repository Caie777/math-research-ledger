"""Version-pinned typed dependencies, separate from semantic similarity."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from math_research.core.refs import ObjectRef


class DependencyRole(StrEnum):
    LOGICAL_PREMISE = "logical_premise"
    DEFINITION = "definition"
    SOURCE_REFERENCE = "source_reference"
    PROOF_TARGET = "proof_target"
    EVIDENCE = "evidence_relation"
    ARTIFACT_PROVENANCE = "artifact_provenance"
    REVISION = "revision_supersession"
    FORMAL_CORRESPONDENCE = "formal_correspondence"


class Dependency(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    dependent: ObjectRef
    target: ObjectRef
    role: DependencyRole
    expected_version: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    provenance: str = "explicit"

    @property
    def key(self) -> tuple[str, str, str]:
        return self.dependent.qualified_id, self.target.qualified_id, self.role.value
