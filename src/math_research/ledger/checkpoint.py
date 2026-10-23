"""Serialized checkpoint publication with durable metadata rollback.

Raw source bytes are append-only and retained even if publication fails. The
archive index and provisional proposal index publish under one writer lock.
MCP reads optimistically validate their entire operation without creating a lock.
An interrupted publication blocks reads until trusted human recovery.
"""

import json
import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash, sha256
from math_research.ledger.records.write_boundary import human_write

_active: ContextVar[Path | None] = ContextVar("checkpoint_state", default=None)
JOURNAL = ".checkpoint-pending.json"
GENERATION = ".checkpoint-generation"
ResultT = TypeVar("ResultT")


class _CheckpointChanged(Exception):
    pass


def guard_checkpoint(state: Path) -> None:
    if _active.get() == state.resolve():
        return
    try:
        (state / JOURNAL).lstat()
    except FileNotFoundError:
        return
    except OSError as exc:
        raise ResearchError(f"Cannot inspect checkpoint journal: {exc}") from exc
    raise ResearchError(
        "Checkpoint publication pending or interrupted; retry after the writer finishes. "
        "If the journal remains, run math-research-ledger ingest recover before continuing."
    )


def _generation(state: Path) -> bytes | None:
    try:
        with (state / GENERATION).open("rb") as stream:
            value = stream.read(33)
    except FileNotFoundError:
        return None  # Legacy state is readable; readers never initialize a marker.
    except OSError as exc:
        raise ResearchError(f"Cannot read checkpoint generation: {exc}") from exc
    if len(value) != 32 or any(c not in b"0123456789abcdef" for c in value):
        raise ResearchError(
            "Invalid checkpoint generation marker; inspect state without repairing it."
        )
    return value


def _state_fingerprint(state: Path) -> str:
    from math_research.ledger.manifest import Ledger

    def unreadable(exc):
        raise ResearchError(f"Cannot fingerprint checkpoint metadata: {exc}") from exc

    # Hash persisted metadata, not parsed defaults (legacy missing timestamps can
    # acquire a different datetime on each load). Existing object versions cover
    # referenced proof/source/artifact bytes and dependency bindings. Unindexed,
    # unreachable retained blobs do not need another full filesystem hash sweep.
    metadata = []
    try:
        for directory, folders, files in os.walk(state, onerror=unreadable):
            folders.sort()
            if any((Path(directory) / name).is_symlink() for name in folders):
                raise ResearchError(
                    "Cannot confirm a checkpoint through redirected metadata directories."
                )
            for name in sorted(files):
                path = Path(directory) / name
                if path.suffix.lower() in {".json", ".jsonl", ".yaml", ".yml"}:
                    metadata.append((path.relative_to(state).as_posix(), sha256(path.read_bytes())))
        workspace = state.parent / "workspace.yaml"
        try:
            metadata.append(("../workspace.yaml", sha256(workspace.read_bytes())))
        except FileNotFoundError:
            pass
    except OSError as exc:
        unreadable(exc)
    versions = [(entry.qualified_id, entry.version) for entry in Ledger(state).objects()]
    return content_hash({"metadata": metadata, "versions": versions})


def _fingerprint(state: Path) -> tuple[bytes | None, str]:
    if not state.is_dir():
        raise ResearchError("No research state; read access never initializes a workspace.")
    guard_checkpoint(state)
    generation = _generation(state)
    try:
        version = _state_fingerprint(state)
    except Exception:
        guard_checkpoint(state)
        if generation != _generation(state):
            raise _CheckpointChanged from None
        raise
    guard_checkpoint(state)
    if generation != _generation(state):
        raise _CheckpointChanged
    return generation, version


def consistent_checkpoint_read(
    state: Path, operation: Callable[[], ResultT], *, attempts: int = 3
) -> ResultT:
    """Replay a *pure*, materialized operation only when its whole read was unstable.

    Content/version fencing detects current-state changes. The writer's durable
    generation also detects ABA: a failed publication can restore identical bytes.
    All concurrent checkpoint writers must use this generation protocol. No read
    creates state, takes a file lock, repairs a journal or persists a fingerprint.
    """
    if attempts < 1:
        raise ValueError("Read attempts must be positive.")
    state = state.resolve()
    if _active.get() == state:
        raise ResearchError("Cannot snapshot inside an active checkpoint publication.")
    for attempt in range(attempts):
        try:
            before = _fingerprint(state)
            try:
                result = operation()
            except Exception:
                if _fingerprint(state) == before:
                    raise  # Preserve stable validation, permission and integrity errors.
            else:
                if _fingerprint(state) == before:
                    return result
        except _CheckpointChanged:
            pass
        if attempt + 1 < attempts:
            time.sleep(0.02)
    raise ResearchError(
        f"Research state changed during read after {attempts} attempts; "
        "no stable checkpoint generation. Retry after publication finishes."
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
            # Never roll this back: even an aborted publication invalidates readers
            # that might have seen its intermediate multi-file state.
            atomic_write_text(state / GENERATION, uuid4().hex)
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
    """Legacy exclusive guard for non-replayable operations (acceptance requests)."""
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
        atomic_write_text(state / GENERATION, uuid4().hex)
        _restore(state, value["files"])
        journal.unlink()
        return {"recovered": True, "raw_sources_retained": True}
