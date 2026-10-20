"""Audited file capabilities for an isolated formalization checkout."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath

from math_research.core.atomicio import atomic_write_text

from .checker import code_only
from .freeze import hash_bytes, repo_root, verify_frozen
from .models import FrozenManifest

WRITABLE = ("WeakSchottky/Proofs/", "WeakSchottky/Helpers/", "WeakSchottky/Scratch/")
_FORBIDDEN = {
    "IO",
    "System",
    "unsafe",
    "initialize",
    "elab",
    "macro",
    "run_tac",
    "run_cmd",
    "run_meta",
    "run_elab",
    "by_elab",
    "extern",
    "include_str",
    "include_bytes",
}


def append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": datetime.now(UTC).isoformat(), **event}) + "\n")


def _local_path(root: Path, relative: str) -> Path:
    portable = relative.replace("\\", "/")
    posix = PurePosixPath(portable)
    if (
        not portable
        or posix.is_absolute()
        or PureWindowsPath(relative).drive
        or ".." in posix.parts
        or ":" in relative
        or "\x00" in relative
    ):
        raise ValueError("Repository-relative paths only")
    candidate = root / posix
    current = root
    for part in posix.parts:
        current = current / part
        # Reject even internal links: capabilities must not change through junction aliases.
        if current.is_symlink() or (hasattr(os.path, "isjunction") and os.path.isjunction(current)):
            raise ValueError("Symlink/junction path rejected")
    if not candidate.resolve().is_relative_to(root):
        raise ValueError("Path escapes capability root")
    return candidate


class FormalWorkspace:
    def __init__(self, repo: Path, frozen: FrozenManifest, audit: Path):
        self.root = repo_root(repo)
        self.frozen = frozen
        self.audit = audit.resolve()
        self.mathlib = (self.root / ".lake/packages/mathlib/Mathlib").resolve(strict=True)
        if not self.mathlib.is_relative_to(self.root):
            raise ValueError("Mathlib must be inside the isolated checkout")
        self.frozen_paths = {
            s.path for s in (frozen.statement, *frozen.local_definitions, *frozen.dependencies)
        }

    def _path(self, tool: str, relative: str, operation: str, *, mathlib: bool = False) -> Path:
        try:
            root = self.mathlib if mathlib else self.root
            path = _local_path(root, relative)
            name = path.relative_to(root).as_posix()
            permitted = (
                name.endswith(".lean")
                if mathlib
                else name in self.frozen_paths
                or name.startswith(WRITABLE)
                and name.endswith(".lean")
            )
            if operation == "write":
                permitted = (
                    permitted and name not in self.frozen_paths and name.startswith(WRITABLE)
                )
            if not permitted:
                raise ValueError("File is outside the allowed capability")
        except (OSError, ValueError):
            append_event(
                self.audit,
                {"tool": tool, "path": relative, "operation": operation, "allowed": False},
            )
            raise ValueError("File access denied") from None
        append_event(
            self.audit, {"tool": tool, "path": str(path), "operation": operation, "allowed": True}
        )
        return path

    def list_formal_workspace(self) -> list[str]:
        paths = sorted(self.frozen_paths | set(self.proof_hashes()))
        append_event(
            self.audit,
            {
                "tool": "list_formal_workspace",
                "path": str(self.root),
                "operation": "list",
                "allowed": True,
            },
        )
        return paths

    def read_formal_file(self, path: str, *, start: int = 1, lines: int = 160) -> str:
        target = self._path("read_formal_file", path, "read")
        if start < 1 or not 1 <= lines <= 200:
            raise ValueError("Invalid line window")
        return "\n".join(target.read_text("utf-8").splitlines()[start - 1 : start - 1 + lines])[
            :16000
        ]

    def write_proof_file(self, path: str, content: str) -> bool:
        target = self._path("write_proof_file", path, "write")
        clean = code_only(content)
        tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_']*", clean))
        if (
            len(content.encode("utf-8")) > 64000
            or tokens & _FORBIDDEN
            or re.search(r"#\s*(eval|run|exec|compile)", clean)
        ):
            append_event(
                self.audit,
                {
                    "tool": "write_proof_file",
                    "path": path,
                    "operation": "source_policy",
                    "allowed": False,
                },
            )
            raise ValueError("Executable metaprogram/oversized source rejected")
        data = content.encode("utf-8")
        changed = not target.exists() or target.read_bytes() != data
        if changed:
            atomic_write_text(target, content)
        return changed

    def proof_hashes(self) -> dict[str, str]:
        result = {}
        for prefix in WRITABLE:
            directory = self.root / prefix
            if not directory.exists():
                continue
            for parent, dirs, files in os.walk(directory, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not (Path(parent) / d).is_symlink())
                for filename in sorted(files):
                    if filename.endswith(".lean"):
                        relative = (Path(parent) / filename).relative_to(self.root).as_posix()
                        path = _local_path(self.root, relative)
                        result[relative] = hash_bytes(path.read_bytes())
        return result

    def integrity(self) -> None:
        if verify_frozen(self.root, self.frozen):
            append_event(
                self.audit,
                {
                    "tool": "integrity",
                    "path": str(self.root),
                    "operation": "frozen_hash",
                    "allowed": False,
                },
            )
            raise ValueError("FROZEN_SOURCE_DRIFT")

    def read_mathlib_source(self, path: str, *, start: int = 1, lines: int = 100) -> str:
        target = self._path("read_mathlib_source", path, "read", mathlib=True)
        if start < 1 or not 1 <= lines <= 160:
            raise ValueError("Invalid line window")
        return "\n".join(target.read_text("utf-8").splitlines()[start - 1 : start - 1 + lines])[
            :12000
        ]

    def search_mathlib(self, query: str, limit: int = 15) -> list[dict]:
        if not query or len(query) > 128 or not 1 <= limit <= 20:
            raise ValueError("Invalid literal search")
        append_event(
            self.audit,
            {
                "tool": "search_mathlib",
                "path": str(self.mathlib),
                "operation": "search",
                "allowed": True,
                "query": query,
            },
        )
        hits = []
        for parent, dirs, files in os.walk(self.mathlib, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in {".git", ".lake"})
            for filename in sorted(files):
                if not filename.endswith(".lean"):
                    continue
                relative = (Path(parent) / filename).relative_to(self.mathlib).as_posix()
                path = _local_path(self.mathlib, relative)
                for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
                    if query in line:
                        hits.append({"path": relative, "line": number, "text": line[:300]})
                        if len(hits) == limit:
                            return hits
        return hits
