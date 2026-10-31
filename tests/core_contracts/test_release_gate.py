"""Support-policy gate contracts; shared semantics never become compatibility-only."""

import argparse
import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("release_gate", ROOT / "scripts/release_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def test_release_gate_requires_real_dsh_and_supports_asar_paths():
    args = argparse.Namespace(dsh_executable=None, dsh_node_modules=None, python=sys.executable)
    with pytest.raises(ValueError, match="real DSH"):
        gate.configuration(args)
    args.dsh_executable = sys.executable
    args.dsh_node_modules = str(ROOT / "virtual.asar/node_modules")
    env = gate.configuration(args)
    assert env["MRL_DSH_REQUIRED"] == "1"
    assert env["MRL_DSH_PYTHON"] == sys.executable
    args.python = str(ROOT / "absent-python")
    with pytest.raises(ValueError, match="executable"):
        gate.configuration(args)


def test_official_host_patch_cannot_install_fallback_alongside_it():
    base = ROOT / "integrations/deepseek-harness"
    host = yaml.safe_load((base / "host-plugin/cordis.patch.yml").read_text("utf-8"))
    assert len(host) == len(host[0]["insert"]) == 1
    assert host[0]["insert"][0]["name"] == "dsh-math-research-ledger-host"
    assert set(host[0]["insert"][0]["config"]) == {"python"}
    fallback = yaml.safe_load((base / "config-bundle/cordis.patch.yml").read_text("utf-8"))
    assert host[0]["insert"][0]["id"] != fallback[0]["insert"][0]["id"]
    assert fallback[0]["insert"][0]["name"] == "@deepseek-ai/dsh-mcp-client"


def test_readonly_inventory_detects_content_mtime_and_generation_changes(tmp_path):
    from workspace_inventory import inventory

    from math_research.core.workspace import init_workspace
    from math_research.services.research import create_problem

    init_workspace(tmp_path)
    state = tmp_path / ".math-research-ledger"
    create_problem(state, "Synthetic inventory fixture")
    first = inventory(state)
    assert first == inventory(state)
    assert first["file_count"] == len(first["files"])
    assert first["latest_mtime_ns"] > 0
    marker = state / ".checkpoint-generation"
    marker.write_text("synthetic-generation", "utf-8")
    second = inventory(state)
    assert second["ledger_generation"] == "synthetic-generation"
    assert first["tree_hash"] != second["tree_hash"]
    assert first != second
    original_stat = marker.stat()
    os.utime(marker, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000_000))
    third = inventory(state)
    assert second["ledger_generation"] == third["ledger_generation"]
    assert second["total_bytes"] == third["total_bytes"]
    assert second["tree_hash"] != third["tree_hash"]
    marker.write_text("different-generation", "utf-8")
    os.utime(marker, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns + 1_000_000_000))
    fourth = inventory(state)
    assert (
        third["files"][".checkpoint-generation"]["mtime_ns"]
        == fourth["files"][".checkpoint-generation"]["mtime_ns"]
    )
    assert third["tree_hash"] != fourth["tree_hash"]


def test_link_guard_handles_windows_reparse_points_without_python312_api():
    from workspace_inventory import is_link

    fake = SimpleNamespace(
        is_symlink=lambda: False,
        lstat=lambda: SimpleNamespace(st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT),
    )
    assert is_link(fake)
    fake.lstat = lambda: SimpleNamespace()
    assert not is_link(fake)


@pytest.mark.parametrize("failure", ["core", "compat", "compat-timeout"])
def test_required_failures_block_but_codex_only_failures_do_not(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(gate, "ROOT", tmp_path)
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k not_actual_dsh")
    monkeypatch.setattr(gate, "verify_dsh_evidence", lambda *a, **k: "checked-report.json")
    output = tmp_path / "dist/report"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_gate.py",
            "--dsh-executable",
            sys.executable,
            "--dsh-node-modules",
            str(tmp_path / "virtual.asar/node_modules"),
            "--python",
            sys.executable,
            "--output",
            str(output),
        ],
    )
    observed = []

    def run(command, **kwargs):
        observed.append(command)
        assert kwargs["env"]["MRL_DSH_REQUIRED"] == "1"
        assert "PYTEST_ADDOPTS" not in kwargs["env"]
        if "codex_compat" in command:
            if failure == "compat-timeout":
                raise subprocess.TimeoutExpired(command, 180)
            return SimpleNamespace(returncode=1)
        if "not codex_compat" in command and failure == "core":
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(gate.subprocess, "run", run)
    assert gate.main() == (1 if failure == "core" else 0)
    report = json.loads((output / "result.json").read_text("utf-8"))
    assert report["required_passed"] is (failure != "core")
    assert any("not codex_compat" in command for command in observed)
    assert any("codex_compat" in command for command in observed) is (failure != "core")


def test_inventory_cli_cannot_overwrite_research_workspace_metadata(tmp_path):
    from math_research.core.workspace import init_workspace

    init_workspace(tmp_path)
    config = tmp_path / "workspace.yaml"
    before = config.read_bytes()
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(ROOT / "scripts/workspace_inventory.py"),
            str(tmp_path / ".math-research-ledger"),
            str(config),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode != 0
    assert "outside the entire research workspace" in result.stderr
    assert config.read_bytes() == before


def test_release_cannot_succeed_when_actual_dsh_was_deselected(tmp_path):
    with pytest.raises(RuntimeError, match="fresh report"):
        gate.verify_dsh_evidence(tmp_path, readonly=False)
    folder = tmp_path / "pytest/test_actual_dsh_agent_factory_0/host-acceptance"
    folder.mkdir(parents=True)
    report = {
        "dsh": "0.2.1-rc.3",
        "model_called": False,
        "cases": {str(i): {"passed": True} for i in range(17)},
    }
    (folder / "acceptance.json").write_text(json.dumps(report), "utf-8")
    assert gate.verify_dsh_evidence(tmp_path, readonly=False).endswith("acceptance.json")
    with pytest.raises(RuntimeError, match="Incomplete"):
        gate.verify_dsh_evidence(tmp_path, readonly=True)
