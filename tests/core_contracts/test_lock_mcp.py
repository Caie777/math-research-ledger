"""Actual MCP handler scheduling and bounded lock errors, with synthetic state only."""

import errno
import time
from pathlib import Path

import pytest

pytest.importorskip("mcp")

import anyio  # noqa: E402
import mcp.types as types  # noqa: E402

from math_research.core import atomicio  # noqa: E402
from math_research.ledger import checkpoint  # noqa: E402
from math_research.mcp.server import create_server  # noqa: E402


@pytest.mark.parametrize("failure", ["windows-denial", "contention"])
def test_status_needs_no_writer_lock_and_keeps_mcp_event_loop_responsive(
    research, monkeypatch, failure
):
    state, _ = research
    server = create_server(state.parent)
    original = atomicio.os.open

    def fail(path, *args):
        if Path(path).name == ".checkpoint.lock":
            if failure == "contention":
                raise FileExistsError(errno.EEXIST, "synthetic contention")
            exc = PermissionError(errno.EACCES, "synthetic Windows access denial")
            exc.winerror = 5
            raise exc
        return original(path, *args)

    if failure == "contention":
        (state / ".checkpoint.lock").write_text("synthetic holder")
        original_lock = checkpoint.file_lock
        monkeypatch.setattr(checkpoint, "file_lock", lambda path: original_lock(path, timeout=0.06))
    monkeypatch.setattr(atomicio, "_WINDOWS", True)
    monkeypatch.setattr(atomicio.os, "open", fail)
    state_fingerprint = checkpoint._state_fingerprint

    def slow_fingerprint(root):
        time.sleep(0.04)
        return state_fingerprint(root)

    monkeypatch.setattr(checkpoint, "_state_fingerprint", slow_fingerprint)

    async def run():
        ticks = []
        finished = anyio.Event()

        async def heartbeat():
            while not finished.is_set():
                await anyio.sleep(0.005)
                ticks.append(1)

        start = time.monotonic()
        async with anyio.create_task_group() as group:
            group.start_soon(heartbeat)
            result = await server.request_handlers[types.CallToolRequest](
                types.CallToolRequest(
                    params=types.CallToolRequestParams(name="research_status", arguments={})
                )
            )
            finished.set()
        assert time.monotonic() - start < 3
        assert len(ticks) >= 3, "Read fingerprint IO blocked the MCP event loop"
        reply = result.root
        assert not reply.isError and reply.structuredContent["problems"] == 1

    anyio.run(run)
