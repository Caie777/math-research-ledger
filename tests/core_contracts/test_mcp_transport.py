"""Real stdio subprocesses, isolated synthetic stores; no compiler or human accept."""

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402

from math_research.core.workspace import init_workspace  # noqa: E402
from math_research.ledger.episodes import list_candidates, list_episodes  # noqa: E402
from math_research.ledger.persistence import records  # noqa: E402
from math_research.mcp.adapter import DESCRIPTIONS, MAX_OUTPUT_BYTES, SCHEMAS  # noqa: E402
from math_research.mcp.server import WorkspaceError, resolve_workspace  # noqa: E402
from math_research.services.research import (  # noqa: E402
    add_claim,
    add_definition,
    create_problem,
    get_object,
)
from math_research.services.verification import ExactVerificationService  # noqa: E402
from math_research.verification.models import (  # noqa: E402
    AcceptanceReceipt,
    CheckOutcome,
    ExactCertificate,
)

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts/smr_mcp.py"


def test_episode_preview_and_integrity_error_over_real_stdio(research):
    from math_research.ledger.archive import source_path
    from math_research.services.ingest import ingest_episode

    state, ref = research
    markdown = "## RESULT-1\n\n**Statement**\nSynthetic checkpoint.\n"
    episode = ingest_episode(
        state, ref.problem_id, "test.md", markdown.encode(), provenance="test"
    )["episode"]
    path = source_path(state, episode["archive_path"])
    path.write_bytes(path.read_bytes() + b"tampered")

    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-B", str(LAUNCHER), "--workspace", str(state.parent)],
            env=environment(),
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as client,
        ):
            await client.initialize()
            preview = await client.call_tool(
                "research_ingest_episode",
                {
                    "problem_id": ref.problem_id,
                    "markdown": markdown + "new",
                    "provenance": "test",
                    "dry_run": True,
                },
            )
            assert not preview.isError and preview.structuredContent["can_publish"]
            bad = await client.call_tool(
                "research_get_object", {"ref": f"{ref.problem_id}:episode:{episode['episode_id']}"}
            )
            assert bad.isError and bad.structuredContent["error"]["code"] == "INTEGRITY_ERROR"
            assert len(bad.model_dump_json().encode()) < MAX_OUTPUT_BYTES

    asyncio.run(run())


@pytest.mark.parametrize("root_count", [0, 1, 2])
def test_unpinned_plugin_cannot_use_tool_argument_or_host_roots(research, root_count):
    import mcp.types as types

    state, _ = research
    second = state.parent / "second-root"
    if root_count == 2:
        init_workspace(second)

    async def roots(context):
        return types.ListRootsResult(
            roots=[types.Root(uri=p.as_uri()) for p in [state.parent, second][:root_count]]
        )

    async def run():
        params = StdioServerParameters(
            command=sys.executable, args=["-B", str(LAUNCHER)], cwd=str(ROOT), env=environment()
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(
                read,
                write,
                list_roots_callback=roots if root_count else None,
                read_timeout_seconds=timedelta(seconds=15),
            ) as client,
        ):
            await client.initialize()
            args = {} if root_count else {"workspace": str(state.parent)}
            result = await client.call_tool("research_status", args)
            assert result.isError and result.structuredContent["error"]["code"] == "NO_WORKSPACE"
            wrong = await client.call_tool("research_status", {"workspace": str(state.parent)})
            assert wrong.isError and wrong.structuredContent["error"]["code"] == "NO_WORKSPACE"

    asyncio.run(run())


def environment():
    env = dict(os.environ)
    env.pop("SMR_WORKSPACE", None)
    env.pop("MRL_WORKSPACE", None)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def verification(state, ref):
    class SyntheticChecker:
        def check(self, certificate):
            assert certificate.inputs == {"synthetic_marker": "smoke-only"}
            return CheckOutcome(status="PASSED", summary="Synthetic transport fixture only")

    return ExactVerificationService({"synthetic-mcp-fixture": SyntheticChecker()}).verify(
        state,
        ref,
        ExactCertificate(
            checker="synthetic-mcp-fixture",
            inputs={"synthetic_marker": "smoke-only"},
            scope="Synthetic integration fixture, no mathematical verification",
        ),
    )


