"""Configuration-only packaging and preparation; no DSH Host/Profile invocation."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest
import yaml

from math_research import __version__

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "integrations/deepseek-harness/config-bundle"
SCRIPT = ROOT / "scripts/prepare_dsh_config_bundle.py"
spec = importlib.util.spec_from_file_location("prepare_config", SCRIPT)
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)


def test_manifest_locale_icon_and_no_adapter():
    package = json.loads((BUNDLE / "package.json").read_text("utf-8"))
    assert package["version"] == __version__ == "1.2.1"
    assert package["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    assert package["files"] == [
        "cordis.patch.yml",
        "locale/*.json",
        "icon.svg",
        "README.md",
        "LICENSE",
    ]
    assert not {"dependencies", "peerDependencies", "scripts", "main"} & package.keys()
    assert not any(p.suffix in {".js", ".mjs"} or p.name == "install.py" for p in BUNDLE.rglob("*"))
    for language in ("en", "zh"):
        meta = json.loads((BUNDLE / f"locale/{language}.json").read_text("utf-8"))["meta"]
        assert meta["title"] == "MathResearch Ledger" and meta["description"]
    assert ET.parse(BUNDLE / "icon.svg").getroot().tag.endswith("svg")
    assert (BUNDLE / "icon.svg").stat().st_size <= 256 * 1024


def test_patch_is_one_native_pinned_client():
    rows = yaml.safe_load((BUNDLE / "cordis.patch.yml").read_text("utf-8"))
    assert len(rows) == len(rows[0]["insert"]) == 1
    row = rows[0]["insert"][0]
    assert row["name"] == "@deepseek-ai/dsh-mcp-client"
    config = row["config"]
    assert config["serverName"] == "math-research-ledger" and config["transport"] == "stdio"
    assert config["command"] == "__MRL_PYTHON__"
    assert config["args"][-2:] == ["--workspace", "__MRL_WORKSPACE__"]
    assert config["failOnStartupError"] is True and config["toolCallTimeoutMs"] == 120000


@pytest.fixture
def deployment(tmp_path):
    workspace = tmp_path / "Researcher's 合成 workspace"
    (workspace / ".math-research-ledger").mkdir(parents=True)
    (workspace / ".math-research-ledger/data.txt").write_bytes(b"synthetic unchanged")
    wheel = tmp_path / f"math_research_ledger-{__version__}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"math_research_ledger-{__version__}.dist-info/METADATA",
            f"Name: math-research-ledger\nVersion: {__version__}\n",
        )
    return workspace, wheel, tmp_path / "out", tmp_path / "runtime"


def invoke(deployment, *extra):
    workspace, wheel, out, runtime = deployment
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--no-install",
            "--python",
            sys.executable,
            "--workspace",
            str(workspace),
            "--wheel",
            str(wheel),
            "--out",
            str(out),
            "--runtime",
            str(runtime),
            *extra,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=40,
    )


def test_no_install_renders_only_allowlisted_config_without_touching_state(deployment):
    workspace, _, out, runtime = deployment
    before = {p.relative_to(workspace): p.read_bytes() for p in workspace.rglob("*") if p.is_file()}
    value = invoke(deployment)
    assert value.returncode == 0, value.stderr
    assert "ordinary PowerShell" in value.stdout
    assert not runtime.exists()
    assert {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()} == set(prep.FILES)
    text = (out / "cordis.patch.yml").read_text("utf-8")
    assert "__MRL_" not in text
    config = yaml.safe_load(text)[0]["insert"][0]["config"]
    assert Path(config["command"]).is_absolute()
    assert config["args"][-1] == str(workspace.resolve())
    assert before == {
        p.relative_to(workspace): p.read_bytes() for p in workspace.rglob("*") if p.is_file()
    }
    assert not list(out.rglob(".venv")) and not list(out.rglob(".runtime.json"))
    assert invoke(deployment).returncode != 0
    assert invoke(deployment, "--force").returncode == 0
    (out / "user-file").write_bytes(b"preserve")
    assert invoke(deployment, "--force").returncode != 0
    assert (out / "user-file").read_bytes() == b"preserve"


@pytest.mark.parametrize(
    "failure", ["missing-state", "missing-python", "bad-python", "wheel-version"]
)
def test_preparation_errors_do_not_create_state_or_output(deployment, failure, monkeypatch):
    workspace, wheel, out, _ = deployment
    extra = []
    if failure == "missing-state":
        extra = ["--workspace", str(workspace.parent)]
    elif failure == "missing-python":
        extra = ["--python", str(workspace / "missing")]
    elif failure == "bad-python":
        fake = workspace.parent / "not-an-executable"
        fake.write_bytes(b"not Python")
        extra = ["--python", str(fake)]
    else:
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("x.dist-info/METADATA", "Name: math-research-ledger\nVersion: 0.0.0\n")
    value = invoke(deployment, *extra)
    assert value.returncode != 0 and "Preparation failed" in value.stderr
    assert not out.exists() and not (workspace.parent / ".math-research-ledger").exists()


@pytest.mark.parametrize("value", [r"D:\Reader's Notes\数学", "/tmp/Researcher's notes"])
def test_yaml_quoting_preserves_apostrophes_and_backslashes(value):
    assert yaml.safe_load("path: " + prep.quote(value))["path"] == value


@pytest.mark.parametrize("minor,accepted", [(11, True), (12, True), (13, True), (14, False)])
def test_python_policy_without_download_or_fallback(monkeypatch, minor, accepted):
    monkeypatch.setattr(prep, "run", lambda *a, **k: json.dumps({"version": [3, minor]}))
    if accepted:
        assert prep.python_info(Path(sys.executable))["version"] == [3, minor]
    else:
        with pytest.raises(ValueError, match="3.11–3.13"):
            prep.python_info(Path(sys.executable))


def test_default_python_uses_only_py_312(monkeypatch):
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        raise FileNotFoundError("synthetic launcher missing")

    monkeypatch.setattr(prep, "run", run)
    with pytest.raises(ValueError, match="Python 3.12 not found"):
        prep.select_python(None)
    assert len(commands) == 1 and commands[0][:2] == ["py", "-3.12"]


def test_runtime_mismatch_is_an_explicit_error(monkeypatch):
    monkeypatch.setattr(prep, "run", lambda *a, **k: "0.0.0")
    with pytest.raises(ValueError, match="differs from Bundle"):
        prep.verify_runtime(Path(sys.executable), __version__)


def test_actual_npm_tarball_keeps_private_runtime_and_state_out(deployment):
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        pytest.skip("npm is needed for actual pack validation")
    _, _, out, _ = deployment
    value = invoke(deployment)
    assert value.returncode == 0, value.stderr
    for name in (".venv", ".math-research-ledger"):
        (out / name).mkdir()
        (out / name / "private").write_bytes(b"not packaged")
    (out / ".runtime.json").write_text("private", encoding="utf-8")
    packed = subprocess.run(
        [npm, "pack", str(out), "--pack-destination", str(out.parent), "--json"],
        capture_output=True,
        text=True,
        check=True,
        timeout=45,
        env={**os.environ, "npm_config_cache": str(out.parent / "npm-cache")},
    )
    with tarfile.open(out.parent / json.loads(packed.stdout)[0]["filename"]) as archive:
        assert set(archive.getnames()) == {"package/" + f for f in prep.FILES}


def test_python_artifacts_exclude_runtime_state_and_evidence(tmp_path):
    source = tmp_path / "source"
    paths = (
        subprocess.check_output(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
        )
        .decode()
        .split("\0")
    )
    for relative in filter(None, paths):
        original = ROOT / relative
        if original.is_file():
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
    for relative in (
        "dist/private-evidence.log",
        ".math-research-ledger/private.md",
        "integrations/deepseek-harness/config-bundle/.runtime.json",
        "integrations/deepseek-harness/config-bundle/.venv/private.md",
    ):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private fixture", encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            "--sdist",
            "--outdir",
            str(tmp_path / "artifacts"),
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=120,
    )
    with zipfile.ZipFile(next((tmp_path / "artifacts").glob("*.whl"))) as archive:
        assert all(
            n.startswith(("math_research/", f"math_research_ledger-{__version__}.dist-info/"))
            for n in archive.namelist()
        )
        assert "math_research/mcp/server.py" in archive.namelist()
    with tarfile.open(next((tmp_path / "artifacts").glob("*.tar.gz"))) as archive:
        names = archive.getnames()
        assert any(n.endswith("config-bundle/package.json") for n in names)
        assert not any(
            ".runtime.json" in n
            or ".venv" in n
            or ".math-research-ledger" in n
            or "private-evidence" in n
            for n in names
        )
