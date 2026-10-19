"""Maintenance CLI; mathematical research actions are in the Web App."""

import json
from pathlib import Path

import typer

from math_research.core.errors import ResearchError
from math_research.core.paths import resolve_cli_workspace_root
from math_research.core.workspace import init_workspace, workspace_dir

app = typer.Typer(help="Structured memory and retrieval for mathematical research.")


def state_dir(path: Path) -> Path:
    root = resolve_cli_workspace_root(path)
    if root is None:
        raise typer.BadParameter("Initialize a workspace with math-research init.")
    return workspace_dir(root)


@app.command()
def init(path: Path = typer.Argument(Path("."))) -> None:
    """Initialize a research workspace without overwriting existing files."""
    created = init_workspace(path)
    typer.echo(f"Workspace ready: {workspace_dir(path.resolve())} ({len(created)} files created)")


@app.command()
def serve(
    path: Path = typer.Argument(Path(".")), host: str = "127.0.0.1", port: int = 8000
) -> None:
    """Serve the local API and the built React application."""
    import uvicorn

    from math_research.app.api.server import create_app

    uvicorn.run(create_app(state_dir(path)), host=host, port=port)


@app.command()
def status(path: Path = typer.Argument(Path("."))) -> None:
    """Read Problem and Research run counts; never starts a model."""
    from math_research.memory.records import store

    state = state_dir(path)
    typer.echo(f"Problems: {len(store.list_dossiers(state))}")
    typer.echo(f"Research runs: {len(list((state / 'research_runs').glob('*/run.json')))}")


@app.command()
def research_progress(run_id: str, path: Path = typer.Argument(Path("."))) -> None:
    """Read durable ResearchRunProgress JSON; no model, repair, or workspace writes."""
    from math_research.agent.progress import read_progress
    from math_research.agent.runtime import read_run, run_directory

    state = state_dir(path)
    run = read_run(state, run_id)
    typer.echo(read_progress(run_directory(state, run_id), run).model_dump_json(indent=2))


@app.command()
def doctor(path: Path = typer.Argument(Path("."))) -> None:
    """Inspect readiness and stored records without repairing them."""
    from math_research.app.maintenance.workspace import system_health

    typer.echo(json.dumps(system_health(state_dir(path)), ensure_ascii=False, indent=2))


@app.command()
def migrate(path: Path = typer.Argument(Path("."))) -> None:
    """Migrate the previous state root, retaining its immutable local backup."""
    from math_research.app.maintenance.migration import migrate_workspace

    try:
        result = migrate_workspace(path)
    except ResearchError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Migrated {result['file_count']} files to .math-research; backup retained.")


@app.command(name="export")
def export_snapshot(output: Path, path: Path = typer.Argument(Path("."))) -> None:
    """Export a sanitized workspace snapshot to a new file."""
    from math_research.app.maintenance.workspace import workspace_snapshot

    raw = workspace_snapshot(state_dir(path))
    with output.open("xb") as stream:
        stream.write(raw)
    typer.echo(str(output))


@app.command()
def verify(snapshot: Path) -> None:
    """Validate a snapshot without restoring or writing research state."""
    from math_research.app.maintenance.workspace import verify_snapshot

    typer.echo(verify_snapshot(snapshot.read_bytes()))


if __name__ == "__main__":
    app()
