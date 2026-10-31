"""Read-only inventory; write reports outside the corpus (may contain private paths)."""

import argparse
import hashlib
import json
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from math_research.core.hashing import content_hash  # noqa: E402
from math_research.ledger.manifest import Ledger  # noqa: E402


def is_link(path: Path) -> bool:
    """Reject symlinks and Windows junction/reparse points, including Python 3.11."""
    return path.is_symlink() or bool(
        getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


def inventory(state: Path) -> dict:
    files = {}
    for path in sorted(state.rglob("*")):
        if is_link(path):
            raise ValueError(f"Inventory refuses links: {path}")
        if path.is_file():
            raw = path.read_bytes()
            files[path.relative_to(state).as_posix()] = {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "mtime_ns": path.stat().st_mtime_ns,
            }
    ledger = Ledger(state)
    objects = ledger.objects()
    return {
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files.values()),
        "inventory_hash": content_hash(files),
        "tree_hash": content_hash(files),
        "latest_mtime_ns": max((f["mtime_ns"] for f in files.values()), default=0),
        "ledger_generation": (
            (state / ".checkpoint-generation").read_text("utf-8")
            if (state / ".checkpoint-generation").is_file()
            else None
        ),
        "object_count": len(objects),
        "problem_count": sum(e.ref.kind == "problem" for e in objects),
        "versions": {e.qualified_id: e.version for e in objects},
        "source_version": ledger.source_version(),
        "artifact_checks": [
            {"ref": e.qualified_id, "artifacts": e.artifact_refs, "warnings": e.warnings}
            for e in objects
            if e.artifact_refs or e.warnings
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    state = args.state.resolve(strict=True)
    report = args.report.resolve()
    if report.is_relative_to(state.parent):
        parser.error("Report must be outside the entire research workspace.")
    result = inventory(state)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k.endswith("count")
                or k.endswith("hash")
                or k in {"total_bytes", "source_version"}
            },
            indent=2,
        )
    )
