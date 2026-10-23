"""Exact immutable-source reads. Hash the bytes returned, never repair metadata."""

import hashlib
from pathlib import Path

from math_research.core.errors import IntegrityError


def verified_bytes(path: Path, expected_sha256: str, *, label: str) -> bytes:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise IntegrityError(f"Unreadable source {label}: {type(exc).__name__}") from exc
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise IntegrityError(f"Source SHA-256 mismatch: {label}")
    return raw


def verified_text(path: Path, expected_sha256: str, *, label: str) -> str:
    raw = verified_bytes(path, expected_sha256, label=label)
    try:
        return raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise IntegrityError(f"Source is not UTF-8: {label}") from exc
