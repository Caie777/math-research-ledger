"""Prepare scoped, metadata-only queries for later human annotation. Never announces gold."""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from math_research.ledger.records import store


def candidates(state: Path, problem_id: str) -> dict:
    problem = store.require_dossier(state, problem_id)
    claims = sorted(store.list_claims(state, problem_id), key=lambda c: c.id)
    failures = sorted(store.list_failed_attempts(state, problem_id), key=lambda f: f.id)
    rows = []

    def add(ident, kind, query, record_status=None, dependencies=()):
        rows.append(
            {
                "ref": f"{problem_id}:{kind}:{ident}",
                "query": query,
                "record_status": record_status,
                "recorded_dependency_ids": list(dependencies),
                "gold": None,
                "relevance_labels": None,
                "annotation_status": "PENDING_HUMAN",
            }
        )

    main = next((c for c in claims if c.id == problem.primary_claim_id), None)
    if main:
        add(
            main.id,
            "gap" if main.type == "OPEN_GAP" else "claim",
            "当前 Problem 明确指定的完整主目标是什么？",
        )
    add(problem_id, "problem", "当前应恢复哪个研究问题，哪些记录仍需核对？", problem.status)
    for c in [c for c in claims if c.type == "OPEN_GAP"][:2]:
        add(c.id, "gap", "这个 Gap 当前依赖什么，哪些输入仍缺少版本绑定？", c.status, c.depends_on)
    for f in failures[:2]:
        add(f.id, "failed_attempt", "这条路线是否做过，已有失败记录能否帮助避免重复？")
    for c in [c for c in claims if c.type != "OPEN_GAP"][:2]:
        add(
            c.id,
            "claim",
            "May this Claim be reused as a premise, and what must be rechecked?",
            c.status,
            c.depends_on,
        )
    return {
        "schema_version": 1,
        "problem_id": problem_id,
        "not_gold": True,
        "scope": "queries_and_record_metadata_only",
        "candidates": rows,
        "annotation_instructions": "Researcher supplies required refs and relevance labels later; "
        "record status is not authority or proof.",
    }


def snapshot(root: Path):
    result = {}
    for path in root.rglob("*"):
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(
                "Scoped diagnostic must not follow paths outside the selected Problem."
            )
        if path.is_file():
            result[path.relative_to(root).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--problem-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    state, output = args.state.resolve(), args.output.resolve()
    if output.is_relative_to(state.parent) or output.exists():
        raise ValueError("Use a new output file outside the research workspace.")
    scope = store.dossier_dir(state, args.problem_id).resolve()

    def guard(event, values):
        if event == "open" and not isinstance(values[0], int):
            path = Path(values[0]).resolve()
            if path.is_relative_to(state.parent):
                if not path.is_relative_to(scope):
                    raise PermissionError(
                        "Only selected Problem records are authorized for this diagnostic."
                    )
                mode, flags = values[1:3]
                if (
                    isinstance(mode, str)
                    and any(c in mode for c in "wax+")
                    or isinstance(flags, int)
                    and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
                ):
                    raise PermissionError("Research diagnostic is read-only.")
        if event in {
            "os.mkdir",
            "os.remove",
            "os.rmdir",
            "os.rename",
            "os.chmod",
            "os.chown",
            "os.link",
            "os.symlink",
            "os.utime",
            "os.truncate",
        }:
            for value in values[:2]:
                if isinstance(value, (str, bytes, os.PathLike)) and Path(
                    os.fsdecode(value)
                ).resolve().is_relative_to(state.parent):
                    raise PermissionError("Research mutations are forbidden.")

    sys.addaudithook(guard)
    before = snapshot(scope)
    result = candidates(state, args.problem_id)
    after = snapshot(scope)
    if before != after:
        raise RuntimeError(
            "Selected Problem changed during diagnostic; cannot assert byte stability."
        )
    result["integrity_observation"] = {
        "problem_files_before": len(before),
        "problem_files_after": len(after),
        "bytes_unchanged": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), "utf-8")
    print(
        json.dumps(
            {
                "problem_id": args.problem_id,
                "candidates": len(result["candidates"]),
                **result["integrity_observation"],
            }
        )
    )


if __name__ == "__main__":
    main()
