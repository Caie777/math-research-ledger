"""MathResearch Ledger exception hierarchy.

All recoverable, user-facing failures inherit from :class:`ResearchError` so the
CLI can render them as helpful, actionable messages instead of raw tracebacks.
"""

from __future__ import annotations


class ResearchError(Exception):
    """Base class for all MathResearch Ledger errors."""


class IntegrityError(ResearchError):
    """An authoritative source cannot be read or no longer matches its identity."""

    def __init__(self, message: str):
        super().__init__("INTEGRITY_ERROR: " + message)


class RecoverableToolError(ResearchError):
    """An ordinary tool outcome the Agent can repair, not a broken runtime."""

    def __init__(self, message: str, **metadata: object):
        super().__init__(message)
        self.metadata = metadata


class PathTraversalError(ResearchError):
    """Raised when a path would escape the workspace root."""


class WorkspaceError(ResearchError):
    """Raised for workspace initialization or discovery problems."""


class ConfigError(ResearchError):
    """Raised when configuration cannot be loaded or is invalid."""


class PermissionDeniedError(ResearchError):
    """Raised when an action is denied by the permission policy."""


class ProviderError(ResearchError):
    """Raised when a model provider is misconfigured or unavailable."""


def is_recoverable_tool_parse_error(exc: Exception) -> bool:
    """True when the provider failed because model tool-call JSON was invalid."""
    msg = str(exc).lower()
    needles = (
        "error parsing tool call",
        "failed to parse json",
        "unexpected end of json input",
        "parse tool call",
        "invalid character",
    )
    return isinstance(exc, ProviderError) and any(n in msg for n in needles)
