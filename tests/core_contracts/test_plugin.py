import json
import subprocess
import sys
from pathlib import Path

from math_research import __version__

ROOT = Path(__file__).resolve().parents[2]


def test_plugin_portable_identity_overlay_and_launcher(tmp_path):
    portable = json.loads((ROOT / "plugin.json").read_text("utf-8"))
    overlay = json.loads((ROOT / ".codex-plugin/plugin.json").read_text("utf-8"))
    config = json.loads((ROOT / "mcp.json").read_text("utf-8"))
    assert portable["name"] == overlay["name"] == "math-research-ledger"
    assert portable["version"] == overlay["version"] == __version__
    assert (
        portable["extensions"]["com.openai"]["mcpServers"] == overlay["mcpServers"] == "./mcp.json"
    )
    server = config["mcpServers"]["math-research-ledger"]
    assert server["type"] == "stdio" and server["command"] == "python"
    assert server["args"] == ["-B", "${PLUGIN_ROOT}/scripts/smr_mcp.py"]
    assert "cwd" not in server and "env" not in server
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/prepare_local_plugin.py"), str(tmp_path / "package")],
        check=True,
    )
    staged = json.loads((tmp_path / "package/mcp.json").read_text("utf-8"))
    assert staged["mcpServers"]["math-research-ledger"]["env"]["MRL_PYTHON"] == sys.executable
    assert (tmp_path / "package/src/math_research/core/research_agents.md").is_file()
    assert not (tmp_path / "package/.math-research-ledger").exists()


def test_capture_does_not_stage_commit_or_change_ordinary_files(tmp_path):
    import hashlib

    from math_research.core.workspace import init_workspace
    from math_research.services.ingest import ingest_episode
    from math_research.services.research import create_problem

    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args])

    git("init", "-q")
    ordinary = tmp_path / "chosen-note.md"
    ordinary.write_bytes(b"User-selected publication only.")
    git("add", "chosen-note.md")
    before = hashlib.sha256((tmp_path / ".git/index").read_bytes()).hexdigest()
    init_workspace(tmp_path)
    state = tmp_path / ".math-research-ledger"
    problem = create_problem(state, "Synthetic only")
    ingest_episode(
        state,
        problem.id,
        "synthetic.md",
        b"## Gap: synthetic\n\nUnresolved fixture.\n",
        provenance="synthetic",
    )
    assert hashlib.sha256((tmp_path / ".git/index").read_bytes()).hexdigest() == before
    assert git("ls-files").decode().splitlines() == ["chosen-note.md"]
    assert ordinary.read_bytes() == b"User-selected publication only."
    assert not (tmp_path / ".git/refs/heads/master").exists()
