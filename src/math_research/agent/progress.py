"""Durable operational projection, never mathematical authority.

ResearchRunProgress is not Claim truth, Research State, Final Episode, Candidate,
or Human Review authority. Those remain with structured memory / Episode / Review.
Readers never repair, migrate, or materialize historical runs. Only explicit runtime
transitions write this snapshot; no token deltas, private reasoning, or log scraping.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from math_research.agent.checkpoint import read_snapshot, write_snapshot
from math_research.agent.state import AgentBudget, AgentRun, StopReason
from math_research.core.atomicio import file_lock

Phase = Literal[
    "initializing",
    "loading_context",
    "researching",
    "using_tools",
    "checkpointing",
    "finalizing",
    "stopping",
    "terminal",
]


class PublicProgress(BaseModel):
    """Only fields from the existing public progress ledger are eligible."""

    model_config = ConfigDict(extra="forbid")
    id: int = Field(ge=1)
    kind: str = Field(
        max_length=160,
        pattern=r"^(public_model_result|public_milestone|artifact|tool_observation:[\w.:-]+)$",
    )
    summary: str = Field(max_length=700)


class ResearchRunProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    run_id: str
    problem_id: str
    target_id: str
    # Preserve AgentRun's actual lifecycle; terminal outcome is stop_reason.
    status: Literal["running", "finished"]
    current_phase: Phase
    started_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    last_checkpoint_at: datetime | None = None
    finished_at: datetime | None = None
    step_count: int = Field(default=0, ge=0)
    model_call_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    checkpoint_count: int = Field(default=0, ge=0)
    public_event_count: int = Field(default=0, ge=0)
    budget: AgentBudget
    stop_reason: StopReason | None = None
    error_type: Literal["MODEL_FAILURE", "TOOL_FAILURE", "RUN_ERROR"] | None = None
    latest_public_progress: PublicProgress | None = None
    stop_requested: bool = False
    source: Literal["snapshot", "reconstructed"] = "snapshot"
    snapshot_error: bool = False

    @model_validator(mode="after")
    def consistent_lifecycle(self) -> Self:
        if self.status == "finished" and (
            self.current_phase != "terminal" or self.finished_at is None
        ):
            raise ValueError("Finished progress requires terminal phase and finished_at")
        if self.status == "running" and (
            self.current_phase == "terminal" or self.finished_at is not None
        ):
            raise ValueError("Running progress cannot be terminal")
        return self


def _time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value)
        return result.replace(tzinfo=UTC) if result.tzinfo is None else result
    except ValueError:
        return None


def _records(path: Path) -> Iterator[dict]:
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                item = json.loads(line)
            except ValueError:
                continue  # Torn appends are not structured records.
            if isinstance(item, dict):
                yield item


def _public(item: dict) -> PublicProgress | None:
    # Only public-ledger summaries; never open arbitrary artifacts, notes or logs.
    kind = item.get("kind", "")
    if not isinstance(kind, str) or not (
        kind in {"public_model_result", "public_milestone", "artifact"}
        or kind.startswith("tool_observation:")
    ):
        return None
    try:
        return PublicProgress(id=item["id"], kind=kind[:160], summary=item["summary"][:700])
    except (KeyError, TypeError, ValidationError):
        return None


def _phase(run: AgentRun) -> Phase:
    if run.status == "finished":
        return "terminal"
    if run.current_action in {"context", "recovery"}:
        return "loading_context"
    return "researching" if run.current_action == "model" else "using_tools"


def _run_fields(run: AgentRun) -> dict:
    return dict(
        status=run.status,
        finished_at=run.ended_at,
        step_count=run.steps,
        model_call_count=run.model_calls,
        tool_call_count=run.tool_calls,
        stop_reason=run.stop_reason,
        error_type=run.stop_reason
        if run.stop_reason in {"MODEL_FAILURE", "TOOL_FAILURE"}
        else "RUN_ERROR"
        if run.error
        else None,
    )


def reconstruct_progress(folder: Path, run: AgentRun) -> ResearchRunProgress:
    """Deterministic, read-only legacy fallback from structured records, never logs.

    Old records lack timestamps in places. A checkpoint's file mtime is a stable
    fallback; unknown activity falls back to start/end, never the time of a poll.
    Numbered checkpoints count rolling recovery snapshots, not final Episode files.
    """
    activity = run.started_at
    checkpoint_at = None
    checkpoint_count = public_count = 0
    latest = None
    for event in _records(folder / "events.jsonl"):
        at = _time(event.get("at"))
        if at:
            activity = max(activity, at)
    state_path = folder / "checkpoint/state.json"
    try:
        state = json.loads(read_snapshot(state_path))
        if isinstance(state, dict):
            number = state.get("number", 0)
            if type(number) is int and number > 0:
                checkpoint_count = number
                checkpoint_at = _time(state.get("created_at")) or datetime.fromtimestamp(
                    state_path.stat().st_mtime, UTC
                )
    except (OSError, ValueError):
        pass
    # Older runs may predate rolling state.json altogether.
    if checkpoint_at is None and run.checkpoint_path:
        path = (folder / run.checkpoint_path).resolve()
        if path.is_relative_to(folder.resolve()) and path.is_file():
            checkpoint_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    for item in _records(folder / "public_progress.jsonl"):
        public = _public(item)
        if public and public.id > public_count:
            public_count, latest = public.id, public
        at = _time(item.get("at"))
        if at:
            activity = max(activity, at)
    activity = max(activity, checkpoint_at or activity, run.ended_at or activity)
    return ResearchRunProgress(
        run_id=run.run_id,
        problem_id=run.request.target.problem_id,
        target_id=run.request.target.node_id,
        current_phase=_phase(run),
        started_at=run.started_at,
        updated_at=activity,
        last_activity_at=activity,
        last_checkpoint_at=checkpoint_at,
        checkpoint_count=checkpoint_count,
        public_event_count=public_count,
        latest_public_progress=latest,
        budget=run.request.budget,
        source="reconstructed",
        **_run_fields(run),
    )


def read_progress(folder: Path, run: AgentRun | None = None) -> ResearchRunProgress:
    """Fast snapshot read; a corrupt/foreign/unsupported snapshot falls back read-only."""
    try:
        progress = ResearchRunProgress.model_validate_json(read_snapshot(folder / "progress.json"))
        if progress.run_id != folder.name or (
            run is not None
            and (
                progress.problem_id != run.request.target.problem_id
                or progress.target_id != run.request.target.node_id
            )
        ):
            raise ValueError("Snapshot scope mismatch")
        if (
            run is not None
            and run.status == "finished"
            and (progress.status != "finished" or progress.finished_at != run.ended_at)
        ):
            # Crash between the run.json commit and its projection write. Metadata
            # proves completion; recover read-only rather than poll running forever.
            raise ValueError("Snapshot predates the terminal run metadata")
        return progress
    except (OSError, ValueError):
        if run is None:
            run = AgentRun.model_validate_json(read_snapshot(folder / "run.json"))
        progress = reconstruct_progress(folder, run)
        progress.snapshot_error = (folder / "progress.json").exists()
        return progress


def update_progress(
    folder: Path,
    run: AgentRun | None = None,
    *,
    phase: Phase | None = None,
    public: dict | None = None,
    checkpoint: tuple[int, datetime] | None = None,
    stop_requested: bool = False,
    resumed: bool = False,
) -> ResearchRunProgress:
    """Only writers lock; API/operator reads never create a lock or any other file.

    Serialize stop requests with executor writes, including across processes. A stop
    update never replaces live counters with an earlier run.json read.
    """
    with file_lock(folder / "progress.json"):
        progress = read_progress(folder, run)
        if stop_requested and progress.status == "finished":
            return progress
        now = datetime.now(UTC)
        if run is not None:
            progress = progress.model_copy(update=_run_fields(run))
            progress.current_phase = phase or _phase(run)
            if run.status == "finished":
                persisted = AgentRun.model_validate_json(read_snapshot(folder / "run.json"))
                if persisted.status != "finished" or persisted.ended_at != run.ended_at:
                    # Initialization failure may still be staging its final Episode.
                    # Do not stop clients before final output metadata is committed.
                    progress.status, progress.finished_at = "running", None
                    progress.current_phase = "finalizing"
        if public is not None and (item := _public(public)) is not None:
            progress.latest_public_progress = item
            progress.public_event_count = max(progress.public_event_count, item.id)
        if checkpoint:
            progress.checkpoint_count, progress.last_checkpoint_at = checkpoint
        if resumed:
            progress.stop_requested = False
        if stop_requested and progress.status == "running":
            progress.stop_requested = True
        if progress.stop_requested and progress.status == "running":
            progress.current_phase = "stopping"
        if progress.status == "finished":
            progress.current_phase = "terminal"
        progress.updated_at = progress.last_activity_at = now
        progress.source, progress.snapshot_error = "snapshot", False
        # Validate after model_copy as well; writes always obey the public schema.
        progress = ResearchRunProgress.model_validate(progress.model_dump())
        write_snapshot(folder / "progress.json", progress.model_dump_json(indent=2))
        return progress
