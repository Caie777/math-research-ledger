"""Optional stdio transport; stdout is reserved exclusively for JSON-RPC."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError

from math_research import __version__
from math_research.core.errors import IntegrityError, ResearchError
from math_research.core.paths import state_at
from math_research.mcp.adapter import DESCRIPTIONS, MAX_OUTPUT_BYTES, SCHEMAS, LedgerAdapter

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """MathResearch Ledger persists research state across harness sessions.
This server is pinned to one workspace at startup. Omit workspace in tool calls;
the optional compatibility field can only assert the same resolved workspace root.
Tool arguments never authorize another workspace. If no scope is configured, ask
the operator to restart with --workspace or MRL_WORKSPACE; do not search other roots.
When continuing long-horizon research, inspect research_status first. Before substantial
work on an existing Problem, obtain research_context_packet and respect missing context.
Search hits are relevance candidates, not evidence or trusted premises: inspect exact
object/version/freshness/authority/verification before relying on them.
Research hot paths stay light: consolidate a meaningful checkpoint with
research_ingest_episode. Separate Confirmed Research Increment (typed state_delta) from
Next Research Directions, which are always advisory. Use research_save_note sparingly
for one important isolated claim, gap, failure or evidence; never persist every chat turn.
Store broadly, retrieve selectively: retain raw Episodes, proof bodies, failures and history.
The harness owns the workspace, the user owns ordinary files, and Ledger owns only
.math-research-ledger/. Do not directly edit private state or reorganize ordinary files.
Never stage, commit, push or select research publication on the user's behalf.
Soft review is advisory. Checked != accepted; canonical != verified. Human acceptance
is absent from this MCP surface: a workflow boundary, not authentication or sandboxing
against arbitrary local code or filesystem access. Stale is derived current state; preserve
historical receipts. Missing workspace requires explicit human initialization, never auto-init.
Register new research lines only with research_create_problem, not unknown Episode IDs.
Problem active/paused/closed is project lifecycle, never verification or human acceptance.
Changing statement/primary_target requires explicit revision_kind=semantic; preview first.
"""


class WorkspaceError(ResearchError):
    pass


class WorkspaceScopeError(WorkspaceError):
    pass


def resolve_workspace(
    workspace: Path | None = None,
    *,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Explicit sources are exact roots; absent those, discover cwd/ancestors; never init."""
    env = os.environ if environ is None else environ
    here = Path.cwd() if cwd is None else cwd
    selected = (
        workspace if workspace is not None else env.get("MRL_WORKSPACE", env.get("SMR_WORKSPACE"))
    )
    if selected is not None:
        root = Path(selected).expanduser()
        if not root.is_absolute():
            root = here / root
        root = root.resolve()
        state = state_at(root)
        # state_at also accepts state-directory aliases for human/legacy callers.
        # Explicit MCP authority names a workspace root, never its parent's state.
        if state is not None and state.parent == root:
            return state
        raise WorkspaceError(
            "Selected workspace has no .math-research-ledger directory (or legacy state)."
        )
    for root in (here.resolve(), *here.resolve().parents):
        state = state_at(root)
        if state is not None:
            return state
    raise WorkspaceError("No research workspace found in server cwd or its ancestors.")


