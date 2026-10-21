"""Minimal idempotent workspace initialization; old data is never rewritten."""

from importlib.resources import files
from pathlib import Path

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.config import CONFIG_FILENAME, write_default_config
from math_research.core.errors import ResearchError
from math_research.core.paths import WORKSPACE_DIRNAME, state_at


def workspace_dir(root: Path) -> Path:
    return root / WORKSPACE_DIRNAME


def init_workspace(root: Path) -> list[Path]:
    existing = state_at(root.resolve())
    if existing and existing.name != WORKSPACE_DIRNAME:
        raise ResearchError(
            "Legacy state is readable; run math-research-ledger migrate before init."
        )
    base = workspace_dir(root.resolve())
    created = []
    if not base.exists():
        base.mkdir(parents=True)
        created.append(base)
    config = base.parent / CONFIG_FILENAME
    if not config.exists():
        write_default_config(config, name=base.parent.name)
        created.append(config)
    for name in ("papers", "problems", "research_archive"):
        path = base / name
        if not path.exists():
            path.mkdir()
            created.append(path)
    instructions = base.parent / "AGENTS.md"
    with file_lock(instructions):
        if not instructions.exists():
            template = files("math_research.core").joinpath("research_agents.md").read_text("utf-8")
            atomic_write_text(instructions, template)
            created.append(instructions)
    return created
