"""Additive immutable record versions. Existing dossier layouts are unchanged."""

from pathlib import Path

from pydantic import BaseModel

from math_research.core.atomicio import file_lock
from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash
from math_research.core.jsonl import append_jsonl, read_jsonl


def ledger_path(state: Path, name: str) -> Path:
    if name not in {"dependencies", "formal_bundles", "verifications", "review_reports", "acceptance_requests", "acceptances"}:
        raise ResearchError("Unknown ledger collection.")
    base = state.resolve() / "ledger"
    path = base / (name + ".jsonl")
    if base.resolve() != base or path.resolve() != path:
        raise ResearchError("Ledger storage must not redirect.")
    return path


def records(state: Path, name: str, model: type[BaseModel]) -> list:
    return read_jsonl(ledger_path(state, name), model)


def append_once(state: Path, name: str, value: BaseModel, *, key: str | None = None) -> BaseModel:
    path = ledger_path(state, name)
    with file_lock(path):
        previous = read_jsonl(path, type(value))
        digest = content_hash(value.model_dump(mode="json"))
        for old in previous:
            if content_hash(old.model_dump(mode="json")) == digest:
                return old
            if key and getattr(old, key) == getattr(value, key):
                raise ResearchError("Immutable ledger identity already has different content.")
        append_jsonl(path, value)
    return value
