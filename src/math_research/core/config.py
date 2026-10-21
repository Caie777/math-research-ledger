"""Versioned research workspace metadata, independent of tool/runtime settings.

Legacy .math-research/config.yaml is preserved as historical data and is never
used for Agent/provider configuration. Existing ledgers need no write to read.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError

CONFIG_FILENAME = "workspace.yaml"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_version: Literal[1, 2]
    name: str = Field(min_length=1, max_length=255)
    created_at: AwareDatetime


def default_config(name: str = "research-workspace") -> Config:
    return Config(workspace_version=2, name=name, created_at=datetime.now(UTC))


def load_config(path: Path) -> Config:
    try:
        return Config.model_validate(yaml.safe_load(path.read_text("utf-8-sig")))
    except (ValidationError, yaml.YAMLError, UnicodeError) as exc:
        raise ResearchError(
            "Invalid workspace.yaml: expected workspace_version: 1 or 2, name and "
            "timezone-aware created_at. Preserve history and migrate metadata explicitly."
        ) from exc


def default_config_yaml(name: str = "research-workspace") -> str:
    return yaml.safe_dump(default_config(name).model_dump(mode="json"), sort_keys=False)


def write_default_config(path: Path, *, name: str = "research-workspace") -> None:
    with file_lock(path):
        if not path.exists():
            atomic_write_text(path, default_config_yaml(name))


def write_config(path: Path, config: Config) -> None:
    with file_lock(path):
        atomic_write_text(path, yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))


def workspace_config(root: Path) -> Config | None:
    """None means a legacy/unversioned workspace; reading never migrates it."""
    path = root / CONFIG_FILENAME
    return load_config(path) if path.is_file() else None
