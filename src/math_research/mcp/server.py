"""Optional stdio transport; stdout is reserved exclusively for JSON-RPC."""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote, urlparse

from pydantic import ValidationError

from math_research import __version__
from math_research.core.errors import ResearchError
from math_research.core.paths import state_at
from math_research.mcp.adapter import DESCRIPTIONS, MAX_OUTPUT_BYTES, SCHEMAS, LedgerAdapter

logger = logging.getLogger(__name__)

SERVER_INSTRUCTIONS = """MathResearch Ledger persists research state across harness sessions.
Include workspace=<current harness absolute workspace root> in tool calls when known.
Some plugin hosts start stdio in PLUGIN_ROOT and do not supply MCP roots. This explicit
request scope then binds the same existing ledger without hardcoded per-user paths.
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
Soft review is advisory. Checked != accepted; canonical != verified. Models cannot grant
themselves authority. Acceptance is human-only. Stale is derived current state; preserve
historical receipts. Missing workspace requires explicit human initialization, never auto-init.
"""


class WorkspaceError(ResearchError):
    pass


def resolve_workspace(
    workspace: Path | None = None,
    *,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Explicit flag > MRL_WORKSPACE > legacy SMR_WORKSPACE > cwd; never initialize."""
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
        if state is not None:
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

    async def client_workspace(requested: str | None) -> Path:
        # Portable plugin hosts can launch stdio in PLUGIN_ROOT. MCP roots are
        # supplied by the harness and bind this request to its actual workspace.
        if (
            workspace is not None
            or os.environ.get("MRL_WORKSPACE")
            or os.environ.get("SMR_WORKSPACE")
        ):
            return resolve_workspace(workspace)
        session = server.request_context.session
        params = session.client_params
        roots = (
            (await session.list_roots()).roots
            if params and params.capabilities.roots is not None
            else []
        )
        if roots:
            paths = []
            for root in roots:
                uri = urlparse(str(root.uri))
                if uri.scheme != "file" or uri.netloc not in {"", "localhost"}:
                    continue
                value = unquote(uri.path)
                if os.name == "nt" and len(value) > 2 and value[0] == "/" and value[2] == ":":
                    value = value[1:]
                paths.append(Path(value))
            if len(paths) == 1:
                return resolve_workspace(paths[0])
            if len(paths) > 1:
                raise WorkspaceError(
                    "Multiple harness roots; select one with MRL_WORKSPACE explicitly."
                )
        if requested is not None:
            path = Path(requested).expanduser()
            if not path.is_absolute():
                raise WorkspaceError(
                    "workspace must be the current harness absolute workspace root."
                )
            return resolve_workspace(path)
        return resolve_workspace()

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
        writes = {"research_ingest_episode", "research_save_note", "research_request_acceptance"}
        return [
            types.Tool(
                name=name,
                description=DESCRIPTIONS[name],
                inputSchema=schema.model_json_schema(),
                annotations=types.ToolAnnotations(
                    readOnlyHint=name not in writes,
                    destructiveHint=False,
                    idempotentHint=True,
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
            state = await client_workspace(args.workspace)
            value = LedgerAdapter(state).call(name, arguments)
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
        except WorkspaceError as exc:
            return failure(
                "NO_WORKSPACE",
                str(exc),
                "Pass --workspace ABSOLUTE_ROOT, set MRL_WORKSPACE, or start inside an existing "
                "research project. Initialize explicitly with math-research-ledger init "
                "if intended.",
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
