"""Thin DSH composition/package contracts, plus opt-in actual official Agent Host."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

from math_research import __version__

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "integrations/deepseek-harness/host-plugin"
spec = importlib.util.spec_from_file_location(
    "prepare_host", ROOT / "scripts/prepare_dsh_host_plugin.py"
)
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


def test_native_host_manifest_and_runtime_only_configuration():
    meta = json.loads((TEMPLATE / "package.json").read_text("utf-8"))
    assert meta["version"] == __version__
    assert meta["main"] == "index.cjs"
    assert meta["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert meta["peerDependencies"]["@deepseek-ai/dsh-mcp-client"] == "0.2.1-rc.3"
    rows = yaml.safe_load((TEMPLATE / "cordis.patch.yml").read_text("utf-8"))
    assert len(rows) == len(rows[0]["insert"]) == 1
    row = rows[0]["insert"][0]
    assert row["name"] == meta["name"]
    assert row["config"] == {"python": "__MRL_PYTHON__"}


def test_preparation_selects_python_never_workspace_or_runtime_install(tmp_path):
    out = tmp_path / "host"
    prep.prepare(out, Path(sys.executable))
    assert {p.name for p in out.iterdir()} == {
        "index.cjs",
        "package.json",
        "cordis.patch.yml",
        "README.md",
        "LICENSE",
    }
    config = yaml.safe_load((out / "cordis.patch.yml").read_text("utf-8"))[0]["insert"][0]["config"]
    assert config == {"python": str(Path(sys.executable).absolute())}
    assert not (out / ".math-research-ledger").exists()
    assert not (out / ".venv").exists()


def test_preparation_never_overwrites_or_downloads(tmp_path):
    with pytest.raises(ValueError, match="new package"):
        prep.prepare(tmp_path, Path(sys.executable))
    with pytest.raises(ValueError, match="existing persistent"):
        prep.prepare(tmp_path / "new", tmp_path / "absent-python")
    assert not (tmp_path / "new").exists()


def test_actual_public_host_tarball_has_no_local_runtime_or_state(tmp_path):
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        pytest.skip("npm is required for actual package inspection")
    public = tmp_path / "public"
    shutil.copytree(TEMPLATE, public)
    shutil.copyfile(ROOT / "LICENSE", public / "LICENSE")
    for name in (".venv", ".math-research-ledger"):
        (public / name).mkdir()
        (public / name / "synthetic-private").write_text("exclude", "utf-8")
    packed = subprocess.run(
        [npm, "pack", str(public), "--json", "--pack-destination", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
        env={**os.environ, "npm_config_cache": str(tmp_path / "npm-cache")},
    )
    with tarfile.open(tmp_path / json.loads(packed.stdout)[0]["filename"]) as archive:
        assert set(archive.getnames()) == {
            "package/" + name
            for name in ("index.cjs", "package.json", "cordis.patch.yml", "README.md", "LICENSE")
        }
        patch = archive.extractfile("package/cordis.patch.yml").read()
        assert b"__MRL_PYTHON__" in patch and str(tmp_path).encode() not in patch


@pytest.mark.integration
def test_actual_dsh_agent_factory_acceptance(tmp_path):
    executable = os.environ.get("MRL_DSH_EXECUTABLE")
    modules = os.environ.get("MRL_DSH_NODE_MODULES")
    python = os.environ.get("MRL_DSH_PYTHON")
    if not all((executable, modules, python)):
        pytest.skip(
            "Set MRL_DSH_EXECUTABLE/NODE_MODULES/PYTHON for isolated official Host acceptance"
        )
    out = tmp_path / "host-acceptance"
    assert out.resolve().is_relative_to(ROOT / "dist"), "Use --basetemp inside checkout dist/"
    env = {
        name: os.environ[name]
        for name in (
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "HOMEDRIVE",
            "HOMEPATH",
            "TEMP",
            "TMP",
        )
        if name in os.environ
    }
    env.update(ELECTRON_RUN_AS_NODE="1", DSH_HOME=str(tmp_path / "home"), NODE_PATH=modules)
    result = subprocess.run(
        [
            executable,
            "--expose-internals",
            str(ROOT / "integrations/deepseek-harness/agent-host-smoke.cjs"),
            modules,
            python,
            str(out),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    report = json.loads((out / "acceptance.json").read_text("utf-8"))
    assert report["dsh"] == "0.2.1-rc.3" and not report["model_called"]
    assert len(report["cases"]) == 14 and all(v["passed"] for v in report["cases"].values())
    assert report["cases"]["profile_plugin_OFF"]["new_agent_tools"] == 0
    assert report["cases"]["profile_plugin_ON"]["new_agent_tools"] == 11
