"""Portable deployment and explicit install contracts; actual Host evidence is separate."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from math_research import __version__

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "integrations/deepseek-harness/bundle"


def test_bundle_is_native_and_separate_from_codex():
    package = json.loads((BUNDLE / "package.json").read_text("utf-8"))
    assert package["version"] == __version__
    assert package["dsh"]["bundle"]["patch"] == "./cordis.patch.yml"
    rows = yaml.safe_load((BUNDLE / "cordis.patch.yml").read_text("utf-8"))[0]["insert"]
    assert len(rows) == 1
    assert rows[0]["name"] == package["name"] == "dsh-math-research-ledger"
    assert "@deepseek-ai/dsh-mcp-client" in package["peerDependencies"]
    assert "scripts" not in package  # no implicit pip/install/prepare hooks
    assert all(not name.startswith(".") for name in package["files"])
    assert "runtime/*.whl" in package["files"]
    assert (ROOT / ".codex-plugin/plugin.json").is_file()


def test_transport_precedence_and_actionable_missing_runtime(tmp_path):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed for the DSH deployment adapter")
    # Standalone transport has no DSH dependency; actual lifecycle uses the official Host.
    script = tmp_path / "check.mjs"
    script.write_text(
        "import {transportConfig} from " + json.dumps((BUNDLE / "transport.mjs").as_uri()) + ";\n"
        "import assert from 'node:assert/strict';\n"
        "const [root, python] = process.argv.slice(2);\n"
        "const explicit = await transportConfig({python,workspace:root}, {}, root);\n"
        "assert.deepEqual(explicit.args.slice(-2), ['--workspace',root]);\n"
        "assert.equal(explicit.command,python);\n"
        "const preferred = await transportConfig({python}, {MRL_PYTHON:'missing'},root);\n"
        "assert.equal(preferred.command,python);\n"
        "assert.equal((await transportConfig({}, {MRL_PYTHON:python},root)).command,python);\n"
        "await assert.rejects(transportConfig({}, {}, root), /install.py/);\n"
        "const fs = await import('node:fs/promises');\n"
        "await fs.writeFile(root+'/.runtime.json',JSON.stringify({python}));\n"
        "assert.equal((await transportConfig({}, {},root)).command,python);\n"
        "assert.deepEqual(explicit.env, {});\n"
        "assert.equal(explicit.transport,'stdio');\n"
        "assert.equal(explicit.failOnStartupError,true);\n",
        encoding="utf-8",
    )
    subprocess.run([node, str(script), str(tmp_path), sys.executable], check=True)


def test_explicit_runtime_install_checks_before_saving_and_never_initializes(tmp_path):
    installer = tmp_path / "install.py"
    shutil.copyfile(BUNDLE / "install.py", installer)
    subprocess.run([sys.executable, str(installer), "--python", sys.executable], check=True)
    saved = json.loads((tmp_path / ".runtime.json").read_text("utf-8"))
    assert Path(saved["python"]) == Path(sys.executable).resolve()
    assert sorted(p.name for p in tmp_path.iterdir()) == [".runtime.json", "install.py"]
    before = (tmp_path / ".runtime.json").read_bytes()
    failed = subprocess.run(
        [sys.executable, str(installer), "--python", str(tmp_path / "missing-python")],
        capture_output=True,
    )
    assert failed.returncode != 0
    assert (tmp_path / ".runtime.json").read_bytes() == before


def test_built_bundle_and_tarball_exclude_local_runtime_and_research(tmp_path):
    import os
    import tarfile
    import zipfile

    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        pytest.skip("npm is needed to validate the installable tarball")
    package = tmp_path / "package"
    env = {**os.environ, "TEMP": str(tmp_path), "TMP": str(tmp_path)}
    built = subprocess.run(
        [sys.executable, str(ROOT / "scripts/build_dsh_bundle.py"), str(package)],
        env=env,
        capture_output=True,
        text=True,
    )
    assert built.returncode == 0, built.stdout + built.stderr
    # Simulate a configured bundle: npm's allowlist must still exclude its private pointer.
    (package / ".runtime.json").write_text('{"python":"private-local-pointer"}')
    packed = subprocess.run(
        [npm, "pack", str(package), "--pack-destination", str(tmp_path), "--json"],
        check=True,
        capture_output=True,
        env={**env, "npm_config_cache": str(tmp_path / "npm-cache")},
        text=True,
    )
    tarball = tmp_path / json.loads(packed.stdout)[0]["filename"]
    with tarfile.open(tarball) as archive:
        names = set(archive.getnames())
        assert names == {
            "package/" + name
            for name in (
                "LICENSE",
                "README.md",
                "package.json",
                "cordis.patch.yml",
                "install.py",
                "index.mjs",
                "transport.mjs",
                f"runtime/math_research_ledger-{__version__}-py3-none-any.whl",
            )
        }
    with zipfile.ZipFile(next((package / "runtime").glob("*.whl"))) as wheel:
        assert all(
            n.startswith(("math_research/", f"math_research_ledger-{__version__}.dist-info/"))
            for n in wheel.namelist()
        )
        assert "math_research/mcp/server.py" in wheel.namelist()
