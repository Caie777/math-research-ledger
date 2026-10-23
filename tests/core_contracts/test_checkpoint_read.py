"""Read-only consistency fences and controlled publication races; synthetic only."""

import errno
import io
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest

from math_research.core.errors import ResearchError
from math_research.ledger import checkpoint
from math_research.ledger.episodes import list_candidates, list_episodes
from math_research.ledger.manifest import Ledger
from math_research.ledger.records import store
from math_research.mcp.adapter import LedgerAdapter
from math_research.services.ingest import ingest_episode


def inventory(state):
    return {p.relative_to(state): p.read_bytes() for p in state.rglob("*") if p.is_file()}


@pytest.fixture
def deny_state_writes(research, monkeypatch, request):
    """Portable OS-API denial, including mkdir(existing), not Windows readonly bits."""
    state, _ = research
    if getattr(request, "param", False):
        (state / checkpoint.GENERATION).write_bytes(b"a" * 32)
    root = state.resolve()
    denied = []

    def protected(path):
        return isinstance(path, (str, bytes, os.PathLike)) and Path(
            os.fsdecode(path)
        ).resolve().is_relative_to(root)

    def deny(path):
        denied.append(str(path))
        raise PermissionError(errno.EACCES, "Synthetic state directory is read-only", str(path))

    opened = io.open

    def open_file(path, mode="r", *args, **kwargs):
        if any(flag in mode for flag in "wax+") and protected(path):
            deny(path)
        return opened(path, mode, *args, **kwargs)

    monkeypatch.setattr(io, "open", open_file)
    opened_fd = os.open

    def open_fd(path, flags, *args, **kwargs):
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC) and protected(
            path
        ):
            deny(path)
        return opened_fd(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", open_fd)
    for name in ("mkdir", "remove", "unlink", "rmdir", "rename", "replace"):
        original = getattr(os, name)

        def mutation(path, *args, _original=original, **kwargs):
            if protected(path) or args and protected(args[0]):
                deny(path)
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(os, name, mutation)
    return denied


@pytest.mark.parametrize(
    "tool",
    [
        "research_status",
        "research_search",
        "research_get_object",
        "research_context_packet",
        "research_review_packet",
        "research_stale_report",
        "preview",
    ],
)
@pytest.mark.parametrize("deny_state_writes", [False, True], indirect=True)
def test_pure_mcp_calls_need_no_state_write(research, deny_state_writes, tool):
    state, ref = research
    before = inventory(state)
    calls = {
        "research_status": {"problem_id": ref.problem_id},
        "research_search": {"query": ref.object_id, "problem_id": ref.problem_id},
        "research_get_object": {"ref": ref.qualified_id},
        "research_context_packet": {"ref": ref.qualified_id, "token_budget": 8000},
        "research_review_packet": {"ref": ref.qualified_id},
        "research_stale_report": {"problem_id": ref.problem_id},
        "preview": {
            "problem_id": ref.problem_id,
            "markdown": "## Claim: fixture\n\nSynthetic only.\n",
            "provenance": "synthetic",
            "dry_run": True,
        },
    }
    result = LedgerAdapter(state).call(
        "research_ingest_episode" if tool == "preview" else tool, calls[tool]
    )
    assert result and not deny_state_writes
    assert inventory(state) == before
    assert not (state / ".checkpoint.lock").exists()
    assert (state / checkpoint.GENERATION).exists() == (Path(checkpoint.GENERATION) in before)


def test_read_only_guard_really_denies_writes(research, deny_state_writes):
    state, _ = research
    with (
        pytest.raises(ResearchError, match="read-only"),
        checkpoint.file_lock(state / ".checkpoint"),
    ):
        pytest.fail("A writer entered read-only state")
    assert deny_state_writes


def test_stable_state_runs_operation_once_without_lock(research, monkeypatch):
    state, _ = research
    calls = []
    monkeypatch.setattr(checkpoint, "file_lock", lambda *a: pytest.fail("Read took a lock"))
    assert (
        checkpoint.consistent_checkpoint_read(state, lambda: calls.append(1) or "stable")
        == "stable"
    )
    assert calls == [1]
    assert not (state / checkpoint.GENERATION).exists()


def test_changes_exhaust_budget_and_sleep_between_retries(research, monkeypatch):
    state, ref = research
    calls, sleeps = [], []
    monkeypatch.setattr(checkpoint.time, "sleep", sleeps.append)

    def change():
        calls.append(1)
        dossier = store.require_dossier(state, ref.problem_id)
        store.save_dossier(
            state, dossier.model_copy(update={"title": f"Synthetic change {len(calls)}"})
        )
        return "must not escape"

    with pytest.raises(ResearchError, match="after 3 attempts.*stable checkpoint"):
        checkpoint.consistent_checkpoint_read(state, change)
    assert calls == [1, 1, 1] and sleeps == [0.02, 0.02]


def test_stable_operation_error_is_not_replayed(research):
    state, _ = research
    calls = []

    def fail():
        calls.append(1)
        raise ResearchError("Synthetic stable error")

    with pytest.raises(ResearchError, match="Synthetic stable error"):
        checkpoint.consistent_checkpoint_read(state, fail)
    assert calls == [1]


def test_unstable_operation_error_retries_instead_of_escaping(research):
    state, ref = research
    calls = []

    def read():
        calls.append(1)
        if len(calls) == 1:
            ingest_episode(
                state,
                ref.problem_id,
                "fixture.md",
                b"## Claim: fixture\n\nSynthetic.\n",
                provenance="synthetic",
            )
            raise ResearchError("Synthetic intermediate view")
        return "stable"

    assert checkpoint.consistent_checkpoint_read(state, read) == "stable"
    assert calls == [1, 1]


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows readonly bits do not enforce directory permissions; denial tests apply",
)
def test_posix_readonly_permissions_allow_mcp_reads(research):
    if os.geteuid() == 0:
        pytest.skip("Root bypasses POSIX directory write permissions")
    import stat

    state, ref = research
    before = inventory(state)
    entries = [state, *state.rglob("*")]
    modes = {p: stat.S_IMODE(p.stat().st_mode) for p in entries}
    try:
        for p in entries:
            p.chmod(0o555 if p.is_dir() else 0o444)
        with pytest.raises(PermissionError):
            (state / "write-probe").write_bytes(b"must fail")
        adapter = LedgerAdapter(state)
        assert adapter.call("research_status", {"problem_id": ref.problem_id})["objects"] == 2
        assert adapter.call("research_search", {"query": ref.object_id})["hits"]
        assert adapter.call("research_context_packet", {"ref": ref.qualified_id})["target"]
        assert inventory(state) == before
    finally:
        for p, mode in modes.items():
            p.chmod(mode)