def test_sdk_initialization_schemas_and_every_tool(research):
    state, ref = research
    receipt = verification(state, ref)

    async def run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-B", str(LAUNCHER), "--workspace", str(state.parent)],
            cwd=str(ROOT.parent),
            env=environment(),
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write, read_timeout_seconds=timedelta(seconds=15)) as client,
        ):
            initialized = await client.initialize()
            assert initialized.serverInfo.name == "math-research-ledger"
            assert "checkpoint" in initialized.instructions
            assert initialized.capabilities.tools is not None
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == set(SCHEMAS) == set(DESCRIPTIONS)
            for tool in tools:
                assert tool.annotations.readOnlyHint == (
                    tool.name
                    not in {
                        "research_ingest_episode",
                        "research_save_note",
                        "research_request_acceptance",
                        "research_create_problem",
                        "research_update_problem",
                    }
                )
                assert tool.inputSchema == SCHEMAS[tool.name].model_json_schema()
                assert tool.description and "not " in tool.description.lower()
                assert tool.inputSchema["additionalProperties"] is False
            calls = {
                "research_status": {"problem_id": ref.problem_id},
                "research_search": {"query": "synthetic", "problem_id": ref.problem_id},
                "research_get_object": {"ref": ref.qualified_id, "length": 10},
                "research_context_packet": {"ref": ref.qualified_id, "token_budget": 3000},
                "research_review_packet": {"ref": ref.qualified_id},
                "research_stale_report": {"problem_id": ref.problem_id},
                "research_ingest_episode": {
                    "problem_id": ref.problem_id,
                    "markdown": "## Claim: 合成 Unicode\n\n仅作工程测试：z ∈ ℂ，α ≤ β。\n",
                    "provenance": "synthetic SDK test",
                },
                "research_save_note": {
                    "problem_id": ref.problem_id,
                    "kind": "gap",
                    "title": "合成缺口",
                    "body": "仅作 fixture：尚无数学研究。 ∀x ∈ ℂ",
                    "provenance": "synthetic SDK",
                },
                "research_request_acceptance": {
                    "ref": ref.qualified_id,
                    "verification_id": receipt.id,
                },
                "research_create_problem": {
                    "title": "Synthetic new research line",
                    "statement": "Synthetic only.",
                    "primary_target": "Synthetic target.",
                },
                "research_update_problem": {
                    "problem_id": ref.problem_id,
                    "lifecycle_status": "paused",
                },
            }
            responses = {}
            assert len(tools) == 11
            for name, args in calls.items():
                reply = await client.call_tool(name, args)
                assert not reply.isError, (name, reply)
                assert reply.structuredContent is not None
                assert len(reply.model_dump_json().encode()) < MAX_OUTPUT_BYTES
                responses[name] = reply.structuredContent
            assert responses["research_get_object"]["truncated"]
            assert responses["research_context_packet"]["token_estimate"] <= 3000
            assert responses["research_search"]["hits"]
            assert responses["research_create_problem"]["problem_id"] == "PROBLEM-0002"
            assert responses["research_update_problem"]["lifecycle_change"]["to"] == "paused"
            for name in ("research_ingest_episode", "research_save_note"):
                repeated = await client.call_tool(name, calls[name])
                assert repeated.structuredContent["duplicate"]
                assert repeated.structuredContent["candidates"] == responses[name]["candidates"]
                assert repeated.structuredContent["canonical_records_created"] == 0
            again = await client.call_tool(
                "research_request_acceptance", calls["research_request_acceptance"]
            )
            assert again.structuredContent == responses["research_request_acceptance"]
            for name, args in [
                ("research_search", {"query": "x", "limit": "20"}),
                ("research_get_object", {"ref": {"path": "C:\\private"}}),
                ("research_status", {"path": "D:\\outside", "shell": "echo x"}),
                ("research_save_note", {**calls["research_save_note"], "authority": "ACCEPTED"}),
                ("accept", {}),
            ]:
                reply = await client.call_tool(name, args)
                assert reply.isError and reply.structuredContent["error"]["code"]
                assert "Traceback" not in reply.model_dump_json()

    asyncio.run(run())
    assert get_object(state, ref).authority == "CANONICAL"
    assert not records(state, "acceptances", AcceptanceReceipt)
    assert len(list_episodes(state)) == 2
    assert len(list_candidates(state, ref.problem_id)) == 2
    provisional = list_candidates(state, ref.problem_id)[0]
    assert "z ∈ ℂ" in provisional.body


