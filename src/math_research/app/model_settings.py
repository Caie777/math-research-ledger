"""Local Web model roles. Secrets never belong to research memory or public DTOs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from math_research.agent.model import ModelConfigurationRequired
from math_research.agent.providers.base import BaseProvider, ProviderResponse
from math_research.agent.providers.registry import get_provider
from math_research.agent.session import SessionMessage
from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.config import Config
from math_research.core.errors import ProviderError, ResearchError

RoleName = Literal["coordinator", "research", "cheap_semantic"]
ProviderName = Literal["openai", "anthropic", "mistral", "ollama"]
PROVIDERS = ("openai", "anthropic", "mistral", "ollama")


class RoleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: ProviderName = "openai"
    model: str = Field(default="", max_length=128, pattern=r"^$|^[A-Za-z0-9][A-Za-z0-9._:/-]*$")
    reasoning_effort: Literal["low", "medium", "high"] | None = None
    enabled: bool = False

    @model_validator(mode="after")
    def supported(self) -> RoleSettings:
        if self.enabled and not self.model:
            raise ValueError("Enabled roles require a model identifier.")
        if self.reasoning_effort and self.provider != "openai":
            raise ValueError("reasoning_effort is supported by the OpenAI transport only.")
        return self


class ModelRoles(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coordinator: RoleSettings = Field(default_factory=RoleSettings)
    research: RoleSettings = Field(default_factory=RoleSettings)
    cheap_semantic: RoleSettings = Field(default_factory=RoleSettings)


class SettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    roles: ModelRoles
    # Omission keeps a key; empty string explicitly removes it. Never returned.
    credentials: dict[ProviderName, SecretStr] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_credentials(self) -> SettingsUpdate:
        for provider, secret in self.credentials.items():
            value = secret.get_secret_value()
            if provider == "ollama" or len(value) > 4096 or any(c.isspace() for c in value):
                raise ValueError("Invalid provider credential.")
        return self


def settings_path(ot_dir: Path) -> Path:
    return ot_dir.resolve().parent / ".local" / "model-settings.json"


def _load(ot_dir: Path) -> tuple[ModelRoles, dict[str, str]]:
    path = settings_path(ot_dir)
    if not path.exists():
        return ModelRoles(), {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        parsed = SettingsUpdate.model_validate(document)
        return parsed.roles, {p: s.get_secret_value() for p, s in parsed.credentials.items()}
    except (OSError, ValueError, TypeError) as exc:
        raise ResearchError(
            "Local model settings are invalid; check .local/model-settings.json."
        ) from exc


def public_settings(ot_dir: Path) -> dict:
    roles, credentials = _load(ot_dir)
    return {
        "roles": roles.model_dump(),
        "status": {
            name: "configured"
            if role.enabled
            and role.model
            and (role.provider == "ollama" or credentials.get(role.provider))
            else "missing"
            for name, role in ((name, getattr(roles, name)) for name in ModelRoles.model_fields)
        },
        "credentials": {
            p: "not_required"
            if p == "ollama"
            else "configured"
            if credentials.get(p)
            else "missing"
            for p in PROVIDERS
        },
        "providers": list(PROVIDERS),
    }


def save_settings(ot_dir: Path, update: SettingsUpdate) -> dict:
    path = settings_path(ot_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        _, credentials = _load(ot_dir)
        for provider, value in update.credentials.items():
            if value.get_secret_value():
                credentials[provider] = value.get_secret_value()
            else:
                credentials.pop(provider, None)
        atomic_write_text(
            path,
            json.dumps({"roles": update.roles.model_dump(), "credentials": credentials}, indent=2),
        )
        path.chmod(0o600)  # Windows additionally relies on the user's directory ACL.
    return public_settings(ot_dir)


def resolve_role(ot_dir: Path, role: RoleName) -> tuple[RoleSettings, Config]:
    roles, credentials = _load(ot_dir)
    settings = getattr(roles, role)
    if (
        not settings.enabled
        or not settings.model
        or (settings.provider != "ollama" and not credentials.get(settings.provider))
    ):
        raise ModelConfigurationRequired(role)
    config = Config()
    config.model.provider, config.model.name = settings.provider, settings.model
    config.model.reasoning_effort = settings.reasoning_effort
    config.model.timeout_seconds, config.model.max_retries = 60, 0
    if settings.provider != "ollama":
        config._api_key = SecretStr(credentials[settings.provider])
    return settings, config


class _PrivateProvider(BaseProvider):
    """Keep raw SDK diagnostics and credentials out of persisted Agent errors."""

    def __init__(self, provider: BaseProvider):
        self._provider = provider
        self.name = provider.name
        self.model_name = provider.model_name

    @property
    def config(self) -> Config | None:
        return getattr(self._provider, "config", None)

    @config.setter
    def config(self, value: Config) -> None:
        self._provider.config = value  # type: ignore[attr-defined]

    def generate(
        self, messages: list[SessionMessage], tools: list[dict] | None = None
    ) -> ProviderResponse:
        try:
            return self._provider.generate(messages, tools)
        except Exception:
            raise ProviderError(
                f"{self.name} request failed. Check local credentials and provider."
            ) from None


def role_provider(ot_dir: Path, role: RoleName) -> BaseProvider:
    _, config = resolve_role(ot_dir, role)
    try:
        return _PrivateProvider(get_provider(config))
    except (ResearchError, ImportError, ValueError):
        raise ModelConfigurationRequired(role) from None


def install_model_settings_routes(app, ot_dir: Path, write_header) -> None:
    from fastapi import Depends, HTTPException
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        if request.url.path == "/api/settings/models":
            # Pydantic error input can contain the submitted secret.
            return JSONResponse(status_code=422, content={"detail": "Invalid model settings."})
        from fastapi.exception_handlers import request_validation_exception_handler

        return await request_validation_exception_handler(request, exc)

    @app.get("/api/settings/models")
    def read() -> dict:
        return public_settings(ot_dir)

    @app.put("/api/settings/models", dependencies=[Depends(write_header)])
    def save(update: SettingsUpdate) -> dict:
        try:
            return save_settings(ot_dir, update)
        except OSError:
            raise HTTPException(403, "Cannot save local model settings.") from None
