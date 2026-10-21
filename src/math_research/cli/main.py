"""CLI adapters only; domain decisions and writes live in deterministic services."""

import json
import sys
from pathlib import Path

import typer
from pydantic import BaseModel

from math_research.core.config import workspace_config
from math_research.core.errors import ResearchError
from math_research.core.paths import (
    STATE_DIRNAMES,
    WORKSPACE_DIRNAME,
    find_workspace_root,
    state_at,
)
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.records.models import Definition
from math_research.services import (
    acceptance,
    ingest,
    research,
    retrieval,
    review,
    stale,
    verification,
)

app = typer.Typer(
    help="MathResearch Ledger: persistent research state, context and verification. "
    "Legacy compatibility aliases: smr, math-research."
)
ledger_app = typer.Typer(help="Typed objects and qualified references.")
context_app = typer.Typer()
ingest_app = typer.Typer()
verify_app = typer.Typer()
formal_app = typer.Typer()
acceptance_app = typer.Typer()
stale_app = typer.Typer()
review_app = typer.Typer()
for name, child in [
    ("ledger", ledger_app),
    ("context", context_app),
    ("ingest", ingest_app),
    ("verify", verify_app),
    ("formal", formal_app),
    ("acceptance", acceptance_app),
    ("stale", stale_app),
    ("review", review_app),
]:
    app.add_typer(child, name=name)


def emit(value):
    from math_research.retrieval.packet import ContextPacket

    if isinstance(value, ContextPacket):
        typer.echo(value.model_dump_json())
        return
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    typer.echo(
        json.dumps(value, ensure_ascii=False, indent=2, default=lambda v: v.model_dump(mode="json"))
    )


@app.callback()
def main(ctx: typer.Context, workspace: Path = typer.Option(Path("."), "--workspace", "-w")):
    root = workspace.resolve()
    if root.name in STATE_DIRNAMES:
        root = root.parent
    if ctx.invoked_subcommand not in {"init", "migrate"}:
        root = find_workspace_root(root) or root
    ctx.obj = (
        root / WORKSPACE_DIRNAME
        if ctx.invoked_subcommand == "migrate"
        else state_at(root) or root / WORKSPACE_DIRNAME
    )
    workspace_config(ctx.obj.parent)


def state(ctx):
    return ctx.obj


def ref(value):
    try:
        return ObjectRef.parse(value)
    except ValueError as exc:
        raise typer.BadParameter("Use problem_id:kind:object_id (or _global:kind:id).") from exc


@app.command()
def init(ctx: typer.Context):
    emit(research.initialize(state(ctx)))


@app.command()
def migrate(ctx: typer.Context, from_workspace: Path | None = None, rollback: bool = False):
    """Explicit offline state-directory migration; preserves corpus bytes and provenance."""
    from math_research.core.migration import migrate_workspace, rollback_migration

    root = state(ctx).parent
    emit(rollback_migration(root) if rollback else migrate_workspace(from_workspace or root, root))


@app.command()
def status(ctx: typer.Context):
    emit(research.status(state(ctx)))


@ingest_app.command("recover")
def recover_ingest(ctx: typer.Context):
    """Roll back interrupted checkpoint metadata; retain original raw source bytes."""
    from math_research.ledger.checkpoint import recover_checkpoint

    emit(recover_checkpoint(state(ctx)))


@ledger_app.command("list")
def ledger_list(ctx: typer.Context, problem: str | None = None):
    emit(research.list_objects(state(ctx), problem))


@ledger_app.command("show")
def ledger_show(ctx: typer.Context, reference: str):
    emit(research.get_object(state(ctx), ref(reference)))


@ledger_app.command("create-problem")
def create_problem(ctx: typer.Context, title: str, statement: str):
    emit(research.create_problem(state(ctx), title, statement))


@ledger_app.command("history")
def object_history(ctx: typer.Context, reference: str):
    emit(research.history(state(ctx), ref(reference)))


@ledger_app.command("add-claim")
def add_claim(ctx: typer.Context, problem: str, statement: str):
    emit(research.add_claim(state(ctx), problem, statement))


@ledger_app.command("add-definition")
def add_definition(ctx: typer.Context, problem: str, term: str, definition: str):
    emit(research.add_definition(state(ctx), problem, term, definition))


