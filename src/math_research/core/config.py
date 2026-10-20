"""Small core configuration. Old runtime keys remain readable, never executed."""

from importlib.resources import files
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from math_research.core.atomicio import atomic_write_text

CONFIG_FILENAME = "config.yaml"


class OpenConfig(BaseModel):
    model_config = ConfigDict(extra="allow")


class ContextConfig(OpenConfig):
    token_budget: int = Field(default=8000, ge=256, le=200000)
    top_k: int = Field(default=20, ge=1, le=100)


class Config(OpenConfig):
    context: ContextConfig = Field(default_factory=ContextConfig)


def default_config() -> Config:
    return Config()


def load_config(path: Path) -> Config:
    return Config.model_validate(yaml.safe_load(path.read_text("utf-8")) or {})


def default_config_yaml() -> str:
    return files("math_research.core").joinpath("default_config.yaml").read_text("utf-8")


def write_default_config(path: Path) -> None:
    if not path.exists():
        atomic_write_text(path, default_config_yaml())


def write_config(path: Path, config: Config) -> None:
    atomic_write_text(path, yaml.safe_dump(config.model_dump(mode="json"), sort_keys=False))
