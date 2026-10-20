"""Typed records and unified deterministic projections."""

from pathlib import Path

from pydantic import BaseModel

from math_research.core.atomicio import file_lock
from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import Dependency, DependencyRole
from math_research.ledger.manifest import Ledger, ManifestEntry
from math_research.ledger.persistence import append_once
from math_research.ledger.records import claims, store
from math_research.ledger.records.models import Definition
from math_research.ledger.records.write_boundary import human_write


def initialize(state: Path) -> dict:
    from math_research.core.workspace import init_workspace

    return {"created": [str(p) for p in init_workspace(state.parent)]}


def status(state: Path) -> dict:
    return {"state_dir": str(state), "problems": len(store.list_dossiers(state)), "objects": len(Ledger(state).objects())}


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
        from math_research.core.atomicio import atomic_write_text
        from math_research.core.hashing import content_hash

        # Per-object snapshots retain previous full typed content, not a global blob store.
        for value in [next(d for d in old if d.id == definition.id), definition]:
            version = content_hash(value.model_dump(mode="json"))
            snapshot = state / "ledger" / "versions" / problem_id / "definition" / definition.id / (version + ".json")
            if not snapshot.exists():
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(snapshot, value.model_dump_json(indent=2))
        store._write_yaml_list(path, [definition if d.id == definition.id else d for d in old])
    return definition


@human_write
def link_dependency(state: Path, dependent: ObjectRef, target: ObjectRef, role: DependencyRole) -> Dependency:
    ledger = Ledger(state)
    ledger.get(dependent)
    upstream = ledger.get(target)
    if dependent == target:
        raise ResearchError("Self dependency is not permitted.")
    from math_research.ledger.persistence import ledger_path, records
    from math_research.core.jsonl import append_jsonl

    edge = Dependency(dependent=dependent, target=target, role=role, expected_version=upstream.version)
    path = ledger_path(state, "dependencies")
    with file_lock(path):
        previous = [d for d in records(state, "dependencies", Dependency) if d.key == edge.key]
        if previous and previous[-1] == edge:
            return previous[-1]
        append_jsonl(path, edge)
    return edge


class ObjectView(BaseModel):
    object: ManifestEntry
    freshness: str
    freshness_reasons: list[str]
    authority: str
    verification: str
    usable_working_premise: bool
    trusted_formal_premise: bool


def list_objects(state: Path, problem_id: str | None = None) -> list[ObjectView]:
    from math_research.services.acceptance import accepted_targets
    from math_research.ledger.persistence import records
    from math_research.verification.models import VerificationReceipt
    from math_research.verification.freshness import Freshness, FreshnessResolver

    entries = Ledger(state).objects()
    resolver = FreshnessResolver(entries)
    accepted, formal = accepted_targets(state, entries)
    checks = records(state, "verifications", VerificationReceipt)
    result = []
    for entry in entries:
        if problem_id and entry.ref.problem_id != problem_id:
            continue
        fresh = resolver.resolve(entry.ref)
        relevant = [r for r in checks if r.target.ref == entry.ref and r.target.version == entry.version and resolver.check_pins((r.target, *r.dependencies)).freshness == Freshness.CURRENT]
        verification = "PASSED" if any(r.outcome.status == "PASSED" for r in relevant) else entry.verification
        accepted_here = entry.qualified_id in accepted
        if accepted_here:
            fresh = resolver.check_pins(accepted[entry.qualified_id])
        working = fresh.freshness == Freshness.CURRENT and entry.research_state not in {"INVALIDATED", "REFUTED", "SUPERSEDED", "REVISED", "HISTORICAL"} and entry.authority not in {"REJECTED/HISTORICAL", "ADVISORY", "NONE"} and entry.ref.kind not in {"gap", "failed_attempt", "episode", "source", "review_report", "verification"}
        result.append(ObjectView(object=entry, freshness=fresh.freshness.value, freshness_reasons=fresh.reasons, authority="HUMAN_ACCEPTED" if accepted_here else entry.authority, verification=verification, usable_working_premise=working, trusted_formal_premise=entry.qualified_id in formal and fresh.freshness == Freshness.CURRENT))
    return result


def get_object(state: Path, ref: ObjectRef) -> ObjectView:
    value = next((v for v in list_objects(state, ref.problem_id) if v.object.ref == ref), None)
    if value is None:
        raise ResearchError(f"Unknown qualified object: {ref.qualified_id}")
    return value