@pytest.mark.parametrize("marker", [b"", b"not-a-generation", b"a" * 33])
def test_invalid_generation_fails_closed_without_repair(research, marker):
    state, _ = research
    path = state / checkpoint.GENERATION
    path.write_bytes(marker)
    with pytest.raises(ResearchError, match="Invalid checkpoint generation"):
        checkpoint.consistent_checkpoint_read(state, lambda: pytest.fail("Invalid marker accepted"))
    assert path.read_bytes() == marker


@pytest.mark.parametrize("filename", [checkpoint.JOURNAL, checkpoint.GENERATION])
def test_unreadable_control_state_fails_promptly(research, monkeypatch, filename):
    state, _ = research
    if filename == checkpoint.JOURNAL:
        original = Path.lstat

        def lstat(path, *args, **kwargs):
            if path == state / filename:
                raise PermissionError("Synthetic unreadable journal")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "lstat", lstat)
    else:
        original = Path.open

        def open_file(path, *args, **kwargs):
            if path == state / filename:
                raise PermissionError("Synthetic unreadable generation")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", open_file)
    with pytest.raises(ResearchError, match="Cannot (inspect|read) checkpoint"):
        checkpoint.consistent_checkpoint_read(
            state, lambda: pytest.fail("Unreadable state accepted")
        )


def test_missing_state_never_initializes(tmp_path):
    state = tmp_path / "missing"
    with pytest.raises(ResearchError, match="never initializes"):
        checkpoint.consistent_checkpoint_read(state, lambda: pytest.fail("Missing state accepted"))
    assert not state.exists()


def test_writer_keeps_original_state_lock_and_generation_is_not_an_object_version(
    research, monkeypatch
):
    state, ref = research
    original = checkpoint.file_lock
    locks = []
    before = Ledger(state).source_version()

    @contextmanager
    def observed(path):
        locks.append(path)
        with original(path):
            assert (state / ".checkpoint.lock").is_file()
            yield

    monkeypatch.setattr(checkpoint, "file_lock", observed)
    with checkpoint.checkpoint_transaction(state, ref.problem_id):
        assert (state / checkpoint.JOURNAL).is_file()
        with pytest.raises(ResearchError, match="active checkpoint"):
            checkpoint.consistent_checkpoint_read(state, lambda: None)
    assert locks == [state / ".checkpoint"]
    assert len((state / checkpoint.GENERATION).read_bytes()) == 32
    assert Ledger(state).source_version() == before
    assert not (state / ".checkpoint.lock").exists()


