"""Run-local public recovery state, never canonical mathematics or private reasoning.

Numbered checkpoints atomically cover a prefix of the public progress ledger.
Only the latest compact state and an uncovered tail are used on explicit recovery.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from math_research.agent.state import AgentRun
from math_research.agent.tools import run_path
from math_research.core.atomicio import atomic_write_text as _atomic_write_text
from math_research.core.errors import ResearchError

STATE_CHARS = 10000
CATEGORIES = (
    "RESULT / candidate lemma",
    "Experiments / results",
    "Counterexamples / boundaries",
    "Excluded routes / reasons",
    "Unresolved obstacle",
    "Current route",
    "Artifacts",
    "Next worthwhile action",
)


def read_snapshot(path: Path) -> str:
    """Windows can briefly expose ERROR_ACCESS_DENIED during atomic replacement."""
    for attempt in range(20):
        try:
            return path.read_text("utf-8")
        except PermissionError:
            if os.name != "nt" or attempt == 19:
                raise
            time.sleep(0.01)
    raise AssertionError("unreachable")


def write_snapshot(path: Path, data: str, *, encoding: str = "utf-8") -> None:
    for attempt in range(20):
        try:
            _atomic_write_text(path, data, encoding=encoding)
            return
        except PermissionError:
            if os.name != "nt" or attempt == 19:
                raise
            time.sleep(0.01)


atomic_write_text = write_snapshot


class PublicCheckpoint:
    def __init__(self, folder: Path, run: AgentRun, *, repair: bool = True):
        self.folder, self.run = folder, run
        self.ledger = folder / "public_progress.jsonl"
        self.state_path = folder / "checkpoint" / "state.json"
        self.state = json.loads(read_snapshot(self.state_path)) if self.state_path.exists() else {}
        self.tail: list[dict] = []
        self.cursor = int(self.state.get("offset", 0))
        self.sequence = int(self.state.get("covered_through", 0))
        self.suspend_periodic = False
        # Seek directly past covered history; never load/replay the old ledger.
        if self.ledger.exists():
            with self.ledger.open("rb") as handle:
                handle.seek(self.cursor)
                while raw := handle.readline():
                    try:
                        item = json.loads(raw)
                    except ValueError:
                        # A torn final append is not a published progress record.
                        break
                    self.tail.append(item)
                    self.sequence = max(self.sequence, item["id"])
                    self.cursor = handle.tell()
            if repair and self.ledger.stat().st_size != self.cursor:
                with self.ledger.open("r+b") as handle:
                    handle.truncate(self.cursor)
        self.run.effective_steps = max(self.run.effective_steps, self.sequence)
        self.refresh()

    def refresh(self) -> None:
        self.run.latest_checkpoint = self.state.get("file")
        self.run.last_checkpoint_step = int(self.state.get("step", 0))
        self.run.uncheckpointed_public_events = len(self.tail)

    def publish(self, kind: str, content: str, *, category: str | None = None) -> None:
        if not content.strip():
            return
        digest = hashlib.sha256((kind + content).encode()).hexdigest()
        # Repeated observations are not effective progress.
        seen = set(self.state.get("digests", [])) | {p["digest"] for p in self.tail}
        if digest in seen:
            return
        self.sequence += 1
        path = f"artifacts/public-{self.sequence:06d}-{uuid4().hex[:8]}.txt"
        atomic_write_text(run_path(self.folder, path), content, encoding="utf-8")
        item = {
            "at": datetime.now(UTC).isoformat(),
            "id": self.sequence,
            "step": self.sequence,
            "kind": kind,
            "category": category or self.category(kind, content),
            "summary": content[:700],
            "artifact": path,
            "digest": digest,
        }
        payload = (json.dumps(item, ensure_ascii=False) + "\n").encode()
        with self.ledger.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            self.cursor = handle.tell()
        self.tail.append(item)
        self.run.effective_steps = self.sequence
        self.refresh()
        from math_research.agent.progress import update_progress

        update_progress(self.folder, self.run, public=item)
        if (
            not self.suspend_periodic
            and self.sequence - self.run.last_checkpoint_step
            >= self.run.request.checkpoint_every_effective_steps
        ):
            self.checkpoint("periodic")

    @staticmethod
    def category(kind: str, content: str) -> str:
        text = (kind + " " + content).lower()
        for needles, category in [
            (("counterexample", "反例", "exception", "boundary"), CATEGORIES[2]),
            (("failed", "exclude", "排除", "failure"), CATEGORIES[3]),
            (("unresolved", "obstacle", "gap", "障碍"), CATEGORIES[4]),
            (("next action", "next step", "下一步"), CATEGORIES[7]),
            (("current route", "当前路线"), CATEGORIES[5]),
            (("python", "experiment", "gap:", "singular", "实验"), CATEGORIES[1]),
            (("artifact",), CATEGORIES[6]),
        ]:
            if any(word in text for word in needles):
                return category
        return CATEGORIES[0]

    def checkpoint(self, reason: str) -> str:
        from math_research.agent.progress import update_progress

        update_progress(self.folder, self.run, phase="checkpointing")
        groups = dict(self.state.get("groups", {}))
        for item in self.tail:
            group = list(groups.get(item["category"], []))
            summary = " ".join(item["summary"].split())[:400]
            group.append(f"- [{item['id']}] {summary}\n  Full public source: {item['artifact']}")
            groups[item["category"]] = group[-2:]
        number = int(self.state.get("number", 0)) + 1
        file = f"checkpoint/{number:04d}.md"
        body = (
            f"# Public research recovery state — {self.run.run_id}\n"
            f"Target: {self.run.request.target.node_id}; effective step: {self.sequence}\n"
            f"Reason: {reason}; public progress covered: 1..{self.sequence}\n"
            "Authority: provisional / unverified; not Human Accept or theorem truth.\n"
            "Exact earlier public records remain in public_progress.jsonl and linked artifacts; "
            "read selected sources only if needed, never replay all history.\n\n"
        )
        for category in CATEGORIES:
            body += (
                f"## {category}\n"
                + "\n".join(groups.get(category, ["No explicit public record yet."]))
                + "\n\n"
            )
        if len(body) > STATE_CHARS:
            raise ResearchError("Public checkpoint exceeded bounded state size.")
        atomic_write_text(run_path(self.folder, file), body, encoding="utf-8")
        digests = set(self.state.get("digests", [])) | {p["digest"] for p in self.tail}
        new_state = {
            "created_at": datetime.now(UTC).isoformat(),
            "number": number,
            "file": file,
            "step": self.sequence,
            "covered_through": self.sequence,
            "offset": self.cursor,
            "groups": groups,
            "digests": sorted(digests),
            "artifact_inventory": self.state.get("artifact_inventory", {}),
        }
        # state.json is the commit point. On recovery its numbered file is authoritative.
        atomic_write_text(
            self.state_path, json.dumps(new_state, ensure_ascii=False), encoding="utf-8"
        )
        atomic_write_text(self.folder / "checkpoint/latest.md", body, encoding="utf-8")
        self.state, self.tail = new_state, []
        self.refresh()
        update_progress(
            self.folder,
            self.run,
            checkpoint=(number, datetime.fromisoformat(new_state["created_at"])),
        )
        return body

    def latest(self) -> str:
        if not self.state:
            return "No rolling checkpoint yet."
        return run_path(self.folder, self.state["file"]).read_text("utf-8")

    def collect_artifacts(self) -> None:
        known = dict(self.state.get("artifact_inventory", {}))
        original_sequence = self.sequence
        for area in ("work", "artifacts"):
            base = self.folder / area
            for path in sorted(base.rglob("*")):
                if not path.is_file() or path.is_symlink() or path.name.startswith(".sandbox"):
                    continue
                if (
                    path.name.startswith("public-")
                    and path.name.split("-")[1].isdigit()
                    and int(path.name.split("-")[1]) <= original_sequence
                ):
                    continue
                relative = path.relative_to(self.folder).as_posix()
                run_path(self.folder, relative)
                signature = f"{path.stat().st_size}:{path.stat().st_mtime_ns}"
                if known.get(relative) == signature:
                    continue
                with path.open("rb") as handle:
                    preview = handle.read(1200).decode("utf-8", errors="replace")
                self.publish(
                    "artifact",
                    f"{relative}; bytes={path.stat().st_size}\n{preview}",
                    category=CATEGORIES[6],
                )
                known[relative] = signature
        # This metadata is also retained when the last record is not yet checkpointed.
        self.state["artifact_inventory"] = known

    def recover(self) -> str:
        self.suspend_periodic = True
        self.collect_artifacts()
        # FIRST operation: absorb every uncovered public record into a new state.
        count = len(self.tail)
        body = self.checkpoint(f"recovery absorbed {count} uncovered public events")
        self.suspend_periodic = False
        self.run.usage["recovery_absorbed_events"] = count
        atomic_write_text(
            self.folder / "checkpoint" / f"recovery-{self.run.attempt:04d}.md",
            body,
            encoding="utf-8",
        )
        return body

    def final_coverage(self) -> str:
        self.collect_artifacts()
        self.checkpoint("final Episode coverage")
        return (
            "\n\n# Public run coverage (operational)\n\n"
            f"Public progress 1..{self.sequence} is covered by {self.run.latest_checkpoint}.\n"
            + self.latest().replace("## ", "### ")
        )


@contextmanager
def run_lease(folder: Path, *, create: bool = True) -> Iterator[None]:
    """OS-owned nonblocking lease. Process death releases it immediately."""
    path = folder / "run.lease"
    with path.open("a+b" if create else "r+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                platform_lock = cast(Any, fcntl)
                platform_lock.flock(handle.fileno(), platform_lock.LOCK_EX | platform_lock.LOCK_NB)
        except OSError as exc:
            raise ResearchError("Research run is still attached to a live executor.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                cast(Any, fcntl).flock(handle.fileno(), cast(Any, fcntl).LOCK_UN)


def lease_available(folder: Path) -> bool:
    if not (folder / "run.lease").exists():
        return True
    try:
        with run_lease(folder, create=False):
            return True
    except (ResearchError, OSError):
        return False
