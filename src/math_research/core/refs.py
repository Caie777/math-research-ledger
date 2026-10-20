"""Qualified identities do not encode content versions or guess a Problem scope."""

from pydantic import BaseModel, ConfigDict, Field


class ObjectRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    problem_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    kind: str = Field(pattern=r"^[a-z][a-z_]{0,63}$")
    object_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

    @property
    def qualified_id(self) -> str:
        return f"{self.problem_id or '_global'}:{self.kind}:{self.object_id}"

    @classmethod
    def parse(cls, value: str) -> "ObjectRef":
        scope, kind, ident = value.split(":")
        return cls(problem_id=None if scope == "_global" else scope, kind=kind, object_id=ident)


class VersionPin(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    ref: ObjectRef
    version: str = Field(pattern=r"^[a-f0-9]{64}$")
