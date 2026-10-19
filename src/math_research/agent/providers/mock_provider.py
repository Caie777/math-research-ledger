"""A deterministic provider for tests and offline use.

It never calls an external service. It returns an honest placeholder answer.
After a tool runs, it summarizes the result and explicitly notes that no
validation was performed.
"""

from __future__ import annotations

import re

from math_research.agent.providers.base import BaseProvider, OnText, ProviderResponse
from math_research.agent.session import SessionMessage
from math_research.memory.records.write_boundary import automated_research


class MockProvider(BaseProvider):
    name = "mock"
    supports_streaming = True

    def __init__(self) -> None:
        self._fallback_seen = False
        # Reported as ``model_name``: the mock has no Config, and the usage ledger
        # (and the golden transcripts) know it as ``mock-default``.
        self._model_name = "mock-default"

    @automated_research
    def respond(
        self,
        messages: list[SessionMessage],
        tools: list[dict] | None = None,
        on_text: OnText | None = None,
        *,
        stream: bool = False,
        tool_choice: str | dict | None = None,
        on_thinking: OnText | None = None,
    ) -> ProviderResponse:
        response = self.generate(messages, tools)
        if on_text and response.kind == "message" and response.content:
            # Emit word-by-word chunks that concatenate back to the full content.
            for chunk in re.findall(r"\S+\s*", response.content):
                on_text(chunk)
        return response

    @automated_research
    def generate(
        self,
        messages: list[SessionMessage],
        tools: list[dict] | None = None,
    ) -> ProviderResponse:
        if not messages:
            return ProviderResponse(kind="message", content="No input received.")

        last = messages[-1]
        if last.role == "tool":
            return ProviderResponse(
                kind="message",
                content=(
                    "Here is what I found:\n\n"
                    f"{last.content}\n\n"
                    "This is observed output, not a validated conclusion. "
                    "Validation not run."
                ),
            )

        # Show the full offline disclaimer once per research session.
        if self._fallback_seen:
            return ProviderResponse(
                kind="message",
                content=(
                    "Mock provider: nothing further to add on this task. "
                    "Configure a real provider for real agent work."
                ),
            )
        self._fallback_seen = True
        return ProviderResponse(
            kind="message",
            content=(
                "I'm running with the deterministic mock provider (no LLM configured). "
                "No mathematical research was performed. Configure a real provider "
                "in local Research Settings."
            ),
        )
