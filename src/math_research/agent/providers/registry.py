"""Resolve a provider from configuration.

Real providers are imported lazily so that missing optional SDKs never break
``import math_research``. An unknown provider name raises a clear ProviderError.
"""

from __future__ import annotations

from math_research.agent.providers.base import BaseProvider
from math_research.agent.providers.mock_provider import MockProvider
from math_research.core.config import Config
from math_research.core.errors import ProviderError


def get_provider(config: Config) -> BaseProvider:
    name = config.model.provider.lower()
    if name == "mock":
        return MockProvider()
    if name == "openai":
        from math_research.agent.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(config)
    if name == "anthropic":
        from math_research.agent.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(config)
    if name == "ollama":
        from math_research.agent.providers.ollama_provider import OllamaProvider

        return OllamaProvider(config)
    if name == "mistral":
        from math_research.agent.providers.mistral_provider import MistralProvider

        return MistralProvider(config)
    raise ProviderError(
        f"Unknown provider '{config.model.provider}'. "
        "Valid providers: mock, openai, anthropic, ollama, mistral."
    )
