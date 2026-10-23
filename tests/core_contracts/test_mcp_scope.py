"""Session authority is deployment input, never model-supplied workspace input."""

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytest.importorskip("mcp")

import anyio  # noqa: E402
import mcp.types as types  # noqa: E402

from math_research.cli.main import app  # noqa: E402
from math_research.core.workspace import init_workspace  # noqa: E402
from math_research.mcp import server as transport  # noqa: E402
from math_research.mcp.adapter import SCHEMAS  # noqa: E402
from math_research.services.research import add_claim, create_problem  # noqa: E402


def call(server, name="research_status", **arguments):
    async def run():
        reply = await server.request_handlers[types.CallToolRequest](
            types.CallToolRequest(
                params=types.CallToolRequestParams(name=name, arguments=arguments)
            )
        )
        return reply.root

    return anyio.run(run)


@pytest.fixture
def second(tmp_path_factory):
    root = tmp_path_factory.mktemp("second-ledger")
    init_workspace(root)
    state = root / ".math-research-ledger"
    problem = create_problem(state, "PRIVATE_SECOND_LEDGER_SENTINEL")
    claim = add_claim(state, problem.id, "PRIVATE_SECOND_CLAIM_SENTINEL")
    return root, f"{problem.id}:claim:{claim.id}"


@pytest.mark.parametrize("form", ["omitted", "absolute", "relative", "dotdot", "trailing", "case"])
def test_pinned_root_accepts_only_equivalent_paths(research, form):
    state, _ = research
    root = state.parent
    if form == "case" and os.name != "nt":
        pytest.skip("Windows path/drive case semantics")
    forms = {
        "absolute": str(root),
        "relative": ".",
        "dotdot": str(root / "unused" / ".."),
        "trailing": str(root) + os.sep,
        "case": str(root).swapcase(),
    }
    result = call(
        transport.create_server(root), **({} if form == "omitted" else {"workspace": forms[form]})
    )
    assert not result.isError and result.structuredContent["workspace_root"] == str(root)


@pytest.mark.parametrize("form", ["sibling", "parent", "child", "escape", "state", "nul"])
def test_other_roots_are_rejected_before_ledger_inspection(research, second, monkeypatch, form):
    state, _ = research
    root, _ = second
    child = state.parent / "child-ledger"
    init_workspace(child)
    server = transport.create_server(state.parent)
    paths = {
        "sibling": str(root),
        "parent": str(state.parent.parent),
        "child": str(child),
        "escape": "../" + root.name,
        "state": str(state),
        "nul": "bad\x00path",
    }
    monkeypatch.setattr(
        transport, "LedgerAdapter", lambda *a: pytest.fail("Out-of-scope Ledger was opened")
    )
    monkeypatch.setattr(
        transport, "resolve_workspace", lambda *a: pytest.fail("Tool expanded startup scope")
    )
    result = call(server, workspace=paths[form])
    assert result.isError
    assert result.structuredContent["error"]["code"] == "WORKSPACE_OUT_OF_SCOPE"
    payload = result.model_dump_json()
    assert str(root) not in payload and "PRIVATE_SECOND" not in payload
    assert "bad" not in result.structuredContent["error"]["message"]


@pytest.mark.parametrize("name", list(SCHEMAS))
def test_scope_check_covers_all_nine_tools_without_reading_or_writing(
    research, second, monkeypatch, name
):
    state, ref = research
    server = transport.create_server(state.parent)
    monkeypatch.setattr(
        transport, "LedgerAdapter", lambda *a: pytest.fail("Out-of-scope tool reached services")
    )
    args = {"workspace": str(second[0])}
    if name in {"research_get_object", "research_context_packet", "research_review_packet"}:
        args["ref"] = ref.qualified_id
    elif name == "research_request_acceptance":
        args.update(ref=ref.qualified_id, verification_id="synthetic")
    elif name == "research_search":
        args["query"] = "synthetic"
    elif name == "research_ingest_episode":
        args.update(problem_id=ref.problem_id, markdown="Synthetic.", provenance="fixture")
    elif name == "research_save_note":
        args.update(
            problem_id=ref.problem_id,
            kind="gap",
            title="Synthetic",
            body="Synthetic only.",
            provenance="fixture",
        )
    result = call(server, name, **args)
    assert result.isError and result.structuredContent["error"]["code"] == "WORKSPACE_OUT_OF_SCOPE"