class RawClient:
    """Inspect raw stdout, not a parser that could silently ignore stray lines."""

    def __init__(self, process):
        self.process = process
        self.lines = queue.Queue()
        self.ident = 0

        def read():
            for line in process.stdout:
                self.lines.put(line)

        threading.Thread(target=read, daemon=True).start()

    def send(self, message):
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def request(self, method, params=None):
        self.ident += 1
        self.send({"jsonrpc": "2.0", "id": self.ident, "method": method, "params": params or {}})
        while True:
            line = self.lines.get(timeout=30)
            assert len(line.encode("utf-8")) <= MAX_OUTPUT_BYTES
            message = json.loads(line)
            assert message["jsonrpc"] == "2.0"
            if message.get("id") == self.ident:
                assert "error" not in message, message
                return message["result"]

    def call(self, name, arguments):
        return self.request("tools/call", {"name": name, "arguments": arguments})


@contextmanager
def raw_client(cwd, args=(), env=None, *, module=False):
    entry = ["-m", "math_research.mcp.server"] if module else [str(LAUNCHER)]
    process = subprocess.Popen(
        [sys.executable, "-B", *entry, *map(str, args)],
        cwd=cwd,
        env=environment() if env is None else env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        client = RawClient(process)
        client.request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "synthetic-raw-client", "version": "1"},
            },
        )
        client.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        yield client
    finally:
        process.terminate()
        process.communicate(timeout=10)


@pytest.mark.parametrize("location", ["root", "state", "subdir", "ordinary"])
def test_module_entry_registers_tools_and_binds_exact_dot(research, tmp_path, location):
    state, _ = research
    root = state.parent
    directory = {
        "root": root,
        "state": state,
        "subdir": root / "nested",
        "ordinary": tmp_path / "empty",
    }[location]
    directory.mkdir(exist_ok=True)
    with raw_client(
        directory,
        ["--workspace", "."],
        env={**environment(), "MRL_WORKSPACE": str(root)},
        module=True,
    ) as client:
        assert len(client.request("tools/list")["tools"]) == 11
        result = client.call("research_status", {})
        if location == "root":
            assert not result.get("isError")
            assert result["structuredContent"]["workspace_root"] == str(root)
        else:
            assert result["isError"]
            assert result["structuredContent"]["error"]["code"] == "NO_WORKSPACE"
            assert not (directory / ".math-research-ledger").exists()


def test_resolution_precedence_no_init_and_raw_protocol(tmp_path, research):
    state, ref = research
    other = tmp_path / "其他 workspace with spaces"
    init_workspace(other)
    nested = state.parent / "nested/deep"
    nested.mkdir(parents=True)
    env = {"SMR_WORKSPACE": str(other)}
    assert (
        resolve_workspace(cwd=nested, environ={**env, "MRL_WORKSPACE": str(state.parent)}) == state
    )
    assert resolve_workspace(state.parent, cwd=nested, environ=env) == state
    assert resolve_workspace(cwd=nested, environ=env) == other / ".math-research-ledger"
    assert resolve_workspace(cwd=nested, environ={}) == state
    with pytest.raises(WorkspaceError):
        resolve_workspace(state, environ={})
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(WorkspaceError):
        resolve_workspace(empty, cwd=nested, environ=env)
    # A missing selected path must not silently fall through to a real project.
    with raw_client(nested) as client:
        reply = client.call("research_status", {})
        assert reply["structuredContent"]["state_dir"] == str(state)
    with raw_client(nested, ["--workspace", empty]) as client:
        reply = client.call("research_status", {})
        assert reply["isError"]
        assert reply["structuredContent"]["error"]["code"] == "NO_WORKSPACE"
        assert "--workspace" in reply["structuredContent"]["error"]["action"]
    with raw_client(empty, env={**environment(), "SMR_WORKSPACE": str(other)}) as client:
        reply = client.call("research_status", {})
        assert reply["structuredContent"]["state_dir"] == str(other / ".math-research-ledger")
    assert not (empty / ".math-research-ledger").exists()
    # A synthetic ordinary root must stay closed, even below a valid Ledger.
    # Explicit dot tests startup cwd binding without probing the machine's drive root.
    ordinary = tmp_path / "uninitialized-root"
    ordinary.mkdir()
    with pytest.raises(WorkspaceError):
        resolve_workspace(Path("."), cwd=ordinary, environ={})
    with raw_client(ordinary, ["--workspace", "."]) as client:
        reply = client.call("research_status", {})
        assert reply["isError"]
        assert reply["structuredContent"]["error"]["code"] == "NO_WORKSPACE"
    assert not list(ordinary.iterdir())


