"""Decision-only executors: the formalization harness retains every tool capability."""

from __future__ import annotations

import time
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from math_research.agent.codex import CodexRPC, CodexToolProvider
from math_research.agent.providers.base import BaseProvider, ProviderResponse, TokenUsage
from math_research.agent.session import SessionMessage
from math_research.core.errors import ResearchError


class ExecutorIsolationError(ResearchError):
    code = "INVALIDATED_CONTEXT_LEAKAGE"


class DecisionExecutor(Protocol):
    name: str

    @property
    def model_name(self) -> str | None: ...

    def generate(
        self, messages: list[SessionMessage], tools: list[dict] | None = None
    ) -> ProviderResponse: ...


class _DecisionRPC(CodexRPC):
    """New-thread-only RPC gate, with no environment or dynamic/native tool capability."""

    def __init__(self, cwd: Path, *, evidence: list[dict], on_receipt=None, **options):
        self.evidence = evidence
        self.on_receipt = on_receipt
        self.fresh_thread: str | None = None
        env = dict(options.pop("env"))
        home = Path(env["CODEX_HOME"]).resolve()
        if home.parent != cwd.resolve() or set(p.name for p in home.iterdir()) != {
            "auth.json",
            "config.toml",
        }:
            raise ExecutorIsolationError("Executor home is not fresh/auth-only")
        config = tomllib.loads((home / "config.toml").read_text("utf-8"))
        if any(
            config.get("features", {}).get(name) is not False
            for name in [
                "shell_tool",
                "unified_exec",
                "apps",
                "plugins",
                "multi_agent",
                "memories",
                "hooks",
            ]
        ):
            raise ExecutorIsolationError("Native tool disabling is not explicit")
        if any((parent / "AGENTS.md").exists() for parent in (cwd, *cwd.parents)):
            raise ExecutorIsolationError("Ancestor instructions would contaminate executor context")
        env["ELAN_HOME"] = "D:/Tools/elan"
        super().__init__(cwd, env=env, **options)

    def call(self, method: str, params: dict, **options) -> dict:
        if method not in {"initialize", "thread/start", "turn/start", "turn/interrupt"}:
            raise ExecutorIsolationError(f"Executor RPC denied: {method}")
        if method == "thread/start":
            if (
                self.fresh_thread
                or not params.get("ephemeral")
                or params.get("dynamicTools") != []
                or params.get("environments") != []
            ):
                raise ExecutorIsolationError("Fresh, tool-free thread required")
            params = {
                **params,
                "allowProviderModelFallback": False,
                "runtimeWorkspaceRoots": [],
                "selectedCapabilityRoots": [],
            }
        if method == "turn/start" and (
            not self.fresh_thread
            or params.get("threadId") != self.fresh_thread
            or params.get("environments") != []
        ):
            raise ExecutorIsolationError("Turn lacks its fresh environment-free thread")
        result = super().call(method, params, **options)
        if method == "thread/start":
            thread = result.get("thread", {})
            if (
                thread.get("ephemeral") is not True
                or thread.get("forkedFromId")
                or thread.get("turns")
            ):
                raise ExecutorIsolationError("Server did not confirm an empty ephemeral thread")
            if not isinstance(thread.get("id"), str) or not thread["id"]:
                raise ExecutorIsolationError("Missing new thread identity")
            self.fresh_thread = thread["id"]
            self.evidence.append(
                {
                    "method": method,
                    "thread_id": self.fresh_thread,
                    "ephemeral": True,
                    "fresh_home": True,
                    "empty_environment": True,
                    "dynamic_tools": 0,
                    "resume_or_fork": False,
                    "model": result.get("model"),
                }
            )
        elif method == "turn/start":
            self.evidence.append({"method": method, "thread_id": self.fresh_thread})
        if method in {"thread/start", "turn/start"} and self.on_receipt:
            self.on_receipt(self.evidence[-1])
        return result


class APIFormalExecutor(BaseProvider):
    """Existing provider protocol, with only the supplied bounded message context."""

    executor_kind = "api"
    decision_only = True
    fresh_context_confirmed = True

    def __init__(self, provider: BaseProvider):
        self.provider = provider
        self.name, self.model_name = provider.name, provider.model_name

    def generate(self, messages, tools=None) -> ProviderResponse:
        if tools:
            raise ValueError("Executor cannot own tools")
        return self.provider.generate(messages, tools=None)

    def snapshot(self) -> dict:
        return {"executor": "api", "fresh_context_confirmed": True}


