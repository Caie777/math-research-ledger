"""Model providers behind a common interface.

The provider layer must never leak into core agent logic: the agent loop only
ever talks to :class:`BaseProvider`.
"""

from math_research.agent.providers.base import BaseProvider, ProviderResponse
from math_research.agent.providers.mock_provider import MockProvider

__all__ = ["BaseProvider", "ProviderResponse", "MockProvider"]
