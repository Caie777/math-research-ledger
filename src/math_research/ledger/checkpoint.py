"""Serialized checkpoint publication with durable metadata rollback.

Raw source bytes are append-only and retained even if publication fails. The
archive index and provisional proposal index publish together behind the MCP
read lock. An interrupted publication blocks reads until trusted human recovery.
"""

import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError
from math_research.ledger.records.write_boundary import human_write

_active: ContextVar[Path | None] = ContextVar("checkpoint_state", default=None)
JOURNAL = ".checkpoint-pending.json"


def guard_checkpoint(state: Path) -> None:
    if (state / JOURNAL).exists() and _active.get() != state.resolve():
        raise ResearchError(
            "Interrupted checkpoint; run math-research-ledger ingest recover before continuing."
        )


def _restore(state: Path, files: dict) -> None:
    for relative, previous in files.items():
        path = (state / relative).resolve()
        parts = Path(relative).parts
        allowed = relative == "research_archive/index.jsonl" or (
            len(parts) == 5
            and parts[0] == "problems"
            and parts[2:] == ("archive", "episodes", "candidates.jsonl")
        )
        if not allowed or not path.is_relative_to(state.resolve()):
            raise ResearchError("Invalid checkpoint journal path; inspect manually.")
        if previous is None:
            path.unlink(missing_ok=True)
        elif not path.is_file() or path.read_bytes() != bytes.fromhex(previous):
            atomic_write_text(path, bytes.fromhex(previous).decode("utf-8"))


@contextmanager
def checkpoint_transaction(state: Path, problem_id: str):
    from math_research.ledger.records import store

    store.require_dossier(state, problem_id)
    with file_lock(state / ".checkpoint"):
        guard_checkpoint(state)
        paths = [
            state / "research_archive/index.jsonl",
            store.dossier_dir(state, problem_id) / "archive/episodes/candidates.jsonl",
        ]
        before = {
            p.relative_to(state).as_posix(): p.read_bytes().hex() if p.exists() else None
            for p in paths
        }
        journal = state / JOURNAL
        atomic_write_text(journal, json.dumps({"files": before}))
        token = _active.set(state.resolve())
        try:
            yield
        except BaseException:
            _restore(state, before)
            journal.unlink()
            raise
        else:
            journal.unlink()
        finally:
            _active.reset(token)


@contextmanager
def checkpoint_read(state: Path):
    if not state.is_dir():
        raise ResearchError("No research state; read access never initializes a workspace.")
    with file_lock(state / ".checkpoint"):
        guard_checkpoint(state)
        yield


@human_write
def recover_checkpoint(state: Path) -> dict:
    """Recovery is an explicit trusted-human CLI action, never an MCP tool."""
    if not state.is_dir():
        raise ResearchError("No research state; recovery never initializes a workspace.")
    with file_lock(state / ".checkpoint"):
        journal = state / JOURNAL
        if not journal.is_file():
            return {"recovered": False}
        value = json.loads(journal.read_text("utf-8"))
        _restore(state, value["files"])
        journal.unlink()
        return {"recovered": True, "raw_sources_retained": True}
