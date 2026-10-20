"""Optional stdio MCP transport. Business logic is the same LedgerAdapter/services."""

import argparse
from pathlib import Path

from math_research.mcp.adapter import SCHEMAS, LedgerAdapter


def create_server(state: Path):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError('Install the optional transport with pip install -e ".[mcp]".') from exc
    server = FastMCP("structured-math-research")
    adapter = LedgerAdapter(state)

    # A single explicit dispatcher keeps SDK-generated signatures simple and validated.
    @server.tool()
    def research_tool(name: str, arguments: dict) -> dict:
        """Call a research capability from research_capabilities. No human accept tool."""
        return adapter.call(name, arguments)

    @server.tool()
    def research_capabilities() -> dict:
        """Inspect validated tool argument schemas."""
        return {name: schema.model_json_schema() for name, schema in SCHEMAS.items()}

    return server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    state = args.workspace.resolve()
    if state.name != ".math-research":
        state = state / ".math-research"
    create_server(state).run(transport="stdio")


if __name__ == "__main__":
    main()