def create_server(workspace: Path | None = None):
    try:
        import mcp.types as types
        from mcp.server.lowlevel import Server
    except ImportError as exc:
        raise RuntimeError('Install the optional transport with pip install -e ".[mcp]".') from exc

    server = Server("math-research-ledger", version=__version__, instructions=SERVER_INSTRUCTIONS)
    # Capture deployment authority once, never from model arguments or mutable
    # per-call cwd/environment. Host roots are not a scope source in this version.
    try:
        pinned_state = resolve_workspace(workspace)
        if pinned_state.resolve() != pinned_state:
            raise WorkspaceError("Research state redirects outside the startup workspace.")
        scope_error = ""
    except ResearchError as exc:
        pinned_state = None
        scope_error = str(exc)

    def client_workspace(requested: str | None) -> Path:
        if pinned_state is None:
            raise WorkspaceError(scope_error)
        if requested is not None:
            try:
                path = Path(requested).expanduser()
                if not path.is_absolute():
                    path = pinned_state.parent / path
                matches = path.resolve() == pinned_state.parent
            except (OSError, RuntimeError, ValueError):
                matches = False
            if not matches:
                # Do not inspect the requested Ledger, echo its path or reveal content.
                raise WorkspaceScopeError("workspace does not match the pinned session root.")
        return pinned_state

    def result(payload: dict, *, error: bool = False):
        import json

        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))],
            structuredContent=payload,
            isError=error,
        )

    def failure(code: str, message: str, action: str, **details):
        return result(
            {"error": {"code": code, "message": message[:600], "action": action, **details}},
            error=True,
        )

    @server.list_tools()
    async def list_tools():
        writes = {
            "research_ingest_episode",
            "research_save_note",
            "research_request_acceptance",
            "research_create_problem",
            "research_update_problem",
        }
        return [
            types.Tool(
                name=name,
                description=DESCRIPTIONS[name],
                inputSchema=schema.model_json_schema(),
                annotations=types.ToolAnnotations(
                    readOnlyHint=name not in writes,
                    destructiveHint=False,
                    idempotentHint=name != "research_create_problem",
                    openWorldHint=False,
                ),
            )
            for name, schema in SCHEMAS.items()
        ]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict):
        # Validate ourselves to return machine-readable, bounded errors without
        # SDK tracebacks or Pydantic's echoed raw input values.
        if name not in SCHEMAS:
            return failure(
                "UNKNOWN_TOOL", "Tool is not exposed; MCP cannot accept.", "Use tools/list."
            )
        try:
            args = SCHEMAS[name].model_validate(arguments)
            state = client_workspace(args.workspace)
            import anyio

            # Deterministic services use filesystem locks. Keep their bounded
            # waits and IO off the stdio event loop (including under contention).
            value = await anyio.to_thread.run_sync(LedgerAdapter(state).call, name, arguments)
            output = result(value)
            # Include BOTH protocol representations, escaping and SDK fields.
            # Reserve 1 KiB for the JSON-RPC envelope (normal host request IDs).
            if len(output.model_dump_json(by_alias=True).encode("utf-8")) > MAX_OUTPUT_BYTES - 1024:
                return failure(
                    "OUTPUT_LIMIT",
                    "Serialized tool result exceeds the 64 KiB output bound.",
                    "Reduce limit, token_budget or length; use paginated object windows.",
                )
            return output
        except WorkspaceScopeError as exc:
            return failure(
                "WORKSPACE_OUT_OF_SCOPE",
                str(exc),
                "Omit workspace or use the pinned root. A different workspace requires an "
                "operator-configured server session.",
            )
        except WorkspaceError as exc:
            return failure(
                "NO_WORKSPACE",
                str(exc),
                "Restart with --workspace ABSOLUTE_ROOT, set MRL_WORKSPACE before startup, or "
                "start inside an existing research project. Tool workspace and MCP roots cannot "
                "grant scope. Initialize explicitly with math-research-ledger init if intended.",
            )
        except ValidationError as exc:
            return failure(
                "INVALID_ARGUMENTS",
                "Tool arguments do not match its schema.",
                "Use tools/list; ref is a string such as PROBLEM-0001:claim:CLAIM-0001.",
                fields=[
                    {"field": str(e["loc"])[:120], "message": e["msg"][:200]}
                    for e in exc.errors(
                        include_input=False, include_context=False, include_url=False
                    )[:8]
                ],
            )
        except IntegrityError as exc:
            return failure(
                "INTEGRITY_ERROR",
                str(exc),
                "Inspect the original archive; do not update digests or repair automatically.",
            )
        except (ResearchError, ValueError) as exc:
            return failure(
                "RESEARCH_ERROR",
                str(exc),
                "Check research_status and qualified ref; reduce budget/window if oversized. "
                "Human acceptance is available only through the trusted human CLI.",
            )
        except Exception as exc:
            logger.error("Research tool failed: %s", type(exc).__name__)
            return failure(
                "INTERNAL_ERROR",
                "Research service could not complete this request.",
                "Inspect server stderr and workspace integrity; do not edit state to bypass gates.",
            )

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)  # stderr only
    import anyio
    from mcp.server.stdio import stdio_server

    async def run():
        server = create_server(args.workspace)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(run)


if __name__ == "__main__":
    main()
