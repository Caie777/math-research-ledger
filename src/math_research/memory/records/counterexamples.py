"""First-class counterexamples in the existing Problem Record, without truth promotion."""

from __future__ import annotations

from pathlib import Path

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError
from math_research.core.jsonl import next_id, read_jsonl, rewrite_jsonl
from math_research.memory.records import store
from math_research.memory.records.models import CounterexampleRecord
from math_research.memory.records.write_boundary import human_write


def render_counterexample(record: CounterexampleRecord) -> str:
    return (
        f"# {record.id}: {record.title}\n\nTarget: {record.target_id}\n"
        f"Status: {record.status} (Human record; not machine verification)\n\n"
        f"## Construction\n\n{record.construction}\n\n"
        f"## Verification\n\n{record.verification}\n\n"
        f"## Scope\n\n{record.scope}\n\n"
        f"## Source provenance\n\n{', '.join(record.source_artifacts)}\n\n{record.notes}\n"
    )


def list_counterexamples(ot_dir: Path, problem_id: str) -> list[CounterexampleRecord]:
    return read_jsonl(
        store.dossier_dir(ot_dir, problem_id) / "counterexamples/index.jsonl", CounterexampleRecord
    )


def get_counterexample(ot_dir: Path, problem_id: str, ident: str) -> CounterexampleRecord | None:
    return next((r for r in list_counterexamples(ot_dir, problem_id) if r.id == ident), None)


def read_counterexample(ot_dir: Path, record: CounterexampleRecord) -> tuple[str, Path]:
    base = store.dossier_dir(ot_dir, record.problem_id).resolve()
    path = (base / record.body_path).resolve()
    if not path.is_relative_to(base / "counterexamples") or not path.is_file():
        raise ResearchError(f"Counterexample body unavailable: {record.id}")
    body = path.read_bytes().decode("utf-8")
    if body != render_counterexample(record):
        raise ResearchError(
            f"Counterexample body differs from its full canonical record: {record.id}"
        )
    return body, path


@human_write
def add_counterexample(
    ot_dir: Path,
    problem_id: str,
    *,
    target_id: str,
    construction: str,
    verification: str,
    scope: str,
    title: str = "",
    notes: str = "",
    source_artifacts: list[str] | None = None,
) -> CounterexampleRecord:
    """Record a human witness, separately from any accepted REFUTES/INVALIDATES edge."""
    store.require_dossier(ot_dir, problem_id)
    if not all(text.strip() for text in (construction, verification, scope)):
        raise ResearchError("Counterexample requires full construction, verification and scope.")
    targets = {c.id for c in store.list_claims(ot_dir, problem_id)}
    targets.update(p.id for p in store.list_proof_attempts(ot_dir, problem_id))
    targets.update(a.id for a in store.list_approaches(ot_dir, problem_id))
    if target_id not in targets:
        raise ResearchError(
            "Counterexample requires an existing Statement, Proof or Approach target."
        )
    # Workspace allocation, including orphan body files, serialized across Problems.
    # This lock has no persisted allocator/database behind it.
    with file_lock(ot_dir / "counterexample_ids"):
        existing_ids = [
            r.id for d in store.list_dossiers(ot_dir) for r in list_counterexamples(ot_dir, d.id)
        ]
        existing_ids.extend(
            p.stem for p in (ot_dir / "problems").glob("*/counterexamples/COUNTEREXAMPLE-*.md")
        )
        ident = next_id("COUNTEREXAMPLE", existing_ids)
        record = CounterexampleRecord(
            id=ident,
            problem_id=problem_id,
            target_id=target_id,
            construction=construction,
            verification=verification,
            scope=scope,
            title=title,
            notes=notes,
            source_artifacts=source_artifacts or [],
            body_path=f"counterexamples/{ident}.md",
        )
        atomic_write_text(
            store.dossier_dir(ot_dir, problem_id) / record.body_path, render_counterexample(record)
        )
        index = store.dossier_dir(ot_dir, problem_id) / "counterexamples/index.jsonl"
        rewrite_jsonl(index, [*list_counterexamples(ot_dir, problem_id), record])
        return record