def test_reader_rejects_half_published_indexes(research, monkeypatch):
    from math_research.services import ingest

    state, ref = research
    archived, finish = threading.Event(), threading.Event()
    original = ingest.extract_candidates

    def paused(*args):
        archived.set()
        assert finish.wait(10)
        return original(*args)

    monkeypatch.setattr(ingest, "extract_candidates", paused)
    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(
            ingest_episode,
            state,
            ref.problem_id,
            "fixture.md",
            b"## Claim: concurrent fixture\n\nSynthetic.\n",
            provenance="synthetic",
        )
        try:
            assert archived.wait(10)
            assert (state / "research_archive/index.jsonl").read_bytes()
            assert not list_candidates(state, ref.problem_id)
            with pytest.raises(ResearchError, match="pending or interrupted"):
                LedgerAdapter(state).call("research_status", {"problem_id": ref.problem_id})
        finally:
            finish.set()
        writer.result(timeout=10)
    assert (
        LedgerAdapter(state).call("research_status", {"problem_id": ref.problem_id})["objects"] == 4
    )


def test_writer_finishing_mid_read_replays_entire_mcp_operation(research, monkeypatch):
    state, ref = research
    go, done = threading.Event(), threading.Event()
    adapter = LedgerAdapter(state)
    original, counts = adapter._call, []

    def operation(name, arguments):
        value = original(name, arguments)
        counts.append(value["objects"])
        if len(counts) == 1:
            go.set()
            assert done.wait(10)
        return value

    monkeypatch.setattr(adapter, "_call", operation)

    def publish():
        assert go.wait(10)
        try:
            ingest_episode(
                state,
                ref.problem_id,
                "fixture.md",
                b"## Claim: new\n\nSynthetic.\n",
                provenance="synthetic",
            )
        finally:
            done.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(publish)
        value = adapter.call("research_status", {"problem_id": ref.problem_id})
        writer.result(timeout=10)
    assert counts == [2, 4] and value["objects"] == 4


def test_rollback_aba_invalidates_read_even_with_identical_source_version(research, monkeypatch):
    from math_research.services import ingest

    state, ref = research
    version = Ledger(state).source_version()
    go, dirty, rollback, done = (threading.Event() for _ in range(4))
    original = ingest.extract_candidates
    observed = []

    def fail(*args):
        original(*args)
        dirty.set()
        assert rollback.wait(10)
        raise OSError("Synthetic failed publication")

    monkeypatch.setattr(ingest, "extract_candidates", fail)

    def publish():
        assert go.wait(10)
        try:
            with pytest.raises(OSError, match="Synthetic failed publication"):
                ingest_episode(
                    state,
                    ref.problem_id,
                    "fixture.md",
                    b"## Claim: transient\n\nSynthetic.\n",
                    provenance="synthetic",
                )
        finally:
            done.set()

    def read_raw():
        if not observed:
            go.set()
            assert dirty.wait(10)
        paths = [
            state / "research_archive/index.jsonl",
            state / "problems" / ref.problem_id / "archive/episodes/candidates.jsonl",
        ]
        value = tuple(len(p.read_bytes().splitlines()) if p.exists() else 0 for p in paths)
        observed.append(value)
        if len(observed) == 1:
            rollback.set()
            assert done.wait(10)
        return value

    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(publish)
        try:
            value = checkpoint.consistent_checkpoint_read(state, read_raw)
        finally:
            rollback.set()
        writer.result(timeout=10)
    assert observed == [(1, 1), (0, 0)] and value == (0, 0)
    assert Ledger(state).source_version() == version
    assert not (state / checkpoint.JOURNAL).exists()


def test_change_during_fingerprint_is_not_accepted(research, monkeypatch):
    state, ref = research
    original, fingerprints, operations = checkpoint._state_fingerprint, [], []

    def changed(root):
        value = original(root)
        fingerprints.append(value)
        if len(fingerprints) == 1:
            ingest_episode(
                state,
                ref.problem_id,
                "fixture.md",
                b"## Claim: during fence\n\nSynthetic.\n",
                provenance="synthetic",
            )
        return value

    monkeypatch.setattr(checkpoint, "_state_fingerprint", changed)
    assert (
        checkpoint.consistent_checkpoint_read(state, lambda: operations.append(1) or "stable")
        == "stable"
    )
    assert len(fingerprints) == 3 and operations == [1]


def test_legacy_missing_timestamps_do_not_create_false_read_conflicts(research):
    import json

    state, ref = research
    path = state / "problems" / ref.problem_id / "claims.jsonl"
    row = json.loads(path.read_text("utf-8"))
    row.pop("created_at")
    row.pop("updated_at")
    path.write_text(json.dumps(row) + "\n", "utf-8")
    before = inventory(state)
    assert checkpoint._fingerprint(state) == checkpoint._fingerprint(state)
    assert LedgerAdapter(state).call("research_status", {})["objects"] == 2
    assert inventory(state) == before


