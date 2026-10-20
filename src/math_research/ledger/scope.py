"""Optional execution thread metadata; no separate memory or authority store."""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from functools import wraps
from typing import ParamSpec, TypeVar

from math_research.core.errors import ResearchError

_THREAD: ContextVar[str | None] = ContextVar("research_thread", default=None)
P = ParamSpec("P")
R = TypeVar("R")


def thread_ids() -> list[str]:
    value = _THREAD.get()
    return [value] if value else []


def threaded_research(function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        value = (
            kwargs.get("thread_id")
            or (getattr(args[0], "research_thread_id", None) if args else None)
            or _THREAD.get()
        )
        if value is not None and (
            not isinstance(value, str) or not value.strip() or len(value) > 128
        ):
            raise ResearchError("Thread ID must contain 1–128 characters.")
        token = _THREAD.set(value)
        try:
            return function(*args, **kwargs)
        finally:
            _THREAD.reset(token)

    return wrapped
