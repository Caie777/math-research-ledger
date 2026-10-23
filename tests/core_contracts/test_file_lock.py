"""Bounded synthetic failure injection and real multiprocess locking, no ACL edits."""

import errno
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from math_research.core import atomicio
from math_research.core.errors import ResearchError
from math_research.mcp.adapter import LedgerAdapter


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        assert seconds > 0
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(
        atomicio, "time", SimpleNamespace(monotonic=lambda: now[0], time=time.time, sleep=sleep)
    )
    return now, sleeps


def deny(winerror=None):
    exc = PermissionError(errno.EACCES, "synthetic access denial")
    if winerror is not None:
        exc.winerror = winerror
    return exc


def test_create_release_and_exception_cleanup(tmp_path):
    target = tmp_path / "data"
    lock = target.with_suffix(".lock")
    with atomicio.file_lock(target):
        assert lock.read_text().strip() == str(os.getpid())
    assert not lock.exists()
    with pytest.raises(ValueError, match="body failed"), atomicio.file_lock(target):
        raise ValueError("body failed")
    assert not lock.exists()


def test_real_competition_times_out_without_entering(tmp_path, clock):
    now, sleeps = clock
    target = tmp_path / "data"
    with atomicio.file_lock(target):
        with (
            pytest.raises(ResearchError, match="Timed out"),
            atomicio.file_lock(target, timeout=0.05),
        ):
            pytest.fail("Must not enter another holder's critical section")
        assert now[0] == pytest.approx(0.05)
        assert sleeps and max(sleeps) <= atomicio._LOCK_POLL_SECONDS


@pytest.mark.parametrize(
    "windows,winerror,attempts",
    [
        (False, None, 1),
        (True, None, 4),
        (True, 5, 4),
        (True, 32, 4),
        (True, 303, 4),
        (True, 999, 1),
    ],
)
def test_access_denial_with_no_lock_is_not_assumed_held(
    tmp_path, monkeypatch, clock, windows, winerror, attempts
):
    target = tmp_path / "data"
    calls = []

    def fail(*args):
        calls.append(args)
        assert len(calls) <= 4, "Unbounded retry regression"
        raise deny(winerror)

    monkeypatch.setattr(atomicio, "_WINDOWS", windows)
    monkeypatch.setattr(atomicio.os, "open", fail)
    with pytest.raises(ResearchError, match="Cannot create .*access denied"):
        with atomicio.file_lock(target):
            pytest.fail("A permissions error cannot grant the lock")
    assert len(calls) == attempts
    assert len(clock[1]) == attempts - 1
    assert not target.with_suffix(".lock").exists()


def test_windows_transient_access_denial_recovers(tmp_path, monkeypatch, clock):
    original = atomicio.os.open
    calls = []

    def transient(*args):
        calls.append(args)
        if len(calls) == 1:
            raise deny(5)
        return original(*args)

    monkeypatch.setattr(atomicio, "_WINDOWS", True)
    monkeypatch.setattr(atomicio.os, "open", transient)
    with atomicio.file_lock(tmp_path / "data"):
        assert len(calls) == 2
    assert len(clock[1]) == 1


def test_windows_crt_eacces_without_winerror_has_bounded_transient_retry(
    tmp_path, monkeypatch, clock
):
    """Windows CRT os.open may omit winerror during delete-pending races."""
    original = atomicio.os.open
    calls = []

    def transient(*args):
        calls.append(args)
        if len(calls) == 1:
            raise deny()  # EACCES with no native winerror, as observed in multiprocess CI.
        return original(*args)

    monkeypatch.setattr(atomicio, "_WINDOWS", True)
    monkeypatch.setattr(atomicio.os, "open", transient)
    with atomicio.file_lock(tmp_path / "data"):
        assert len(calls) == 2
    assert len(clock[1]) == 1


@pytest.mark.parametrize(
    "error", [PermissionError("synthetic stat denied"), OSError(errno.EIO, "synthetic stat IO")]
)
def test_unreadable_existing_lock_fails_immediately(tmp_path, monkeypatch, clock, error):
    target = tmp_path / "data"
    lock = target.with_suffix(".lock")
    lock.write_text("synthetic holder")
    original = Path.stat

    def stat(path, *args, **kwargs):
        if path == lock:
            raise error
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", stat)
    with pytest.raises(ResearchError, match="Cannot inspect existing"):
        with atomicio.file_lock(target):
            pytest.fail("Unreadable lock must not be taken")
    assert not clock[1]


