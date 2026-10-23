"""Event guidance only: no counters, model calls, scheduler or research loop."""

from typing import Literal

MemoryEvent = Literal[
    "session_start",
    "local_reasoning",
    "route_transition",
    "duplicate_risk",
    "premise_reuse",
    "possible_conflict",
    "before_expensive_work",
    "historical_failures",
    "checkpoint",
]


def memory_access(event: MemoryEvent) -> dict:
    """A harness may request this guidance; nothing executes a Ledger call."""
    plans = {
        "session_start": ("RESTORE", ["research_status", "research_context_packet"]),
        "local_reasoning": ("NONE", []),
        "route_transition": ("RETRIEVE", ["research_search"]),
        "duplicate_risk": ("RETRIEVE", ["research_search"]),
        "premise_reuse": ("CHECK_EXACT", ["research_get_object"]),
        "possible_conflict": ("CHECK_EXACT", ["research_get_object"]),
        "before_expensive_work": ("RETRIEVE", ["research_search"]),
        "historical_failures": ("RETRIEVE", ["research_search"]),
        "checkpoint": (
            "CHECKPOINT_IF_CHANGED",
            ["research_ingest_episode:dry_run", "research_ingest_episode"],
        ),
    }
    if event not in plans:
        raise ValueError("Unknown memory event")
    action, tools = plans[event]
    return {
        "event": event,
        "action": action,
        "suggested_tools": tools,
        "guidance_only": True,
        "requires_meaningful_change": event == "checkpoint",
    }
