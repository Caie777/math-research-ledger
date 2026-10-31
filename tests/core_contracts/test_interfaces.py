import ast
import json
from importlib.util import resolve_name
from pathlib import Path

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
        adapter.call("research_get_object", {"ref": ref.qualified_id, "path": "../outside"})
    result = adapter.call("research_get_object", {"ref": ref.qualified_id, "length": 10})
    assert len(result["content"]) <= 10 and result["truncated"]
    assert adapter.call("research_search", {"query": "synthetic"})["hits"]


_RUNTIME_LAYERS = ("core", "ledger", "retrieval", "verification", "services")
_FORBIDDEN_RUNTIME_MODULES = (
    "math_research.cli",
    "math_research.mcp",
    "math_research.agent",
    "math_research.app",
    "math_research.formalization",
    "math_research.integrations",
    "mcp",
    "codex",
    "dsh",
    "deepseek_harness",
    "openai",
    "anthropic",
    "integrations",
)


def _forbidden_runtime_imports(source, package, layer):
    imports = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = resolve_name("." * node.level + (node.module or ""), package)
            imports.add(module)
            imports.update(f"{module}.{alias.name}" for alias in node.names)
    forbidden = _FORBIDDEN_RUNTIME_MODULES
    if layer != "services":
        forbidden += ("math_research.services",)
    return {
        module
        for module in imports
        if any(module == prefix or module.startswith(prefix + ".") for prefix in forbidden)
    }


@pytest.mark.parametrize("layer", _RUNTIME_LAYERS)
def test_runtime_independent_import_boundaries(layer):
    root = Path(__file__).resolve().parents[2] / "src" / "math_research"
    assert (root / layer).is_dir()
    for path in (root / layer).rglob("*.py"):
        parts = path.relative_to(root.parent).with_suffix("").parts
        package = ".".join(parts[:-1])
        forbidden = _forbidden_runtime_imports(path.read_text("utf-8"), package, layer)
        assert not forbidden, f"{path}: forbidden runtime imports: {sorted(forbidden)}"


@pytest.mark.parametrize("layer", _RUNTIME_LAYERS)
@pytest.mark.parametrize("module", _FORBIDDEN_RUNTIME_MODULES)
@pytest.mark.parametrize(
    "statement", ["import {module} as adapter", "from {module} import adapter"]
)
def test_import_boundary_guard_rejects_import_and_from(layer, module, statement):
    assert _forbidden_runtime_imports(
        statement.format(module=module), f"math_research.{layer}", layer
    )


@pytest.mark.parametrize("layer", _RUNTIME_LAYERS)
@pytest.mark.parametrize(
    "statement",
    [
        "from math_research import cli as adapter",
        "from math_research import mcp",
        "from .. import cli",
        "from ..mcp import adapter",
        "if False:\n    import codex",
        "def deferred():\n    from dsh import runtime",
    ],
)
def test_import_boundary_guard_rejects_indirect_and_nested_imports(layer, statement):
    assert _forbidden_runtime_imports(statement, f"math_research.{layer}", layer)


@pytest.mark.parametrize("layer", _RUNTIME_LAYERS)
def test_import_boundary_guard_preserves_shared_layers(layer):
    package = f"math_research.{layer}"
    assert not _forbidden_runtime_imports(
        "import json\nfrom math_research.core import errors\nfrom . import helpers", package, layer
    )
    forbidden = _forbidden_runtime_imports(
        "from math_research.services import research", package, layer
    )
    assert bool(forbidden) == (layer != "services")


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