def test_content_change_is_detected_even_when_mtime_and_object_versions_match(research):
    state, _ = research
    path = state / "config.yaml"
    path.write_text("fixture: A\n", "utf-8")
    times = path.stat()
    versions = [(e.qualified_id, e.version) for e in Ledger(state).objects()]
    observed = []

    def read():
        value = path.read_text("utf-8")
        observed.append(value)
        if len(observed) == 1:
            path.write_text("fixture: B\n", "utf-8")
            os.utime(path, ns=(times.st_atime_ns, times.st_mtime_ns))
        return value

    assert checkpoint.consistent_checkpoint_read(state, read) == "fixture: B\n"
    assert observed == ["fixture: A\n", "fixture: B\n"]
    assert path.stat().st_mtime_ns == times.st_mtime_ns
    assert [(e.qualified_id, e.version) for e in Ledger(state).objects()] == versions


def test_request_acceptance_remains_a_nonreplayable_write(research, monkeypatch):
    state, ref = research
    monkeypatch.setattr(checkpoint, "_fingerprint", lambda *a: pytest.fail("Write was replayable"))
    with pytest.raises(ResearchError, match="existing passed"):
        LedgerAdapter(state).call(
            "research_request_acceptance", {"ref": ref.qualified_id, "verification_id": "missing"}
        )


def test_process_crash_blocks_reads_and_existing_recovery_restores_indexes(research):
    state, ref = research
    before = Ledger(state).source_version()
    worker = """
import os,sys
from pathlib import Path
from datetime import UTC,datetime
from math_research.ledger.checkpoint import checkpoint_transaction
from math_research.ledger.archive import archive_source
state=Path(sys.argv[1])
with checkpoint_transaction(state,sys.argv[2]):
    archive_source(state,sys.argv[2],'crash.md',b'## Claim: crash fixture\\n\\nSynthetic.\\n',
                   datetime.now(UTC),related_problem_ids=[],thread_ids=[],
                   provenance='synthetic',source_language=None)
    os._exit(23)
"""
    crashed = subprocess.run(
        [sys.executable, "-B", "-c", worker, str(state), ref.problem_id], timeout=20
    )
    assert crashed.returncode == 23
    with pytest.raises(ResearchError, match="recover"):
        LedgerAdapter(state).call("research_status", {})
    # Age only this synthetic dead holder; retain normal stale-lock recovery semantics.
    os.utime(state / ".checkpoint.lock", (1, 1))
    assert checkpoint.recover_checkpoint(state)["recovered"]
    assert Ledger(state).source_version() == before
    assert not list_episodes(state)
    assert len(list((state / "research_archive").rglob("*.md"))) == 1
    assert LedgerAdapter(state).call("research_status", {})["objects"] == 2


def test_concurrent_process_writers_and_reader_keep_complete_checkpoints(research):
    state, ref = research
    worker = """
import sys
from pathlib import Path
from math_research.services.ingest import ingest_episode
state=Path(sys.argv[1])
for i in range(3):
    raw=f'## Claim: process {sys.argv[3]} item {i}\\n\\nSynthetic only.\\n'.encode()
    ingest_episode(state,sys.argv[2],'fixture.md',raw,provenance='synthetic process')
"""
    jobs = [
        subprocess.Popen(
            [sys.executable, "-B", "-c", worker, str(state), ref.problem_id, str(i)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for i in range(2)
    ]
    accepted = []
    try:
        deadline = time.monotonic() + 40
        while any(job.poll() is None for job in jobs):
            assert time.monotonic() < deadline
            try:
                value = LedgerAdapter(state).call("research_status", {"problem_id": ref.problem_id})
                accepted.append(value["objects"])
                assert value["objects"] % 2 == 0, "Torn Episode/proposal pair escaped"
            except ResearchError as exc:
                assert "checkpoint" in str(exc).lower() or "publication" in str(exc).lower()
            time.sleep(0.01)
        for job in jobs:
            stdout, stderr = job.communicate(timeout=5)
            if job.returncode != 0:
                pytest.fail(stderr.decode("utf-8", errors="replace"))
    finally:
        for job in jobs:
            if job.poll() is None:
                job.kill()
            job.communicate(timeout=5)
    assert len(list_episodes(state)) == len(list_candidates(state, ref.problem_id)) == 6
    assert LedgerAdapter(state).call("research_status", {})["objects"] == 14


def test_invalid_retry_budget_is_rejected(research):
    with pytest.raises(ValueError, match="positive"):
        checkpoint.consistent_checkpoint_read(research[0], lambda: None, attempts=0)
