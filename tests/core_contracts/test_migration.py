import json
from pathlib import Path

import pytest

from math_research.core.atomicio import atomic_write_text
from math_research.core.errors import ResearchError
from math_research.core.migration import migrate_workspace, rollback_migration
from math_research.core.paths import MIGRATION_JOURNAL, state_at
from math_research.core.workspace import init_workspace
from math_research.ledger.manifest import Ledger
from math_research.services.ingest import ingest_episode


def make_legacy(state):
    root = state.parent
    legacy = root / ".math-research"
    state.rename(legacy)
    config = root / "workspace.yaml"
    config.write_text(
        config.read_text("utf-8").replace("workspace_version: 2", "workspace_version: 1"), "utf-8"
    )
    return legacy


def test_migration_preserves_every_byte_versions_provenance_and_operational_paths(
    research, tmp_path
):
    state, ref = research
    legacy = make_legacy(state)
    ingest_episode(
        legacy,
        ref.problem_id,
        "fixture.md",
        b"## Claim: fixture\n\nSynthetic only.\n",
        provenance="C:/historical/source",
    )
    before = {p.relative_to(legacy): p.read_bytes() for p in legacy.rglob("*") if p.is_file()}
    versions = {e.qualified_id: e.version for e in Ledger(legacy).objects()}
    source_version = Ledger(legacy).source_version()
    ordinary = legacy.parent / "user manuscript.txt"
    ordinary.write_bytes(b"user bytes")
    target = tmp_path / "unified workspace"
    target.mkdir()
    migrate_workspace(legacy.parent, target)
    moved = target / ".math-research-ledger"
    assert {p.relative_to(moved): p.read_bytes() for p in moved.rglob("*") if p.is_file()} == before
    assert {e.qualified_id: e.version for e in Ledger(moved).objects()} == versions
    assert Ledger(moved).source_version() == source_version
    assert all(
        Path(a["path"]).is_relative_to(moved)
        for e in Ledger(moved).objects()
        for a in e.artifact_refs
    )
    assert ordinary.read_bytes() == b"user bytes"
    assert state_at(target) == moved
    assert migrate_workspace(target)["migrated"] is False


def test_conflicts_init_and_version_mismatch_fail_without_writes(research):
    state, _ = research
    legacy = make_legacy(state)
    with pytest.raises(ResearchError, match="migrate"):
        init_workspace(state.parent)
    state.mkdir()
    (state / "unknown").write_bytes(b"preserve")
    with pytest.raises(ResearchError, match="Conflicting"):
        migrate_workspace(state.parent)
    assert (state / "unknown").read_bytes() == b"preserve"
    assert legacy.is_dir()


def test_metadata_failure_rolls_back_directory_and_exact_metadata(research, monkeypatch):
    state, _ = research
    legacy = make_legacy(state)
    metadata = state.parent / "workspace.yaml"
    before = metadata.read_bytes()

    def fail(path, text):
        if path == metadata:
            raise OSError("synthetic metadata failure")
        return atomic_write_text(path, text)

    monkeypatch.setattr("math_research.core.migration.atomic_write_text", fail)
    with pytest.raises(OSError, match="synthetic"):
        migrate_workspace(state.parent)
    assert legacy.is_dir() and not state.exists()
    assert metadata.read_bytes() == before
    # Recovery can be repeated explicitly if publication of restored metadata failed.
    monkeypatch.undo()
    if (state.parent / MIGRATION_JOURNAL).exists():
        rollback_migration(state.parent)
    assert state_at(state.parent) == legacy


def test_interrupted_migration_blocks_reads_until_explicit_rollback(research):
    state, _ = research
    legacy = make_legacy(state)
    metadata = state.parent / "workspace.yaml"
    value = {"source": str(legacy), "metadata_before": metadata.read_bytes().hex()}
    (state.parent / MIGRATION_JOURNAL).write_text(json.dumps(value), "utf-8")
    legacy.rename(state)
    with pytest.raises(ResearchError, match="rollback"):
        state_at(state.parent)
    rollback_migration(state.parent)
    assert state_at(state.parent) == legacy