@ledger_app.command("revise-definition")
def revise_definition(ctx: typer.Context, reference: str, definition: str):
    target = ref(reference)
    old = research.get_object(state(ctx), target)
    if target.kind != "definition":
        raise typer.BadParameter("Expected definition reference.")
    value = Definition.model_validate(old.object.record).model_copy(
        update={"definition": definition}
    )
    emit(research.update_definition(state(ctx), target.problem_id, value))


@ledger_app.command("link")
def link(ctx: typer.Context, dependent: str, target: str, role: DependencyRole):
    emit(research.link_dependency(state(ctx), ref(dependent), ref(target), role))


@app.command("search")
def search(ctx: typer.Context, query: str, problem: str | None = None, limit: int = 20):
    emit(retrieval.search_research(state(ctx), query, problem_id=problem, limit=limit))


@context_app.command("export")
def export_context(
    ctx: typer.Context,
    reference: str,
    budget: int = 8000,
    query: str = "",
    purpose: str = "CONTINUE_RESEARCH",
):
    emit(
        retrieval.export_context_packet(
            state(ctx), ref(reference), token_budget=budget, query=query, purpose=purpose
        )
    )


@ingest_app.command("episode")
def ingest_episode(
    ctx: typer.Context,
    problem: str,
    file: Path,
    provenance: str = typer.Option(...),
    preview: bool = False,
):
    emit(ingest.ingest_file(state(ctx), problem, file, provenance=provenance, preview=preview))


@ingest_app.command("review")
def review_candidate(
    ctx: typer.Context, problem: str, candidate_id: str, decision: str, edits: Path | None = None
):
    emit(ingest.review_from_file(state(ctx), problem, candidate_id, decision, edits))


@ingest_app.command("source")
def ingest_source(ctx: typer.Context, problem: str, file: Path):
    emit(ingest.ingest_source_file(state(ctx), problem, file))


@verify_app.command("show")
def show_verification(ctx: typer.Context, verification_id: str):
    emit(verification.get_receipt(state(ctx), verification_id))


@formal_app.command("freeze")
def formal_freeze(
    ctx: typer.Context,
    reference: str,
    ident: str,
    repo: Path,
    statement: str,
    module: str,
    declaration: str,
    expected_type: str,
    local_definition: list[str] = typer.Option([]),
    version: int = 1,
    reason: str | None = None,
):
    emit(
        verification.freeze_statement(
            state(ctx),
            ref(reference),
            ident=ident,
            repo=repo,
            statement=statement,
            module=module,
            declaration=declaration,
            expected_type=expected_type,
            local_definitions=tuple(local_definition),
            version=version,
            reason=reason,
        )
    )


@formal_app.command("check")
def formal_check(
    ctx: typer.Context,
    reference: str,
    lake: Path = typer.Option(...),
    elan_home: Path = typer.Option(...),
):
    emit(verification.run_formal_check(state(ctx), ref(reference), lake=lake, elan_home=elan_home))


@acceptance_app.command("request")
def request_acceptance(ctx: typer.Context, reference: str, verification_id: str):
    emit(acceptance.request_acceptance(state(ctx), ref(reference), verification_id))


@acceptance_app.command("pending")
def pending(ctx: typer.Context):
    emit(acceptance.pending_acceptances(state(ctx)))


@acceptance_app.command("accept")
def human_accept(
    ctx: typer.Context,
    request_id: str,
    actor: str = typer.Option(...),
    rationale: str = typer.Option(...),
    correspondence: str | None = None,
):
    """Trusted human operator only; not exposed by MCP. Automated scope is refused."""
    emit(
        acceptance.accept(
            state(ctx), request_id, actor=actor, rationale=rationale, correspondence=correspondence
        )
    )


@stale_app.command("report")
def stale_report(ctx: typer.Context, problem: str | None = None):
    emit(stale.stale_report(state(ctx), problem))


@review_app.command("packet")
def review_packet(ctx: typer.Context, reference: str):
    emit(review.prepare_review(state(ctx), ref(reference)))


@review_app.command("record")
def review_record(ctx: typer.Context, file: Path):
    emit(review.ingest_report_file(state(ctx), file))


def run():
    for stream in (sys.stdout, sys.stderr):
        configure = getattr(stream, "reconfigure", None)
        if configure is not None:
            configure(encoding="utf-8")
    try:
        app()
    except (ResearchError, ValueError, OSError) as exc:
        typer.echo(str(exc), err=True)
        raise SystemExit(2) from None
