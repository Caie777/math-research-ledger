"""Atomic file writes for the artifact store.

A crash, full disk, or Ctrl-C during a plain ``write_text`` (or a truncate-then-
write ``rewrite``) can leave a half-written, corrupt file — and the JSONL reader
silently drops the corrupted tail, discarding records with no error. Routing the
store's whole-file writes through :func:`atomic_write_text` makes them durable:
write to a temp file in the same directory, fsync, then ``os.replace`` — an atomic
rename that either fully succeeds or leaves the prior file intact.

Atomicity of a single write is not enough for a *mutable* ledger, though. Those are
updated read-modify-write — read every record, add or change one, replace the file
— and two processes doing that concurrently both succeed while one of them silently
loses its record, because the second rename overwrites the first writer's file.
Worse, each derives the next artifact id from what it just read, so both mint the
same id. Measured: four processes appending fifteen claims each to one workspace
reported sixty successes and left sixteen records behind, with ids handed out four
times over. :func:`file_lock` closes that window — hold it across the read *and*
the write, not just the write.
"""

from __future__ import annotations

import errno
import math
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from math_research.core.errors import ResearchError

_LOCK_POLL_SECONDS = 0.02
_LOCK_TIMEOUT_SECONDS = 15.0
# A holder that died leaves its lock file behind. Reclaim one that is older than any
# plausible read-modify-write rather than blocking every later run forever.
_LOCK_STALE_SECONDS = 120.0
_WINDOWS = os.name == "nt"
# Windows delete-pending/sharing errors can briefly masquerade as access denial.
# Never turn a persistent ACL denial into an ordinary, indefinitely held lock.
_WINDOWS_ACCESS_RETRIES = 3


@contextmanager
def file_lock(
    path: Path,
    *,
    timeout: float = _LOCK_TIMEOUT_SECONDS,
    stale_after: float = _LOCK_STALE_SECONDS,
) -> Iterator[None]:
    """Serialize a read-modify-write of ``path`` across processes.

    Uses an ``O_EXCL`` sibling lock file rather than ``fcntl``: the same code then
    works on Windows, and the lock is visible in a directory listing when something
    goes wrong. A lock file older than ``stale_after`` is assumed to belong to a
    process that died and is reclaimed, so a crash cannot wedge the workspace.

    Every retry checks the monotonic deadline and sleeps. Only EEXIST establishes
    contention; unreadable state and cleanup errors fail diagnostically. Known
    Windows sharing/delete-pending access errors receive a short bounded retry.
    A caller that cannot take the lock must never fall through and write anyway.
    """
    lock = path.with_name(path.name + ".lock")
    if not math.isfinite(timeout) or timeout < 0:
        raise ValueError("Lock timeout must be finite and nonnegative.")
    if not math.isfinite(stale_after) or stale_after < 0:
        raise ValueError("Lock stale_after must be finite and nonnegative.")

    def failure(operation: str, exc: OSError) -> ResearchError:
        return ResearchError(f"Cannot {operation} lock {lock}: {type(exc).__name__}: {exc}")

    def release() -> None:
        try:
            lock.unlink()
        except OSError as exc:
            raise failure("remove owned", exc) from exc

    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise failure("prepare directory for", exc) from exc
    deadline = time.monotonic() + timeout
    access_retries = 0
    last_error: OSError | None = None

    def timed_out() -> ResearchError:
        detail = f" Last error: {type(last_error).__name__}: {last_error}." if last_error else ""
        return ResearchError(
            f"Timed out after {timeout:g}s waiting for lock {lock}.{detail} "
            "Inspect the lock holder and workspace access; no write was performed."
        )

    first_attempt = True
    while True:
        if not first_attempt and time.monotonic() >= deadline:
            raise timed_out() from last_error
        first_attempt = False
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError as exc:
            last_error = exc
            try:
                age = time.time() - lock.stat().st_mtime
            except FileNotFoundError:
                pass  # released during inspection; still use the bounded retry below
            except OSError as exc:
                raise failure("inspect existing", exc) from exc
            else:
                if age > stale_after:
                    try:
                        lock.unlink()
                    except FileNotFoundError:
                        pass  # another contender already reclaimed it
                    except OSError as exc:
                        raise failure("remove stale", exc) from exc
        except PermissionError as exc:
            last_error = exc
            # The Windows CRT can return EACCES without preserving winerror
            # for a delete-pending lock. This is a transient access retry,
            # never evidence that another holder exists or permission to write.
            transient_access = getattr(exc, "winerror", None) in {5, 32, 303} or (
                getattr(exc, "winerror", None) is None and exc.errno == errno.EACCES
            )
            if not _WINDOWS or not transient_access or access_retries >= _WINDOWS_ACCESS_RETRIES:
                raise failure("create (access denied)", exc) from exc
            access_retries += 1
        except OSError as exc:
            raise failure("create", exc) from exc
        else:
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise timed_out() from last_error
        time.sleep(min(_LOCK_POLL_SECONDS, remaining))

    try:
        try:
            os.write(fd, f"{os.getpid()}\n".encode())
        finally:
            os.close(fd)
    except OSError as exc:
        try:
            release()
        except ResearchError as cleanup:
            raise cleanup from exc
        raise failure("initialize", exc) from exc
    try:
        yield
    finally:
        release()


def atomic_write_text(path: Path, data: str, *, encoding: str = "utf-8") -> None:
    """Write ``data`` to ``path`` atomically (temp file + fsync + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        # Never leave the temp file behind on failure; the original is untouched.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