def test_repeated_disappearance_is_bounded_and_sleeps(tmp_path, monkeypatch, clock):
    target = tmp_path / "data"
    lock = target.with_suffix(".lock")
    original = Path.stat

    def occupied(*args):
        raise FileExistsError(errno.EEXIST, "synthetic open/stat race")

    def stat(path, *args, **kwargs):
        if path == lock:
            raise FileNotFoundError("released during stat")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(atomicio.os, "open", occupied)
    monkeypatch.setattr(Path, "stat", stat)
    with pytest.raises(ResearchError, match="Timed out"):
        with atomicio.file_lock(target, timeout=0.05):
            pytest.fail("No successful exclusive create")
    assert clock[0][0] == pytest.approx(0.05)
    assert len(clock[1]) == 3


@pytest.mark.parametrize("operation", ["stale", "owned"])
def test_cleanup_denial_is_not_silently_ignored(tmp_path, monkeypatch, operation):
    target = tmp_path / "data"
    lock = target.with_suffix(".lock")
    if operation == "stale":
        lock.write_text("synthetic dead holder")
        os.utime(lock, (1, 1))
    original = Path.unlink

    def unlink(path, *args, **kwargs):
        if path == lock:
            raise deny()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    with pytest.raises(ResearchError, match=f"Cannot remove {operation}"):
        with atomicio.file_lock(target):
            pass


def test_stale_reclaim_and_metadata_write_failure(tmp_path, monkeypatch):
    target = tmp_path / "data"
    lock = target.with_suffix(".lock")
    lock.write_text("synthetic dead holder")
    os.utime(lock, (1, 1))
    with atomicio.file_lock(target):
        assert lock.read_text().strip() == str(os.getpid())
    monkeypatch.setattr(atomicio.os, "write", lambda *a: (_ for _ in ()).throw(deny()))
    with pytest.raises(ResearchError, match="Cannot initialize"):
        with atomicio.file_lock(target):
            pytest.fail("Failed initialization")
    assert not lock.exists()


@pytest.mark.parametrize("timeout", [-1, float("inf"), float("nan")])
def test_timeout_must_be_finite(tmp_path, timeout):
    with pytest.raises(ValueError, match="finite"):
        with atomicio.file_lock(tmp_path / "data", timeout=timeout):
            pass


