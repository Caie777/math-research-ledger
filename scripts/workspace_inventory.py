"""Read-only inventory; write reports outside the corpus (may contain private paths)."""

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from math_research.core.hashing import content_hash  # noqa: E402
from math_research.ledger.manifest import Ledger  # noqa: E402


def inventory(state: Path) -> dict:
    files = {}
    for path in sorted(state.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Inventory refuses symlinks: {path}")
        if path.is_file():
            raw = path.read_bytes()
            files[path.relative_to(state).as_posix()] = {
                "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
            }
    ledger = Ledger(state)
    objects = ledger.objects()
    return {
        "files": files,
        "file_count": len(files),
        "total_bytes": sum(f["bytes"] for f in files.values()),
        "inventory_hash": content_hash(files),
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
    if report.is_relative_to(state):
        parser.error("Report must be outside research state.")
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