class CodexFormalExecutor(BaseProvider):
    """A fresh installed native transport invocation per structured decision, never `exec`."""

    name = "codex"
    executor_kind = "codex native"
    decision_only = True

    def __init__(self, model: str, effort: str | None, *, timeout: float = 300):
        self.model_name, self.effort = model, effort
        self.timeout = timeout
        self.evidence: list[dict] = []
        self.calls = 0
        self.completed_responses = 0
        self.native_usage: list[dict] = []
        self.fresh_context_confirmed = False
        self.event_sink: Callable[[dict], None] | None = None

    def _rpc_factory(self, cwd, **options):
        return _DecisionRPC(cwd, evidence=self.evidence, on_receipt=self.event_sink, **options)

    def preflight_context(self) -> dict:
        """Fresh thread handshake only; no inference turn or theorem context is sent."""
        backend = CodexToolProvider(
            self.model_name,
            self.effort,
            deadline=time.monotonic() + self.timeout,
            should_stop=lambda: False,
            tool_free=True,
            rpc_factory=self._rpc_factory,
        )
        try:
            backend._start(
                [SessionMessage(role="system", content="Decision-only transport preflight")],
                [],
                start_turn=False,
            )
            return {
                "model_calls": 0,
                "thread_receipt": self.evidence[-1],
                "version": backend.version,
            }
        finally:
            backend.close()

    def generate(self, messages, tools=None) -> ProviderResponse:
        if tools:
            raise ExecutorIsolationError("Native executor cannot receive tools")
        self.calls += 1
        prior = len([e for e in self.evidence if e["method"] == "thread/start"])
        backend = CodexToolProvider(
            self.model_name,
            self.effort,
            deadline=time.monotonic() + self.timeout,
            should_stop=lambda: False,
            tool_free=True,
            rpc_factory=self._rpc_factory,
        )
        backend.on_diagnostic = lambda event: self._reject_native_item(event)
        try:
            response = backend.generate(messages, tools=None)
            if response.kind != "message" or response.tool_calls:
                raise ExecutorIsolationError("Native tool output rejected; JSON decisions only")
            starts = [e for e in self.evidence if e["method"] == "thread/start"]
            if len(starts) != prior + 1 or len({e["thread_id"] for e in starts}) != len(starts):
                raise ExecutorIsolationError("Fresh thread receipt missing or reused")
            self.fresh_context_confirmed = len(starts) == self.calls
            raw = backend.usage
            exact = all(isinstance(raw.get(k), int) for k in ("inputTokens", "outputTokens"))
            response.usage = (
                TokenUsage(
                    prompt_tokens=raw["inputTokens"],
                    completion_tokens=raw["outputTokens"],
                    thinking_tokens=raw.get("reasoningOutputTokens", 0),
                )
                if exact
                else None
            )
            self.native_usage.append(
                {
                    "input_tokens": raw.get("inputTokens"),
                    "output_tokens": raw.get("outputTokens"),
                    "cached_tokens": raw.get("cachedInputTokens"),
                    "reasoning_tokens": raw.get("reasoningOutputTokens"),
                }
            )
            self.completed_responses += 1
            return response
        finally:
            starts = [e for e in self.evidence if e["method"] == "thread/start"]
            self.fresh_context_confirmed = (
                len(starts) == self.calls and len({e["thread_id"] for e in starts}) == self.calls
            )
            backend.close()

    def restore_audit(self, snapshot: dict) -> None:
        """Restore counters/receipts only. Never resume a model thread or hidden history."""
        self.calls = snapshot["invocations"]
        self.completed_responses = snapshot["completed_responses"]
        self.evidence = snapshot["context_receipts"]
        self.native_usage = snapshot["native_usage"]
        self.fresh_context_confirmed = snapshot["fresh_context_confirmed"]

    def _reject_native_item(self, event: dict) -> None:
        self.evidence.append(
            {"method": "rejected_native_item", "item_type": event.get("item_type")}
        )
        raise ExecutorIsolationError("Unexpected native capability item")

    def snapshot(self) -> dict:
        return {
            "executor": self.executor_kind,
            "fresh_context_confirmed": self.fresh_context_confirmed,
            "model": self.model_name,
            "reasoning_effort": self.effort,
            "invocations": self.calls,
            "completed_responses": self.completed_responses,
            "native_usage": self.native_usage,
            "context_receipts": self.evidence,
        }


def select_formal_executor(ot_dir: Path):
    from math_research.app.model_settings import resolve_role
    from math_research.app.workflows.actions import load_research_defaults

    from .agent import APISelection, select_api_provider

    try:
        resolve_role(ot_dir, "research")
    except (ResearchError, ValueError):
        defaults = load_research_defaults(ot_dir).research
        if defaults.get("provider") == "codex":
            model, effort = defaults["model"], defaults.get("reasoning_effort")
            return APISelection(
                CodexFormalExecutor(model, effort),
                {
                    "executor": "codex native",
                    "provider": "codex",
                    "model": model,
                    "reasoning_effort": effort,
                    "role": "research",
                    "status": "CONFIGURED",
                    "configuration_source": "research_ui_defaults",
                    "fallback": False,
                },
            )
    selected = select_api_provider(ot_dir)
    if selected.provider is not None:
        selected.provider = APIFormalExecutor(selected.provider)
        selected.metadata["executor"] = "api"
    return selected
