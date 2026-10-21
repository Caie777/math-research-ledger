"""Tool/workspace separation, additive metadata and portable operational paths."""

import hashlib
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from math_research.cli.main import app
from math_research.core.config import load_config, workspace_config
from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.core.workspace import init_workspace
from math_research.ledger.archive import source_path
from math_research.ledger.episodes import list_episodes
from math_research.ledger.manifest import Ledger
from math_research.mcp.server import resolve_workspace
from math_research.services.ingest import ingest_episode
from math_research.services.research import add_definition, status
from math_research.services.retrieval import export_context_packet


def test_init_minimal_metadata_packaged_instructions_and_no_fake_records(tmp_path):
    root = tmp_path / "曲面 research"
    root.mkdir()
    result = CliRunner().invoke(app, ["-w", str(root), "init"])
    assert result.exit_code == 0, result.output
    assert (root / "AGENTS.md").is_file()
    assert "research_status" in (root / "AGENTS.md").read_text("utf-8")
    config = yaml.safe_load((root / "workspace.yaml").read_text("utf-8"))
    assert set(config) == {"workspace_version", "name", "created_at"}
    assert config["workspace_version"] == 2 and config["name"] == root.name
    assert load_config(root / "workspace.yaml").created_at.tzinfo is not None
    assert not (root / ".math-research-ledger/config.yaml").exists()
    assert not (root / "papers").exists() and not (root / "notes").exists()
    assert Ledger(root / ".math-research-ledger").objects() == []
    before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert init_workspace(root) == []
    assert all(p.read_bytes() == raw for p, raw in before.items())


def test_legacy_read_never_migrates_and_explicit_init_is_additive(tmp_path):
    root = tmp_path / "legacy"
    state = root / ".math-research"
    state.mkdir(parents=True)
    original = b"model:\n  provider: retired\nagent:\n  max_steps: 12\ncontext:\n  top_k: 5\n"
    (state / "config.yaml").write_bytes(original)
    (root / "AGENTS.md").write_text("Custom research instructions", "utf-8")
    assert workspace_config(root) is None
    assert resolve_workspace(root, environ={}) == state
    assert status(state)["metadata_status"] == "LEGACY_UNVERSIONED"
    assert not (root / "workspace.yaml").exists()
    with pytest.raises(ResearchError, match="migrate"):
        init_workspace(root)
    from math_research.core.migration import migrate_workspace

    migrate_workspace(root)
    state = root / ".math-research-ledger"
    assert (state / "config.yaml").read_bytes() == original
    assert (root / "AGENTS.md").read_text("utf-8") == "Custom research instructions"
    assert status(state)["workspace_metadata"]["workspace_version"] == 2
    assert status(state)["workspace_root"] == str(root)


@pytest.mark.parametrize(
    "metadata",
    [
        {"workspace_version": 3, "name": "unsupported", "created_at": "2026-10-20T00:00:00Z"},
        {"name": "missing version", "created_at": "2026-10-20T00:00:00Z"},
        {"workspace_version": 1, "name": "invalid timestamp", "created_at": "2026-10-20"},
        {
            "workspace_version": 1,
            "name": "runtime key",
            "created_at": "2026-10-20T00:00:00Z",
            "agent": {"autonomous": True},
        },
    ],
)
def test_unsupported_or_runtime_metadata_is_explicit_error(tmp_path, metadata):
    init_workspace(tmp_path)
    path = tmp_path / "workspace.yaml"
    raw = yaml.safe_dump(metadata)
    path.write_text(raw, "utf-8")
    with pytest.raises(ResearchError, match="workspace_version"):
        resolve_workspace(tmp_path, environ={})
    assert path.read_text("utf-8") == raw


def test_init_inside_existing_corpus_creates_selected_new_workspace(tmp_path):
    init_workspace(tmp_path)
    child = tmp_path / "new workspace"
    child.mkdir()
    result = CliRunner().invoke(app, ["-w", str(child), "init"])
    assert result.exit_code == 0, result.output
    assert resolve_workspace(child, environ={}) == child / ".math-research-ledger"
    assert load_config(child / "workspace.yaml").name == "new workspace"


def test_relocation_preserves_object_versions_and_historical_provenance(research, tmp_path):
    state, ref = research
    add_definition(state, ref.problem_id, "D", "Synthetic definition only")
    old_absolute = str(state / "old historical source.md")
    raw = ("## Claim: synthetic\n\nUnicode 数学 ∀z ∈ ℂ; fixture only.\n" + old_absolute).encode()
    ingest_episode(state, ref.problem_id, "test.md", raw, provenance=old_absolute)
    before = Ledger(state)
    expected_versions = {e.qualified_id: e.version for e in before.objects()}
    expected_source = before.source_version()
    target = tmp_path / "relocated corpus with spaces"
    shutil.copytree(state.parent, target)
    assert state.resolve().is_relative_to(tmp_path.resolve())
    assert target.resolve().is_relative_to(tmp_path.resolve())
    shutil.rmtree(state)  # No old location remains available to a broken resolver.
    moved = target / ".math-research-ledger"
    after = Ledger(moved)
    assert {e.qualified_id: e.version for e in after.objects()} == expected_versions
    assert after.source_version() == expected_source
    episode = list_episodes(moved)[0]
    assert episode.provenance == old_absolute
    archive = source_path(moved, episode.archive_path)
    assert archive.read_bytes() == raw
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == episode.content_sha256
    assert all(
        Path(a["path"]).is_relative_to(moved) for e in after.objects() for a in e.artifact_refs
    )
    packet = export_context_packet(moved, ObjectRef.parse(ref.qualified_id), token_budget=4000)
    assert packet.token_estimate <= 4000
    assert old_absolute in [e.record.get("provenance") for e in after.objects()]
