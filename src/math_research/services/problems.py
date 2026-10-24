"""Explicit Problem registration/lifecycle; never mathematical acceptance or CRUD."""

from pathlib import Path
from typing import Annotated, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from math_research.core.atomicio import atomic_write_text
from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.checkpoint import checkpoint_transaction, consistent_checkpoint_read
from math_research.ledger.history import snapshot_entry
from math_research.ledger.manifest import Ledger
from math_research.ledger.records import store
from math_research.ledger.records.models import utcnow
from math_research.services.research import create_problem as create_record

Text = Annotated[str, Field(min_length=1, max_length=8000)]
Link = Annotated[str, Field(min_length=1, max_length=400)]
Closure = Literal["resolved", "abandoned", "superseded", "other"]
Metadata = Annotated[
    dict[Annotated[str, Field(min_length=1, max_length=64)], Annotated[str, Field(max_length=200)]],
    Field(max_length=10),
]


class ProblemInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    dry_run: bool = False

    @model_validator(mode="after")
    def bounded(self) -> Self:
        for name in self.model_fields_set:
            value = getattr(self, name)
            if isinstance(value, str) and name != "workspace":
                if not value.strip() and name != "summary":
                    raise ValueError(f"{name} must not be blank.")
                setattr(self, name, value.strip())
        for name in ("source_refs", "resolution_refs"):
            values = getattr(self, name, None)
            if values is not None:
                if any(not value.strip() for value in values):
                    raise ValueError(f"{name} must contain nonblank references.")
                setattr(self, name, list(dict.fromkeys(value.strip() for value in values)))
        if len(self.model_dump_json().encode("utf-8")) > 12000:
            raise ValueError("Problem input exceeds 12,000 UTF-8 bytes; use concise fields.")
        return self


class CreateProblemInput(ProblemInput):
    title: str = Field(min_length=1, max_length=300, pattern=r"^[^\r\n]+$")
    statement: Text
    primary_target: Text = Field(max_length=2000)
    summary: str = Field(default="", max_length=1000)
    source_refs: list[Link] = Field(default_factory=list, max_length=20)
    metadata: Metadata = Field(default_factory=dict)


class UpdateProblemInput(ProblemInput):
    problem_id: str = Field(pattern=r"^PROBLEM-\d{4,}$", max_length=128)
    revision_kind: Literal["metadata", "semantic"] = "metadata"
    expected_version: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    title: str | None = Field(default=None, min_length=1, max_length=300, pattern=r"^[^\r\n]+$")
    statement: Text | None = None
    primary_target: Text | None = Field(default=None, max_length=2000)
    summary: str | None = Field(default=None, max_length=1000)
    source_refs: list[Link] | None = Field(default=None, max_length=20)
    metadata: Metadata | None = None
    lifecycle_status: Literal["active", "paused", "closed"] | None = None
    closure_kind: Closure | None = None
    closure_reason: str | None = Field(default=None, min_length=1, max_length=1000)
    resolution_refs: list[Link] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def explicit_revision(self) -> Self:
        if {
            "statement",
            "primary_target",
        } & self.model_fields_set and self.revision_kind != "semantic":
            raise ValueError("statement/primary_target require revision_kind='semantic'.")
        changes = self.model_fields_set - {
            "problem_id",
            "revision_kind",
            "expected_version",
            "dry_run",
            "workspace",
        }
        if not changes or any(getattr(self, name) is None for name in changes):
            raise ValueError("Supply at least one non-null Problem field to update.")
        return self


def _result(state: Path, problem, fields: dict, *, dry_run: bool, before=None, semantic=False):
    ref = ObjectRef(problem_id=problem.id, kind="problem", object_id=problem.id)
    return {
        "problem_id": problem.id,
        "ref": ref.qualified_id,
        "dry_run": dry_run,
        "normalized_fields": fields,
        "lifecycle_change": {
            "from": before.lifecycle_status if before else None,
            "to": problem.lifecycle_status,
        },
        "semantic_revision": semantic,
        "expected_impact": "Existing pinned dependencies may become STALE; no blanket cascade."
        if semantic and before
        else "No mathematical dependency version change.",
        "validation_errors": [],
        "authority_promoted": False,
        "version": None if dry_run else Ledger(state).get(ref).version,
        "id_reserved": not dry_run,
    }


def create_problem(state: Path, **arguments) -> dict:
    args = CreateProblemInput.model_validate(arguments)
    fields = args.model_dump(exclude={"dry_run"})
    if args.dry_run:

        def preview():
            from math_research.ledger.records.models import ProblemRecord

            problem = ProblemRecord(
                id=store._next_problem_id(state), **fields, statement_authority="PROVISIONAL"
            )
            return _result(state, problem, fields, dry_run=True)

        return consistent_checkpoint_read(state, preview)
    statement = fields.pop("statement")
    title = fields.pop("title")
    with checkpoint_transaction(state, None, problem_record=True):
        problem = create_record(state, title, statement, **fields, provisional=True, activate=False)
        return _result(
            state, problem, {**fields, "title": title, "statement": statement}, dry_run=False
        )


def update_problem(state: Path, **arguments) -> dict:
    args = UpdateProblemInput.model_validate(arguments)
    fields = args.model_dump(
        exclude_unset=True, exclude={"problem_id", "revision_kind", "expected_version", "dry_run"}
    )

    def operation():
        old = store.require_dossier(state, args.problem_id)
        ref = ObjectRef(problem_id=old.id, kind="problem", object_id=old.id)
        entry = Ledger(state).get(ref)
        if args.expected_version and entry.version != args.expected_version:
            raise ResearchError(
                "Problem version conflicts with expected_version; reload and preview."
            )
        before_statement = store.statement_body_for_display(store.read_statement(state, old.id))
        statement = fields.get("statement", before_statement)
        if "resolution_refs" in fields:
            fields["resolution_refs"] = list(
                dict.fromkeys(
                    Ledger(state)
                    .resolve(link, problem_id=None if ":" in link else old.id)
                    .qualified_id
                    for link in fields["resolution_refs"]
                )
            )
        changes = {k: v for k, v in fields.items() if k != "statement"}
        revised = old.model_copy(update=changes)
        semantic = statement != before_statement or revised.primary_target != old.primary_target
        if revised.lifecycle_status == "closed" and (
            not revised.closure_kind or not revised.closure_reason.strip()
        ):
            raise ResearchError("Closing requires closure_kind and a nonempty closure_reason.")
        if (
            revised.lifecycle_status != "closed"
            and {"closure_kind", "closure_reason", "resolution_refs"} & fields.keys()
        ):
            raise ResearchError("Closure fields can only be updated on a closed Problem.")
        for link in revised.resolution_refs:
            Ledger(state).resolve(link)  # Links only: no dependency edge or authority grant.
        if args.dry_run:
            return _result(state, revised, fields, dry_run=True, before=old, semantic=semantic)
        if semantic:
            snapshot_entry(state, entry)  # Prior committed version; retained on rollback.
            revised.statement_authority = "PROVISIONAL"
        revised.version_title = old.version_title if old.version_title is not None else old.title
        revised.updated_at = utcnow()
        base = store.dossier_dir(state, old.id)
        atomic_write_text(
            base / "problem.yaml",
            yaml.safe_dump(revised.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        )
        if "statement" in fields and statement != before_statement:
            atomic_write_text(base / "statement.md", f"# {old.id}\n\n{statement}\n")
        return _result(state, revised, fields, dry_run=False, before=old, semantic=semantic)

    if args.dry_run:
        return consistent_checkpoint_read(state, operation)
    with checkpoint_transaction(state, args.problem_id, problem_record=True):
        return operation()
