"""One-time .opentorus migration; the final runtime has only one state root."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from pathlib import Path
from uuid import uuid4

import yaml

from math_research.core.errors import ResearchError

LEGACY_ROOT = ".opentorus"
STATE_ROOT = ".math-research"
PATH_FIELDS = {
    "path",
    "archive_path",
    "source_path",
    "source_artifacts",
    "original_path",
    "file_path",
    "note_path",
    "pdf_path",
    "structure_path",
    "text_path",
    "artifacts",
}


def inventory(base: Path) -> dict[str, str]:
    """Content inventory without changing the source tree."""
    return {
        p.relative_to(base).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(base.rglob("*"))
        if p.is_file()
    }


def _rewrite(value: object, key: str = "") -> object:
    if isinstance(value, dict):
        output = {k: _rewrite(v, k) for k, v in value.items()}
        if output.get("kind") == "claim" and "node_id" in output:
            if output.get("campaign_id") is not None:
                raise ResearchError("Campaign targets are outside the final research product.")
            output.pop("campaign_id", None)
        if "harness_ui_defaults" in output:
            if "research_ui_defaults" in output:
                raise ResearchError("Conflicting research settings; no migration performed.")
            output["research_ui_defaults"] = output.pop("harness_ui_defaults")
        return output
    if isinstance(value, list):
        return [_rewrite(v, key) for v in value]
    if isinstance(value, str) and (key in PATH_FIELDS or key.endswith("_path")):
        if value.startswith(LEGACY_ROOT + "/") or value.startswith(LEGACY_ROOT + "\\"):
            return STATE_ROOT + value[len(LEGACY_ROOT) :]
    return value


def semantic_snapshot(base: Path) -> dict:
    """Exercise Records, Resolver, raw Archive, Recall and recovery without a model."""
    from math_research.agent.runtime import recovery_status
    from math_research.agent.state import AgentRun
    from math_research.memory.archive import _verified_bytes
    from math_research.memory.episodes import list_candidates, list_episodes, list_reviews
    from math_research.memory.handoff import current_research_state
    from math_research.memory.records import store
    from math_research.memory.relations.ledger import active_relations
    from math_research.memory.state import KnowledgeStateResolver
    from math_research.memory.target import ResearchTarget
    from math_research.retrieval.recall import ResearchRecall

    def dump(value):
        return value.model_dump(mode="json")

    result: dict = {"problems": {}, "runs": {}, "files": inventory(base)}
    for problem in store.list_dossiers(base):
        pid = problem.id
        states = KnowledgeStateResolver(base).resolve(pid)
        episodes = list_episodes(base, pid)
        for episode in episodes:
            _verified_bytes(base, episode)
        entry = {
            "problem": dump(problem),
            "states": {k: dump(v) for k, v in sorted(states.items())},
            "relations": [dump(r) for r in active_relations(base, pid)],
            "episodes": [dump(e) for e in episodes],
            "candidates": [dump(c) for c in list_candidates(base, pid)],
            "reviews": [dump(r) for r in list_reviews(base, pid)],
            "records": {},
            "current_state": {},
            "recall": {},
        }
        for name in [
            "claims",
            "proof_attempts",
            "counterexamples",
            "evidence",
            "failed_attempts",
            "assumptions",
            "definitions",
            "known_results",
            "related_papers",
            "approaches",
        ]:
            entry["records"][name] = [dump(x) for x in getattr(store, "list_" + name)(base, pid)]
        for claim in store.list_claims(base, pid):
            target = ResearchTarget(kind="claim", problem_id=pid, node_id=claim.id)
            entry["current_state"][claim.id] = dump(current_research_state(base, target))
            entry["recall"][claim.id] = dump(ResearchRecall(base, pid).find_files(claim.id))
        result["problems"][pid] = entry
    for path in (base / "research_runs").glob("*/run.json"):
        payload = json.loads(path.read_text("utf-8"))
        target = payload["request"]["target"]
        if target.get("campaign_id") is None:
            target.pop("campaign_id", None)
        run = AgentRun.model_validate(payload)
        result["runs"][run.run_id] = dump(recovery_status(base, run))
    return result


def logical_identity(value: object) -> object:
    """Normalize storage location and derived version hashes, never mathematical content."""
    if isinstance(value, dict):
        return {
            k: logical_identity(v)
            for k, v in value.items()
            if k not in {"files", "version", "source_version", "research_version", "campaign_id"}
        }
    if isinstance(value, list):
        return [logical_identity(v) for v in value]
    if isinstance(value, str):
        return value.replace(LEGACY_ROOT, "STATE_ROOT").replace(STATE_ROOT, "STATE_ROOT")
    return value


def _copy_state(source: Path, destination: Path) -> None:
    """Copy bytes and directories, leaving new permissions inherited from the project."""
    destination.mkdir()
    for path in source.rglob("*"):
        target = destination / path.relative_to(source)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def migrate_workspace(root: Path, *, immutable_backup: bool = True) -> dict:
    """Stage, validate and atomically publish the new root; refuse overwrite or symlinks."""
    root = root.resolve()
    source, destination = root / LEGACY_ROOT, root / STATE_ROOT
    if not source.is_dir() or source.is_symlink():
        raise ResearchError("A regular legacy state directory is required.")
    if destination.exists():
        raise ResearchError("The final state root already exists; nothing was overwritten.")
    if any(p.is_symlink() for p in source.rglob("*")):
        raise ResearchError("State contains symlinks; inspect it before migration.")
    before = inventory(source)
    semantics = semantic_snapshot(source)
    changed: list[str] = []
    # TemporaryDirectory uses mkdir(0o700), which installs a protected Windows DACL.
    # A same-volume rename retains permissions: staging must inherit the project ACL.
    temporary = root / f".research-migration-{uuid4().hex}"
    temporary.mkdir()
    try:
        staged = temporary / STATE_ROOT
        _copy_state(source, staged)
        if inventory(staged) != before:
            raise ResearchError("Source copy SHA-256 verification failed.")
        for p in staged.rglob("*"):
            if not p.is_file() or p.suffix not in {".json", ".jsonl", ".yaml", ".yml"}:
                continue
            text = p.read_text("utf-8")
            if not text.strip():
                continue
            if p.suffix == ".jsonl":
                records = [json.loads(line) for line in text.splitlines() if line.strip()]
                rewritten = _rewrite(records)
                assert isinstance(rewritten, list)
                rendered = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rewritten)
            else:
                records = json.loads(text) if p.suffix == ".json" else yaml.safe_load(text)
                rewritten = _rewrite(records)
                rendered = (
                    json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n"
                    if p.suffix == ".json"
                    else yaml.safe_dump(rewritten, allow_unicode=True)
                )
            if rewritten != records:
                os.chmod(p, stat.S_IWRITE | stat.S_IREAD)
                p.write_text(rendered, "utf-8")
                changed.append(p.relative_to(staged).as_posix())
        after = semantic_snapshot(staged)
        if logical_identity(semantics) != logical_identity(after):
            raise ResearchError("Logical identity changed; original state was left untouched.")
        expected = inventory(staged)
        if any(expected[name] != digest for name, digest in before.items() if name not in changed):
            raise ResearchError("Non-metadata content changed; original state was left untouched.")
        if inventory(source) != before:
            raise ResearchError("Original state changed during migration; retry when inactive.")
        staged.rename(destination)
    finally:
        shutil.rmtree(temporary)
    if immutable_backup:
        # Backup protection is local to the original files, after independent publication.
        for p in source.rglob("*"):
            if p.is_file():
                os.chmod(p, p.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    return {
        "file_count": len(before),
        "rewritten_metadata": changed,
        "before": before,
        "after": expected,
        "semantic_identity": True,
    }
