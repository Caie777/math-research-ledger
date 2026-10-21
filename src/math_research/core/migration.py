"""Explicit offline format migration, with a durable rollback journal.

Only the state directory is renamed. Ordinary files and historical provenance stay
where the user put them. Stop other writers before migration. Directory publication
is an atomic same-volume rename; metadata publication is atomic per file. A crash
between them leaves a journal which blocks discovery until explicit rollback.
"""

import json
import os
from pathlib import Path

import yaml

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.config import CONFIG_FILENAME, default_config, workspace_config
from math_research.core.errors import ResearchError
from math_research.core.paths import (
    LEGACY_WORKSPACE_DIRNAME,
    MIGRATION_JOURNAL,
    STATE_DIRNAMES,
    WORKSPACE_DIRNAME,
    state_at,
)


def _restore(root: Path, value: dict) -> dict:
    source = Path(value["source"])
    target = root / WORKSPACE_DIRNAME
    if not source.is_absolute() or source.name not in STATE_DIRNAMES or source == target:
        raise ResearchError("Invalid migration journal source; manual inspection required.")
    if target.exists():
        if source.exists() or target.is_symlink():
            raise ResearchError("Rollback would overwrite state; preserve both and inspect.")
        os.rename(target, source)
    elif not source.is_dir():
        raise ResearchError("Neither migration source nor target exists; inspect backups.")
    config = root / CONFIG_FILENAME
    previous = value["metadata_before"]
    if previous is None:
        config.unlink(missing_ok=True)
    elif not config.is_file() or config.read_bytes() != bytes.fromhex(previous):
        # utf-8 (not utf-8-sig) preserves a preexisting BOM and newline bytes.
        atomic_write_text(config, bytes.fromhex(previous).decode("utf-8"))
    (root / MIGRATION_JOURNAL).unlink()
    return {"rolled_back": True, "state_dir": str(source)}


def rollback_migration(root: Path) -> dict:
    root = root.resolve(strict=True)
    with file_lock(root / MIGRATION_JOURNAL):
        journal = root / MIGRATION_JOURNAL
        if not journal.is_file():
            raise ResearchError("No interrupted migration journal exists.")
        return _restore(root, json.loads(journal.read_text("utf-8")))


def migrate_workspace(source_root: Path, target_root: Path | None = None) -> dict:
    """Refuse conflicts; rename bytes unchanged; preserve source-side ordinary metadata."""
    source_root = source_root.resolve(strict=True)
    target_root = (target_root or source_root).resolve(strict=True)
    journal = target_root / MIGRATION_JOURNAL
    with file_lock(journal):
        if journal.exists():
            raise ResearchError("Migration journal exists; use migrate --rollback first.")
        source = state_at(source_root)
        if source is None:
            raise ResearchError("No source research state; migration never initializes a corpus.")
        target = target_root / WORKSPACE_DIRNAME
        if source == target:
            return {"migrated": False, "state_dir": str(target), "workspace_version": 2}
        if target.exists() or (
            target_root != source_root and (target_root / LEGACY_WORKSPACE_DIRNAME).exists()
        ):
            raise ResearchError("Migration target exists; never overwrite or merge unknown state.")
        if target_root.is_relative_to(source):
            raise ResearchError("Migration target cannot be inside research state.")
        for path in source.rglob("*"):
            if path.is_symlink() or path.name.endswith(".lock"):
                raise ResearchError(
                    "Stop writers and inspect symlinks/locks before offline migration."
                )
        config_path = target_root / CONFIG_FILENAME
        if target_root != source_root and config_path.exists():
            raise ResearchError("Target workspace.yaml exists; resolve workspace ownership first.")
        metadata = workspace_config(source_root) or default_config(source_root.name)
        metadata = metadata.model_copy(update={"workspace_version": 2})
        value = {
            "source": str(source),
            "metadata_before": config_path.read_bytes().hex() if config_path.exists() else None,
        }
        atomic_write_text(journal, json.dumps(value))
        try:
            os.rename(source, target)  # Atomic; cross-volume moves fail without copying.
            atomic_write_text(
                config_path, yaml.safe_dump(metadata.model_dump(mode="json"), sort_keys=False)
            )
        except BaseException:
            _restore(target_root, value)
            raise
        journal.unlink()
        return {"migrated": True, "state_dir": str(target), "workspace_version": 2}
