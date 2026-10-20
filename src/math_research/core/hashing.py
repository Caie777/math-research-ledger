"""Exact byte hashes and deterministic content identities; never primary IDs."""

import hashlib
import json


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_hash(value: object) -> str:
    return sha256(canonical_json(value))
