import json

import pytest
from typer.testing import CliRunner

from math_research.cli.main import app
from math_research.core.errors import ResearchError
from math_research.mcp.adapter import SCHEMAS, LedgerAdapter


def test_cli_services_share_same_qualified_objects(research):
    state, ref = research
    runner = CliRunner()
    result = runner.invoke(
        app, ["--workspace", str(state.parent), "ledger", "show", ref.qualified_id]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["object"]["qualified_id"] == ref.qualified_id
    result = runner.invoke(
        app, ["-w", str(state.parent), "context", "export", ref.qualified_id, "--budget", "3000"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["token_estimate"] <= 3000
    from math_research.retrieval.context import estimate_tokens

    assert estimate_tokens(result.output.strip()) <= 3000


def test_mcp_adapter_bounded_and_no_accept_or_filesystem(research):
    state, ref = research
    adapter = LedgerAdapter(state)
    assert "accept" not in SCHEMAS
    with pytest.raises(ResearchError):
        adapter.call("accept", {})
    with pytest.raises(ValueError):
        adapter.call("get_research_object", {"ref": ref.model_dump(), "path": "../outside"})
    result = adapter.call("get_research_object", {"ref": ref.model_dump(), "length": 10})
    assert len(result["content"]) <= 10 and result["truncated"]
    assert adapter.call("search_research", {"query": "synthetic"})["hits"]


def test_runtime_independent_import_boundaries():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "src" / "math_research"
    assert root.is_dir()
    for folder in ["core", "ledger", "retrieval", "verification", "services"]:
        for path in (root / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text("utf-8"))):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert not node.module.startswith(
                        ("math_research.agent", "math_research.app", "math_research.formalization")
                    ), path
                    if folder != "services":
                        assert not node.module.startswith("math_research.services"), path


def test_cli_pipe_preserves_mathematical_unicode(research):
    import subprocess
    import sys

    state, ref = research
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "math_research.cli",
            "-w",
            str(state.parent),
            "ledger",
            "add-definition",
            ref.problem_id,
            "complex domain",
            "z ∈ ℂ",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["definition"] == "z ∈ ℂ"