def alias(link: Path, target: Path):
    if os.name == "nt":
        # Junctions require no administrator/symlink privilege; synthetic paths only.
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
    else:
        link.symlink_to(target, target_is_directory=True)


def remove_alias(link: Path):
    if os.name == "nt":
        link.rmdir()  # Remove only the junction, never recurse into the target.
    else:
        link.unlink()


@pytest.mark.parametrize("same", [True, False])
def test_resolved_directory_alias_obeys_exact_root_pin(research, second, same):
    state, _ = research
    link = state.parent / "alias"
    alias(link, state.parent if same else second[0])
    try:
        result = call(transport.create_server(state.parent), workspace=str(link))
        assert result.isError == (not same)
        if same:
            assert result.structuredContent["workspace_root"] == str(state.parent)
        else:
            assert result.structuredContent["error"]["code"] == "WORKSPACE_OUT_OF_SCOPE"
    finally:
        remove_alias(link)


def test_retargeting_startup_alias_does_not_rebind_session(research, second):
    state, _ = research
    link = state.parent / "startup-alias"
    alias(link, state.parent)
    try:
        server = transport.create_server(link)
        remove_alias(link)
        alias(link, second[0])
        assert call(server).structuredContent["workspace_root"] == str(state.parent)
        assert call(server, workspace=str(link)).structuredContent["error"]["code"] == (
            "WORKSPACE_OUT_OF_SCOPE"
        )
    finally:
        remove_alias(link)


def test_redirected_state_cannot_change_pinned_workspace(second, tmp_path_factory):
    root = tmp_path_factory.mktemp("redirected-state")
    link = root / ".math-research-ledger"
    alias(link, second[0] / ".math-research-ledger")
    try:
        result = call(transport.create_server(root))
        assert result.isError and result.structuredContent["error"]["code"] == "NO_WORKSPACE"
        assert "PRIVATE_SECOND" not in result.model_dump_json()
    finally:
        remove_alias(link)


def test_startup_flag_and_environment_are_captured_once(research, second, monkeypatch):
    state, _ = research
    monkeypatch.setenv("MRL_WORKSPACE", str(second[0]))
    explicit = transport.create_server(state.parent)
    monkeypatch.setenv("MRL_WORKSPACE", str(state.parent))
    environment = transport.create_server()
    monkeypatch.chdir(state.parent / "..")
    monkeypatch.setenv("MRL_WORKSPACE", str(second[0]))
    for server in (explicit, environment):
        assert call(server).structuredContent["workspace_root"] == str(state.parent)
        assert call(server, workspace=str(second[0])).structuredContent["error"]["code"] == (
            "WORKSPACE_OUT_OF_SCOPE"
        )


def test_startup_relative_flag_is_anchored_once(research, second, monkeypatch):
    state, _ = research
    monkeypatch.chdir(state.parent.parent)
    server = transport.create_server(Path(state.parent.name))
    monkeypatch.chdir(second[0])
    assert call(server, workspace=".").structuredContent["workspace_root"] == str(state.parent)


def test_missing_startup_scope_stays_closed_even_if_model_supplies_valid_ledger(
    research, second, monkeypatch
):
    # Use an unrelated directory, not an ancestor/child discoverable inside the Ledger.
    empty = second[0].parent / ("ordinary-project-" + second[0].name)
    empty.mkdir()
    monkeypatch.delenv("MRL_WORKSPACE", raising=False)
    monkeypatch.delenv("SMR_WORKSPACE", raising=False)
    monkeypatch.chdir(empty)
    server = transport.create_server()
    init_workspace(empty)  # Adding state later does not authorize an already-started session.
    for args in ({}, {"workspace": str(research[0].parent)}, {"workspace": str(second[0])}):
        result = call(server, **args)
        assert result.isError and result.structuredContent["error"]["code"] == "NO_WORKSPACE"


def test_cli_explicit_other_workspace_remains_unrestricted(research, second):
    server = transport.create_server(research[0].parent)
    result = call(server, workspace=str(second[0]))
    assert result.structuredContent["error"]["code"] == "WORKSPACE_OUT_OF_SCOPE"
    result = CliRunner().invoke(app, ["--workspace", str(second[0]), "ledger", "show", second[1]])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["object"]["qualified_id"] == second[1]
    assert "PRIVATE_SECOND_CLAIM_SENTINEL" in result.output
