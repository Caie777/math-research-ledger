"""Byte-authoritative, append-only version snapshots for statement dependencies."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from .models import FrozenManifest, FrozenSource


def repo_root(repo: Path) -> Path:
    root = repo.resolve(strict=True)
    if not root.is_dir() or not (root / ".git").exists():
        raise ValueError("Expected an existing independent Lean Git repository")
    return root


def source_path(root: Path, relative: str) -> Path:
    """Validate both slash conventions, even when running on the other OS."""
    posix = PurePosixPath(relative.replace("\\", "/"))
    windows = PureWindowsPath(relative)
    if (
        not relative
        or posix.is_absolute()
        or windows.drive
        or ".." in posix.parts
        or any(part in {".git", ".lake"} for part in posix.parts)
        or ":" in relative
    ):
        raise ValueError("Source must be a local repository-relative path")
    path = (root / posix).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("Source escapes the repository or is not a file")
    return path


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def frozen_source(root: Path, relative: str) -> FrozenSource:
    data = source_path(root, relative).read_bytes()
    return FrozenSource(
        path=relative.replace("\\", "/"),
        sha256=hash_bytes(data),
        normalized_sha256=hash_bytes(data.replace(b"\r\n", b"\n")),
    )


def dependency_identity(root: Path) -> tuple[str, str, str]:
    toolchain = source_path(root, "lean-toolchain").read_text(encoding="utf-8").strip()
    manifest = json.loads(source_path(root, "lake-manifest.json").read_text(encoding="utf-8"))
    mathlib = next(p for p in manifest["packages"] if p["name"] == "mathlib")
    return toolchain, mathlib["inputRev"], mathlib["rev"]


def freeze(
    repo: Path,
    statement: str,
    local_definitions: tuple[str, ...],
    store: Path,
    *,
    version: int = 1,
    reason: str | None = None,
) -> FrozenManifest:
    """Never rebind an existing version. A changed statement needs a new version/reason."""
    root = repo_root(repo)
    if version < 1 or (version > 1 and not reason) or (reason is not None and not reason.strip()):
        raise ValueError("A positive version and explicit reason are required")
    if version > 1 and not (store / f"v{version - 1}" / "manifest.json").is_file():
        raise ValueError("Preserve the prior version before creating the next version")
    configs = tuple(name for name in ("lakefile.toml", "lakefile.lean") if (root / name).exists())
    if not configs:
        raise ValueError("Missing Lake configuration")
    toolchain, ref, commit = dependency_identity(root)
    result = FrozenManifest(
        statement_version=version,
        reason=reason or "Initial statement freeze",
        frozen_at=datetime.now(UTC).isoformat(),
        statement=frozen_source(root, statement),
        local_definitions=tuple(frozen_source(root, path) for path in local_definitions),
        dependencies=tuple(
            frozen_source(root, path) for path in ("lean-toolchain", "lake-manifest.json", *configs)
        ),
        lean_toolchain=toolchain,
        mathlib_ref=ref,
        mathlib_commit=commit,
    )
    destination = store.resolve() / f"v{version}"
    destination.mkdir(parents=True, exist_ok=False)
    for source in (result.statement, *result.local_definitions, *result.dependencies):
        data = source_path(root, source.path).read_bytes()
        if hash_bytes(data) != source.sha256:
            raise ValueError("FROZEN_SOURCE_DRIFT during snapshot creation")
        target = destination / "sources" / source.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (destination / "manifest.json").write_text(result.model_dump_json(indent=2) + "\n", "utf-8")
    return result


def load_freeze(path: Path) -> FrozenManifest:
    return FrozenManifest.model_validate_json(path.read_bytes())


def verify_frozen(repo: Path, frozen: FrozenManifest) -> tuple[str, ...]:
    root = repo_root(repo)
    drift = []
    for source in (frozen.statement, *frozen.local_definitions, *frozen.dependencies):
        try:
            if frozen_source(root, source.path).sha256 != source.sha256:
                drift.append(source.path)
        except (OSError, ValueError):
            drift.append(source.path)
    try:
        if dependency_identity(root) != (
            frozen.lean_toolchain,
            frozen.mathlib_ref,
            frozen.mathlib_commit,
        ):
            drift.append("dependency identity")
    except (OSError, ValueError, KeyError, StopIteration):
        drift.append("dependency identity")
    return tuple(drift)
