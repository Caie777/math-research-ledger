"""Keep automated research out of canonical mathematical facts and human reviews.

Explicit Problem registration/lifecycle is a separate project-scope capability;
its semantic statements remain provisional. It cannot write Claim facts or receipts.

The context is execution provenance, not an approval token. Human acceptance is
the existing review_candidate service, invoked outside an automated run.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import ParamSpec, TypeVar

from math_research.core.errors import ResearchError

_AUTOMATED: ContextVar[bool] = ContextVar("automated_research", default=False)
AUTOMATED_ENV = "SMR_AUTOMATED_RESEARCH"
LEGACY_AUTOMATED_ENV = "MCH_AUTOMATED_RESEARCH"
P = ParamSpec("P")
R = TypeVar("R")


def is_automated() -> bool:
    return _AUTOMATED.get() or any(
        os.environ.get(key) == "1" for key in (AUTOMATED_ENV, LEGACY_AUTOMATED_ENV)
    )


@contextmanager
def automated_scope() -> Iterator[None]:
    token = _AUTOMATED.set(True)
    try:
        yield
    finally:
        _AUTOMATED.reset(token)


def automated_research(function: Callable[P, R]) -> Callable[P, R]:
    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        with automated_scope():
            return function(*args, **kwargs)

    return wrapped


def assert_human_write() -> None:
    if is_automated():
        raise ResearchError(
            "Automated research cannot commit Problem Record facts or decide human reviews. "
            "Stage an Episode candidate, then use Human Review / Accept. "
            "Verifier acceptance is not human acceptance."
        )


def human_write(function: Callable[P, R]) -> Callable[P, R]:
    """Reject automated callers before any body/file/index mutation."""

    @wraps(function)
    def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        assert_human_write()
        return function(*args, **kwargs)

    return wrapped
