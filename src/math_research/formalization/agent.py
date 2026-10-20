"""Formalization decisions, executor configuration and persistent run state."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from math_research.agent.providers.base import BaseProvider
from math_research.agent.providers.registry import get_provider
from math_research.app.model_settings import resolve_role, role_provider
from math_research.app.workflows.actions import load_research_defaults
from math_research.core.config import load_config
from math_research.core.errors import ResearchError

from .diagnostics import LeanDiagnostic


class FormalBudget(BaseModel):
    model_calls: int = Field(default=16, ge=1, le=16)
    builds: int = Field(default=24, ge=1, le=24)
    target_checks: int = Field(default=4, ge=1, le=4)
    total_tokens: int = Field(default=160000, ge=100, le=250000)
    max_context_tokens: int = Field(default=24000, ge=100, le=32000)


class FormalAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: Literal[
        "list_formal_workspace",
        "read_formal_file",
        "write_proof_file",
        "run_lean_build",
        "check_target",
        "read_build_diagnostics",
        "search_mathlib",
        "read_mathlib_source",
        "FINISH",
    ]
    arguments: dict = Field(default_factory=dict)


class FormalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(default="", max_length=1200)
    actions: list[FormalAction] = Field(min_length=1, max_length=4)


class FormalRunState(BaseModel):
    run_id: str
    budget: FormalBudget = Field(default_factory=FormalBudget)
    model_calls: int = 0
    build_count: int = 0
    target_checks: int = 0
    tool_calls: int = 0
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    tokens_estimated: bool = False
    usage_missing_calls: int = 0
    cached_tokens: int | None = None
    actual_models: list[str] = Field(default_factory=list)
    proof_hashes: dict[str, str] = Field(default_factory=dict)
    diagnostics: list[LeanDiagnostic] = Field(default_factory=list)
    successful_helper_facts: list[str] = Field(default_factory=list)
    successful_source_facts: dict[str, dict] = Field(default_factory=dict)
    last_action: str = "INITIALIZE"
    last_observation: dict = Field(default_factory=dict)
    last_build_ok: bool = False
    last_built_hash: str = ""
    last_error_signature: str = ""
    repeated_errors: int = 0
    repeated_actions: int = 0
    last_action_signature: str = ""
    no_progress_events: list[str] = Field(default_factory=list)
    reflection_used: bool = False
    reflection_pending: bool = False
    malformed_responses: int = 0
    pending_operation: str | None = None
    stop_reason: str | None = None


@dataclass
class ExecutorSelection:
    provider: BaseProvider | None
    metadata: dict


APISelection = ExecutorSelection  # Compatibility for V1 API-specific callers.


def select_api_provider(ot_dir: Path) -> APISelection:
    """Read existing roles/credentials only. Never instantiate a native Codex provider."""
    selected_role: dict | None = None
    try:
        settings, _ = resolve_role(ot_dir, "research")
        metadata = {
            "provider": settings.provider,
            "model": settings.model,
            "reasoning_effort": settings.reasoning_effort,
            "role": "research",
            "configuration_source": "local_model_roles",
            "status": "CONFIGURED",
        }
        selected_role = metadata
        provider = role_provider(ot_dir, "research")
    except (ResearchError, ValueError, ImportError):
        if selected_role:
            return APISelection(
                None,
                {
                    **selected_role,
                    "status": "BLOCKED_API_CONFIGURATION",
                    "reason": "Configured API adapter could not initialize",
                },
            )
        defaults = load_research_defaults(ot_dir).research
        name = defaults.get("provider", "codex")
        metadata = {
            "provider": name,
            "model": defaults.get("model"),
            "role": "research",
            "reasoning_effort": defaults.get("reasoning_effort"),
            "configuration_source": "research_ui_defaults",
        }
        if name not in {"openai", "anthropic", "mistral", "ollama"}:
            return APISelection(
                None,
                {
                    **metadata,
                    "status": "BLOCKED_API_CONFIGURATION",
                    "reason": "Research role has no API-capable transport",
                },
            )
        config = load_config(ot_dir / "config.yaml")
        config.model.provider = name
        config.model.name = defaults["model"]
        effort = defaults.get("reasoning_effort")
        if effort not in {None, "low", "medium", "high"}:
            return APISelection(
                None,
                {
                    **metadata,
                    "status": "BLOCKED_API_CONFIGURATION",
                    "reason": "Unsupported API reasoning setting",
                },
            )
        config.model.reasoning_effort = effort
        key_name = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "mistral": "MISTRAL_API_KEY",
        }.get(name)
        if key_name and not config._api_key and not os.environ.get(key_name):
            return APISelection(
                None,
                {
                    **metadata,
                    "status": "BLOCKED_API_CONFIGURATION",
                    "reason": "API credential is not configured",
                },
            )
        config.model.max_retries = 0
        try:
            provider = get_provider(config)
        except (ResearchError, ImportError, ValueError):
            return APISelection(
                None,
                {
                    **metadata,
                    "status": "BLOCKED_API_CONFIGURATION",
                    "reason": "API adapter could not initialize",
                },
            )
        metadata["status"] = "CONFIGURED"
    # Changes apply to this in-memory instance only, never saved to research settings.
    selected_config = getattr(provider, "config", None)
    if selected_config is not None:
        selected_config.model.max_retries = 0
        selected_config.model.timeout_seconds = 180
        selected_config.model.max_tokens = 8192
    return APISelection(provider, metadata)


SYSTEM_PROMPT = """You are a Lean formalization agent using a decision-only executor.
Prove the exact requested declaration using the supplied frozen statement and informal source.
Return ONLY JSON matching the supplied decision schema: a concise public action summary and
1-4 actions. Do not emit private reasoning. write_proof_file replaces a complete UTF-8 file.
Use only the supplied file and Mathlib tools; there is no shell or external agent.
Frozen statement, definitions, root module and dependency locks are read-only. Do not change,
redefine, weaken or shadow the statement. No sorry/admit/axiom, executable metaprograms, custom
IO, or attempts to access a baseline solution. Writable regions and current sources are given.
Each changed proof file automatically triggers a build. Use compiler diagnostics to repair it.
Successful build facts are retained, but they are not kernel checks of the exact final target.
FINISH/check_target requests the deterministic target/axiom check, which alone can yield checked.
No acceptance or premise authorization is possible. Read missing source windows with tools.
If a reflection notice is present, change the failing approach or stop; do not loop indefinitely.
"""
