"""Thin DSH composition/package contracts, plus opt-in actual official Agent Host."""

import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "integrations/deepseek-harness/host-plugin"


def test_native_host_manifest_and_runtime_only_configuration():
    meta = json.loads((TEMPLATE / "package.json").read_text("utf-8"))
    # Adapter-only patches do not require a Python runtime release.
    assert meta["version"] == "1.5.1"
    assert "activation.cjs" in meta["files"]
    assert meta["main"] == "index.cjs"
    assert meta["exports"]["."] == "./index.cjs"
    for language in ("en", "zh"):
        locale = json.loads((TEMPLATE / f"locale/{language}.json").read_text("utf-8"))
        assert locale["meta"]["title"] == "MathResearch Ledger for DSH"
    assert meta["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert meta["engines"]["dsh"] == "0.2.x"
    assert meta["peerDependencies"]["@deepseek-ai/dsh-agent"] == "0.2.x"
    assert meta["peerDependencies"]["@deepseek-ai/dsh-mcp-client"] == "0.2.x"
    rows = yaml.safe_load((TEMPLATE / "cordis.patch.yml").read_text("utf-8"))
    assert len(rows) == len(rows[0]["insert"]) == 1
    row = rows[0]["insert"][0]
    assert row["name"] == meta["name"]
    assert row["config"] == {}


def test_actual_public_host_tarball_has_no_local_runtime_or_state(tmp_path):
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    node = shutil.which("node")
    if not npm or not node:
        pytest.skip("npm and Node are required for package and relocation checks")
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
            for name in (
                "index.cjs",
                "activation.cjs",
                "runtime.cjs",
                "package.json",
                "cordis.patch.yml",
                "README.md",
                "LICENSE",
                "locale/en.json",
                "locale/zh.json",
            )
        }
        patch = archive.extractfile("package/cordis.patch.yml").read()
        assert b"__MRL_" not in patch and yaml.safe_load(patch)[0]["insert"][0]["config"] == {}
        for member in archive.getmembers():
            content = archive.extractfile(member).read()
            assert str(tmp_path).encode() not in content
            assert str(sys.executable).encode() not in content

        # Reuse the real packed sources under two synthetic install roots. No DSH
        # processes or profiles are involved; only the plugin API boundary is stubbed.
        first = tmp_path / "旧 安装"
        second = tmp_path / "迁移 安装"
        first.mkdir()
        for member in archive.getmembers():
            target = first / member.name.removeprefix("package/")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    subprocess.run(
        [
            node,
            str(Path(__file__).with_name("dsh_runtime_contract.cjs")),
            first,
            second,
            sys.executable,
        ],
        cwd=tmp_path,
        check=True,
        timeout=45,
    )


@pytest.mark.integration
def test_actual_dsh_agent_factory_acceptance(tmp_path):
    executable = os.environ.get("MRL_DSH_EXECUTABLE")
    modules = os.environ.get("MRL_DSH_NODE_MODULES")
    python = os.environ.get("MRL_DSH_PYTHON")
    if not all((executable, modules, python)):
        message = "Set MRL_DSH_EXECUTABLE/NODE_MODULES/PYTHON for official Host acceptance"
        if os.environ.get("MRL_DSH_REQUIRED") == "1":
            pytest.fail(message + "; required release gate must not skip DSH")
        pytest.skip(message)
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
    readonly = os.environ.get("MRL_DSH_READONLY_WORKSPACE")
    result = subprocess.run(
        [
            executable,
            "--expose-internals",
            str(ROOT / "integrations/deepseek-harness/agent-host-smoke.cjs"),
            modules,
            python,
            str(out),
            *([readonly] if readonly else []),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    report = json.loads((out / "acceptance.json").read_text("utf-8"))
    assert report["dsh"].startswith("0.2.") and not report["model_called"]
    # Workspace-gated activation: no tools, process or state without a pointer.
    expected_cases = {
        "absence_no_tools_no_process_no_state",
        "explicit_default_activation",
        "explicit_subdirectory_activation",
        "reject_outside_and_unknown",
        "no_ancestor_search",
        "global_tools_absent",
    }
    if readonly:
        expected_cases.add("existing_real_workspace_pointer")
    assert set(report["cases"]) == expected_cases
    assert all(v["passed"] for v in report["cases"].values())
    assert report["cases"]["global_tools_absent"]["global_ledger_tools"] == 0
    assert report["cases"]["absence_no_tools_no_process_no_state"]["tools"] == 0
    assert report["cases"]["absence_no_tools_no_process_no_state"]["python_processes"] == 0
    assert report["cases"]["absence_no_tools_no_process_no_state"]["state_created"] is False
    assert report["cases"]["explicit_default_activation"]["new_agent_tools"] == 11
    assert report["cases"]["explicit_subdirectory_activation"]["bound"] == "research/foo"
    for launch in report["launches"]:
        assert launch["args"] == ["-I", "-B", "-m", "math_research.mcp.server", "--workspace", "."]
