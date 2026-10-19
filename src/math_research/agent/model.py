"""Shared, bounded model transport for hard proposals and ephemeral soft reranking."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Literal, cast

from math_research.agent.providers.base import BaseProvider, ProviderResponse, TokenUsage
from math_research.agent.providers.registry import get_provider
from math_research.agent.session import SessionMessage
from math_research.agent.transport import CodexCLIExecutor, ResearchBudget
from math_research.core.config import load_config
from math_research.core.errors import ResearchError
from math_research.memory.records.write_boundary import automated_research


class ModelConfigurationRequired(ResearchError):
    """An explicit semantic model role is not configured; never select a fallback."""


def get_role_provider(
    ot_dir: Path, *, model_role: Literal["coordinator", "research", "cheap_semantic"]
) -> BaseProvider:
    """Resolve local Web roles, retaining explicit legacy Coordinator configuration.

    Coordinator transport has no built-in shell/browser/filesystem/MCP tools.
    Public schema output is validated by the caller, never a private reasoning stream.
    """
    from math_research.agent.codex import CodexToolProvider
    from math_research.app.model_settings import role_provider, settings_path
    from math_research.app.workflows.actions import load_research_defaults

    if settings_path(ot_dir).exists() or model_role != "coordinator":
        return role_provider(ot_dir, model_role)

    try:
        settings = getattr(load_research_defaults(ot_dir), model_role)
    except (ResearchError, ValueError) as exc:
        raise ModelConfigurationRequired("MODEL_CONFIGURATION_REQUIRED") from exc
    if settings is None:
        raise ModelConfigurationRequired("MODEL_CONFIGURATION_REQUIRED")
    if settings.provider == "codex":
        return CodexToolProvider(
            settings.model,
            settings.reasoning_effort,
            deadline=time.monotonic() + 60,
            should_stop=lambda: False,
            tool_free=True,
        )
    config = load_config(ot_dir / "config.yaml")
    config.model.provider, config.model.name = settings.provider, settings.model
    config.model.timeout_seconds, config.model.max_retries = 60, 0
    if settings.reasoning_effort is not None:
        if settings.reasoning_effort not in {"low", "medium", "high"}:
            raise ModelConfigurationRequired("MODEL_CONFIGURATION_REQUIRED")
        config.model.reasoning_effort = settings.reasoning_effort
    try:
        return get_provider(config)
    except (ResearchError, ImportError, ValueError) as exc:
        raise ModelConfigurationRequired("MODEL_CONFIGURATION_REQUIRED") from exc


class SemanticModel:
    """No persistence or mathematical-state access; delegates to existing executors."""

    def __init__(
        self,
        ot_dir: Path,
        *,
        provider: BaseProvider | None = None,
        provider_name: str | None = None,
        model: str | None = None,
        reasoning_effort: str | None = None,
        codex_executor: CodexCLIExecutor | None = None,
    ) -> None:
        if model is not None and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model):
            raise ResearchError("Invalid model identifier.")
        config = load_config(ot_dir / "config.yaml")
        if provider_name:
            config.model.provider = provider_name
        self.codex_backend = config.model.provider == "codex" and provider is None
        efforts = {None, "low", "medium", "high"}
        if self.codex_backend:
            efforts.update({"xhigh", "max"})
        if reasoning_effort not in efforts:
            raise ResearchError("Unsupported reasoning_effort for the selected provider.")
        if model:
            config.model.name = model
        if provider is None and config.model.provider == "mock":
            raise ResearchError("Semantic tasks need Codex or a configured real provider.")
        if reasoning_effort is not None:
            if config.model.provider not in {"openai", "codex"}:
                raise ResearchError("reasoning_effort requires OpenAI API or Codex CLI.")
            if config.model.provider == "openai":
                config.model.reasoning_effort = cast(
                    Literal["low", "medium", "high"], reasoning_effort
                )
        self.provider = None if self.codex_backend else (provider or get_provider(config))
        self.codex = (codex_executor or CodexCLIExecutor()) if self.codex_backend else None
        self.name = "codex" if self.provider is None else self.provider.name
        self.requested_model = model or (
            "Codex default" if self.codex_backend else config.model.name
        )
        self.model = model
        self.effort = reasoning_effort
        self.actual_effort = reasoning_effort
        self.actual_models: list[str] = []
        self.cli_version: str | None = None
        self.cli_usage: list[dict[str, int]] = []
        self.budget = ResearchBudget(
            timeout_seconds=min(max(config.model.timeout_seconds, 5), 3600)
        )

    @automated_research
    def generate(
        self, messages: list[SessionMessage], schema: dict[str, object]
    ) -> ProviderResponse:
        if self.codex is not None:
            prompt = "\n\n".join(message.content for message in messages[:-1])
            prompt += "\n\nInput candidates and scoped historical hits:\n" + messages[-1].content
            raw, version, usage, _events, _errors, _duration, model, effort = self.codex.execute(
                prompt,
                self.budget,
                model=self.model,
                reasoning_effort=self.effort,
                output_schema=schema,
            )
            self.cli_version = version
            if usage:
                self.cli_usage.append(usage)
            self.actual_effort = effort or self.effort
            response = ProviderResponse(
                kind="message",
                content=raw,
                model=model or self.model,
                usage=TokenUsage(
                    prompt_tokens=usage.get("input_tokens", 0),
                    completion_tokens=usage.get("output_tokens", 0),
                    thinking_tokens=usage.get("reasoning_output_tokens", 0),
                )
                if usage
                else None,
            )
        else:
            assert self.provider is not None
            response = self.provider.generate(messages, tools=None)
        self.actual_models.append(
            response.model or (self.provider.model_name if self.provider else None) or "unknown"
        )
        return response