def test_ambiguous_ref_bounded_review_and_truncation(research):
    from math_research.core.jsonl import rewrite_jsonl
    from math_research.core.refs import ObjectRef
    from math_research.ledger.dependencies import DependencyRole
    from math_research.ledger.records import store
    from math_research.services.research import link_dependency

    state, ref = research
    second = create_problem(state, "Second synthetic fixture")
    collision = add_claim(state, second.id, "Claim ID collision across synthetic problems")
    rewrite_jsonl(
        store.dossier_dir(state, second.id) / "claims.jsonl",
        [collision.model_copy(update={"id": ref.object_id})],
    )
    definition = add_definition(
        state, ref.problem_id, "Large synthetic input", '合成 ∀α "\\' * 6000
    )
    link_dependency(
        state,
        ref,
        ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=definition.id),
        DependencyRole.DEFINITION,
    )
    with raw_client(state.parent) as client:
        reply = client.call("research_get_object", {"ref": ref.object_id})
        assert reply["isError"] and "ambiguous" in reply["structuredContent"]["error"]["message"]
        reply = client.call("research_review_packet", {"ref": ref.qualified_id})
        assert reply["isError"] and "64 KiB" in reply["structuredContent"]["error"]["message"]
        reply = client.call(
            "research_context_packet", {"ref": ref.qualified_id, "token_budget": 3000}
        )
        assert not reply["isError"]
        packet = reply["structuredContent"]
        assert packet["required_context_truncated"]
        assert packet["token_estimate"] <= 3000
        reply = client.call("research_get_object", {"ref": ref.qualified_id, "length": 8})
        assert not reply["isError"] and reply["structuredContent"]["truncated"]


def test_serialized_sdk_envelope_is_bounded_not_only_adapter_payload(research):
    state, ref = research
    # Adapter JSON fits 64 KiB. Duplicated text + structuredContent and escaping
    # in the MCP result do not; the transport must replace it with a small error.
    add_definition(state, ref.problem_id, "Escape-heavy synthetic fixture", '"\\' * 2500)
    from math_research.mcp.adapter import LedgerAdapter

    value = LedgerAdapter(state).call("research_review_packet", {"ref": ref.qualified_id})
    assert len(json.dumps(value, ensure_ascii=False).encode()) < MAX_OUTPUT_BYTES
    with raw_client(state.parent) as client:
        reply = client.call("research_review_packet", {"ref": ref.qualified_id})
        assert reply["isError"]
        assert reply["structuredContent"]["error"]["code"] == "OUTPUT_LIMIT"


@pytest.mark.parametrize("kind", ["claim", "gap", "failed_attempt", "evidence", "counterexample"])
def test_single_notes_reuse_proposals_without_canonical_writes(research, kind):
    from math_research.ledger.manifest import Ledger
    from math_research.mcp.adapter import LedgerAdapter

    state, ref = research
    adapter = LedgerAdapter(state)
    args = dict(
        problem_id=ref.problem_id,
        kind=kind,
        title="合成 note",
        body="Synthetic fixture only: ∀z ∈ ℂ; no conclusion.",
        provenance="test",
    )
    first = adapter.call("research_save_note", args)
    repeated = adapter.call("research_save_note", args)
    assert repeated["duplicate"] and first["candidates"] == repeated["candidates"]
    assert len(list_candidates(state, ref.problem_id)) == 1
    assert len(list_episodes(state)) == 1
    candidate = first["candidates"][0]
    entry = next(e for e in Ledger(state).objects() if e.ref.object_id == candidate["object_id"])
    assert entry.authority == "PROVISIONAL"
    assert entry.verification == "NOT_CHECKED"
    assert (
        len(
            [
                e
                for e in Ledger(state).objects()
                if e.authority == "CANONICAL" and e.ref.kind != "episode"
            ]
        )
        == 2
    )


def test_import_surface_avoids_cli_and_heavy_research_dependencies():
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            "import sys; import math_research.mcp.server; print('\n'.join(sys.modules))".replace(
                "'\n'", "'\\n'"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    modules = result.stdout.splitlines()
    assert not any(m.startswith(("math_research.cli", "numpy", "sympy", "pypdf")) for m in modules)