def test_windows_access_retries_respect_shorter_deadline(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(atomicio, "_WINDOWS", True)
    monkeypatch.setattr(atomicio.os, "open", lambda *a: (_ for _ in ()).throw(deny(5)))
    with pytest.raises(ResearchError, match="Timed out"):
        with atomicio.file_lock(tmp_path / "data", timeout=0.005):
            pass
    assert clock[1] == [0.005]


@pytest.mark.parametrize("operation", ["directory", "open"])
def test_other_acquisition_errors_are_diagnostic(tmp_path, monkeypatch, operation):
    if operation == "directory":
        monkeypatch.setattr(Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(deny()))
    else:
        monkeypatch.setattr(
            atomicio.os,
            "open",
            lambda *a: (_ for _ in ()).throw(OSError(errno.EIO, "synthetic IO")),
        )
    with pytest.raises(ResearchError, match="Cannot .*lock"):
        with atomicio.file_lock(tmp_path / "data"):
            pass


def test_failed_atomic_replace_preserves_previous_bytes(tmp_path, monkeypatch):
    path = tmp_path / "data"
    path.write_bytes(b"original")
    monkeypatch.setattr(atomicio.os, "replace", lambda *a: (_ for _ in ()).throw(deny()))
    with pytest.raises(PermissionError), atomicio.file_lock(path):
        atomicio.atomic_write_text(path, "replacement")
    assert path.read_bytes() == b"original"
    assert not path.with_suffix(".lock").exists()
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_atomic_replace_retries_transient_windows_read_handles(
    tmp_path, monkeypatch, clock, winerror
):
    path = tmp_path / "atomic.json"
    path.write_bytes(b"original")
    original = atomicio.os.replace
    attempts = []

    def replace(source, target):
        attempts.append(1)
        assert path.read_bytes() == b"original"
        if len(attempts) < 3:
            raise deny(winerror)
        original(source, target)

    monkeypatch.setattr(atomicio, "_WINDOWS", True)
    monkeypatch.setattr(atomicio.os, "replace", replace)
    atomicio.atomic_write_text(path, "replacement")
    assert path.read_bytes() == b"replacement"
    assert attempts == [1, 1, 1] and clock[1] == [0.02, 0.02]


def test_atomic_replace_persistent_windows_denial_is_bounded(tmp_path, monkeypatch, clock):
    path = tmp_path / "atomic.json"
    path.write_bytes(b"original")
    attempts = []

    def replace(*args):
        attempts.append(1)
        raise deny(5)

    monkeypatch.setattr(atomicio, "_WINDOWS", True)
    monkeypatch.setattr(atomicio.os, "replace", replace)
    with pytest.raises(PermissionError):
        atomicio.atomic_write_text(path, "replacement")
    assert path.read_bytes() == b"original"
    assert len(attempts) == 4 and clock[1] == [0.02, 0.02, 0.02]
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("windows,winerror", [(False, 5), (True, 87)])
def test_atomic_replace_does_not_retry_unrelated_errors(
    tmp_path, monkeypatch, clock, windows, winerror
):
    path = tmp_path / "atomic.json"
    path.write_bytes(b"original")
    monkeypatch.setattr(atomicio, "_WINDOWS", windows)
    monkeypatch.setattr(atomicio.os, "replace", lambda *args: (_ for _ in ()).throw(deny(winerror)))
    with pytest.raises(PermissionError):
        atomicio.atomic_write_text(path, "replacement")
    assert not clock[1] and path.read_bytes() == b"original"


@pytest.mark.skipif(os.name != "nt", reason="POSIX permits rename while a reader is open")
def test_real_windows_read_handle_can_close_before_atomic_replace_retry(tmp_path, monkeypatch):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "atomic.json"
    path.write_bytes(b"original")
    attempted = threading.Event()
    original = atomicio.os.replace

    def replace(*args):
        try:
            return original(*args)
        finally:
            attempted.set()

    monkeypatch.setattr(atomicio.os, "replace", replace)
    reader = path.open("rb")
    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(atomicio.atomic_write_text, path, "replacement")
        try:
            assert attempted.wait(5)
        finally:
            reader.close()
        writer.result(timeout=5)
    assert path.read_bytes() == b"replacement"


def test_status_needs_no_lock_write_permission_and_does_not_mutate(research, monkeypatch, clock):
    state, _ = research
    assert LedgerAdapter(state).call("research_status", {})["problems"] == 1
    before = {p.relative_to(state): p.read_bytes() for p in state.rglob("*") if p.is_file()}
    original = atomicio.os.open

    attempted = []

    def fail(path, *args):
        if Path(path).name == ".checkpoint.lock":
            attempted.append(path)
            raise deny(5)
        return original(path, *args)

    monkeypatch.setattr(atomicio, "_WINDOWS", True)
    monkeypatch.setattr(atomicio.os, "open", fail)
    assert LedgerAdapter(state).call("research_status", {})["problems"] == 1
    assert not attempted and clock[0][0] == 0 and not clock[1]
    assert before == {p.relative_to(state): p.read_bytes() for p in state.rglob("*") if p.is_file()}


def test_multiprocess_increment_and_atomic_replace(tmp_path):
    path = tmp_path / "counter.json"
    atomicio.atomic_write_text(path, '{"count": 0}')
    worker = """
import json,sys
from pathlib import Path
from math_research.core.atomicio import file_lock,atomic_write_text
p=Path(sys.argv[1])
for _ in range(15):
    with file_lock(p):
        value=json.loads(p.read_text())
        atomic_write_text(p,json.dumps({'count':value['count']+1}))
"""
    jobs = [subprocess.Popen([sys.executable, "-B", "-c", worker, str(path)]) for _ in range(4)]
    try:
        deadline = time.monotonic() + 30
        while any(job.poll() is None for job in jobs):
            assert time.monotonic() < deadline
            # Windows readers must close the file before another process replaces
            # it. This counter tests the unchanged explicit lock contract;
            # optimistic MCP reads separately fence publication generations.
            with atomicio.file_lock(path):
                assert 0 <= json.loads(path.read_text())["count"] <= 60
            time.sleep(0.001)
        for job in jobs:
            assert job.wait(timeout=30) == 0
    finally:
        for job in jobs:
            if job.poll() is None:
                job.kill()
            job.wait(timeout=5)
    assert json.loads(path.read_text())["count"] == 60
    assert not path.with_suffix(".json.lock").exists()
    assert not list(tmp_path.glob("*.tmp"))
