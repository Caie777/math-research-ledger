"""Research Agent recovery hints and callback policy composition."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from math_research.agent.control.models import (
    ALLOW,
    PolicyAction,
    PolicyContext,
    PolicyDecision,
    ReasonCode,
    ToolOutcome,
)

RESEARCH_RECOVERY_HINT = (
    "Continue with an available Research Agent tool; save durable research artifacts."
)


@dataclass(frozen=True)
class HintTexts:
    """The recovery hints a deliverable-driven loop hands the model on a chat-only turn."""

    prove_recovery: str = RESEARCH_RECOVERY_HINT
    prove_gaps_recovery: str = RESEARCH_RECOVERY_HINT
    prove_recovery_after_tools: str = RESEARCH_RECOVERY_HINT
    lit_recovery: str = RESEARCH_RECOVERY_HINT
    lit_recovery_after_tools: str = RESEARCH_RECOVERY_HINT


DEFAULT_HINTS = HintTexts()


def pre_deliverable_block_message(name: str, detail: str) -> str:
    """The rejection a deliverable tool gets when its literature precondition fails.

    Today the only gated deliverable is ``proof_write``, so the text reads exactly as
    it always did; ``name`` keeps it honest for any other deliverable a caller gates.
    """
    return f"Blocked {name}: Research Agent preconditions not met ({detail})."


class CallbackPolicySet:
    """The old ``AgentLoop`` callback kwargs, spoken as a policy set.

    * ``tool_gate(name, args) -> str | None`` → ``before_tool`` (``BLOCK`` /
      ``TOOL_GATE_BLOCKED`` with the gate's text);
    * ``stall_check() -> str | None`` → ``before_turn`` (``STOP`` /
      ``NO_ARTIFACT_PROGRESS`` with the stall text);
    * ``session_gate`` / ``deliverable_complete`` → ``evaluate_completion``.

    The callables are looked up at call time, so a caller that swaps ``tool_gate``
    after construction (a few tests do) is honoured.
    """

    def __init__(
        self,
        *,
        tool_gate: Callable[[str, dict], str | None] | None = None,
        stall_check: Callable[[], str | None] | None = None,
        session_gate: Callable[[], bool] | None = None,
        deliverable_complete: Callable[[], bool] | None = None,
    ) -> None:
        self.tool_gate = tool_gate
        self.stall_check = stall_check
        self.session_gate = session_gate
        self.deliverable_complete = deliverable_complete

    def before_turn(self, ctx: PolicyContext) -> PolicyDecision:
        if self.stall_check is None:
            return ALLOW
        message = self.stall_check()
        if message is None:
            return ALLOW
        return PolicyDecision(
            action=PolicyAction.STOP, reason_code=ReasonCode.NO_ARTIFACT_PROGRESS, message=message
        )

    def before_tool(self, name: str, args: dict) -> PolicyDecision:
        if self.tool_gate is None:
            return ALLOW
        blocked = self.tool_gate(name, args)
        if blocked is None:
            return ALLOW
        return PolicyDecision(
            action=PolicyAction.BLOCK, reason_code=ReasonCode.TOOL_GATE_BLOCKED, message=blocked
        )

    def after_tool(self, outcome: ToolOutcome) -> PolicyDecision:
        return ALLOW

    def evaluate_progress(self, ctx: PolicyContext) -> PolicyDecision:
        return ALLOW

    def evaluate_completion(self, ctx: PolicyContext) -> PolicyDecision:
        if ctx.deliverable_satisfied:
            if self.deliverable_complete is not None and not self.deliverable_complete():
                return PolicyDecision(
                    action=PolicyAction.BLOCK,
                    reason_code=ReasonCode.DELIVERABLE_MISSING,
                    message="deliverable exists but is not complete",
                )
            return ALLOW
        if self.session_gate is not None and self.session_gate():
            return ALLOW
        if self.session_gate is None and self.deliverable_complete is None:
            return ALLOW
        return PolicyDecision(
            action=PolicyAction.BLOCK,
            reason_code=ReasonCode.DELIVERABLE_MISSING,
            message="deliverable not produced yet",
        )
