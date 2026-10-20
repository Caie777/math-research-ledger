"""Typed records and unified deterministic projections."""

from pathlib import Path

from math_research.core.atomicio import file_lock
from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import Dependency, DependencyRole
from math_research.ledger.manifest import Ledger
from math_research.ledger.projection import (
    ObjectView as ObjectView,
)
from math_research.ledger.projection import (
    get_object as get_object,
)
from math_research.ledger.projection import (
    list_objects as list_objects,
)
from math_research.ledger.records import claims, store
from math_research.ledger.records.models import Definition
from math_research.ledger.records.write_boundary import human_write


def initialize(state: Path) -> dict:
    from math_research.core.workspace import init_workspace

    return {"created": [str(p) for p in init_workspace(state.parent)]}


def status(state: Path, problem_id: str | None = None, *, offset: int = 0, limit: int = 20) -> dict:
    """Paginated orientation for a human or external harness, without full bodies."""
    from math_research.core.config import workspace_config

    metadata = workspace_config(state.parent)
    problems = store.list_dossiers(state)
    if problem_id:
        store.require_dossier(state, problem_id)
        problems = [p for p in problems if p.id == problem_id]
    views = list_objects(state, problem_id)
    return {
        "state_dir": str(state),
        "workspace_root": str(state.parent),
        "workspace_metadata": metadata.model_dump(mode="json") if metadata else None,
        "metadata_status": "VERSIONED" if metadata else "LEGACY_UNVERSIONED",
        "problems": len(problems),
        "objects": len(views),
        "problem_summaries": [
            {"id": p.id, "title": p.title[:400], "ref": f"{p.id}:problem:{p.id}"}
            for p in problems[offset : offset + limit]
        ],
        "object_summaries": [
            {
                "ref": v.object.qualified_id,
                "authority": v.authority,
                "verification": v.verification,
                "freshness": v.freshness,
                "research_state": v.object.research_state,
            }
            for v in views[offset : offset + limit]
        ],
        "offset": offset,
        "limit": limit,
        "truncated": offset > 0 or max(len(problems), len(views)) > offset + limit,
    }


def create_problem(state: Path, title: str, statement: str = ""):
    return store.create_dossier(state, statement or title, title=title)


def add_claim(state: Path, problem_id: str, statement: str):
    return claims.add_claim(state, problem_id, claim_type="CLAIM", statement=statement)


def add_definition(state: Path, problem_id: str, term: str, definition: str):
    return store.add_definition(state, problem_id, term, definition)


@human_write
def update_definition(state: Path, problem_id: str, definition: Definition) -> Definition:
    """Existing typed layout stays readable; pinned dependents retain old versions."""
    path = store.dossier_dir(state, problem_id) / "definitions.yaml"
    with file_lock(path):
        old = store.list_definitions(state, problem_id)
        if not any(d.id == definition.id for d in old):
            raise ResearchError("Definition does not exist in this Problem.")
        from math_research.ledger.history import snapshot_entry

        ref = ObjectRef(problem_id=problem_id, kind="definition", object_id=definition.id)
        snapshot_entry(state, Ledger(state).get(ref))
        store._write_yaml_list(path, [definition if d.id == definition.id else d for d in old])
        snapshot_entry(state, Ledger(state).get(ref))
    return definition


def history(state: Path, ref: ObjectRef) -> list[dict]:
    from math_research.ledger.history import object_history

    return object_history(state, ref)


@human_write
def link_dependency(
    state: Path, dependent: ObjectRef, target: ObjectRef, role: DependencyRole
) -> Dependency:
    ledger = Ledger(state)
    ledger.get(dependent)
    upstream = ledger.get(target)
    if dependent == target:
        raise ResearchError("Self dependency is not permitted.")
    from math_research.core.jsonl import append_jsonl
    from math_research.ledger.persistence import ledger_path, records

    edge = Dependency(
        dependent=dependent, target=target, role=role, expected_version=upstream.version
    )
    path = ledger_path(state, "dependencies")
    with file_lock(path):
        previous = [d for d in records(state, "dependencies", Dependency) if d.key == edge.key]
        if previous and previous[-1] == edge:
            return previous[-1]
        append_jsonl(path, edge)
    return edge
