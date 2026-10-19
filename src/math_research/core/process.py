"""Platform kwargs for non-interactive children; the caller owns their lifecycle."""

from __future__ import annotations

import atexit
import json
import os
import re
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, cast
from uuid import uuid4

_WINDOWS = os.name == "nt"
PROCESS_LOG_ENV = "MATH_RESEARCH_PROCESS_LOG"


class ProcessKwargs(TypedDict, total=False):
    creationflags: int


def hidden_process_kwargs(*, background: bool = True, creationflags: int = 0) -> ProcessKwargs:
    """Hide Windows consoles without detaching, redirecting streams or changing PID ownership.

    Existing lifecycle flags are retained. On other platforms no Windows kwargs
    are introduced. Direct foreground CLI entry points do not need this helper.
    """
    if not _WINDOWS:
        return {}
    flags = creationflags
    if background:
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    return {"creationflags": flags} if flags else {}


def _write_process_event(path: Path | None, metadata: dict) -> None:
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps({"timestamp": datetime.now(UTC).isoformat(), **metadata}) + "\n"
            )
    except (OSError, ValueError):
        pass  # Observability must never change process/timeout/recovery behavior.


def _executable(args: object, options: dict) -> str:
    explicit = options.get("executable")
    if explicit:
        return os.fsdecode(explicit)
    if options.get("shell"):
        return os.environ.get("COMSPEC", "shell")
    if isinstance(args, (list, tuple)) and args:
        return os.fsdecode(args[0])  # Deliberately never inspect the remaining arguments.
    if isinstance(args, os.PathLike):
        return os.fsdecode(args)
    if isinstance(args, (str, bytes)):
        match = re.match(r'^\s*(?:"([^"]+)"|(\S+))', os.fsdecode(args))
        return (match.group(1) or match.group(2)) if match else "unknown"
    return "unknown"


def spawn_process(
    args: Any,
    *,
    interactive: bool = False,
    diagnostics_path: Path | None = None,
    **options: Any,
) -> subprocess.Popen:
    """Create an owned child and observe lifecycle without reading args or output bodies."""
    flags = options.get("creationflags", 0)
    if _WINDOWS and not interactive:
        # Both flags negate CREATE_NO_WINDOW. Fail instead of silently claiming hidden.
        if flags & 0x18:  # DETACHED_PROCESS | CREATE_NEW_CONSOLE
            raise ValueError("Non-interactive child has conflicting console creation flags.")
        options.update(hidden_process_kwargs(creationflags=flags))
    log = diagnostics_path or (
        Path(os.environ[PROCESS_LOG_ENV]) if os.environ.get(PROCESS_LOG_ENV) else None
    )
    if log is not None:
        options["env"] = dict(os.environ if options.get("env") is None else options["env"])
        options["env"][PROCESS_LOG_ENV] = str(log.resolve())
        options["env"]["MATH_RESEARCH_PROCESS_CLASSIFICATION"] = (
            "interactive" if interactive else "non-interactive"
        )
    executable = _executable(args, options)
    startupinfo = options.get("startupinfo")
    frame = sys._getframe(1)
    if frame.f_globals.get("__name__") == __name__ and frame.f_code.co_name == "run_process":
        frame = frame.f_back or frame
    metadata = {
        "launch_id": uuid4().hex,
        "executable": executable,
        "process_name": Path(executable).name,
        "parent_pid": os.getpid(),
        "launcher_identity": frame.f_globals.get("__name__", "unknown")
        + "."
        + frame.f_code.co_name,
        "call_site_line": frame.f_lineno,
        "shell": bool(options.get("shell", False)),
        "creationflags": options.get("creationflags", 0) if _WINDOWS else None,
        "startupinfo": startupinfo is not None,
        "startupinfo_flags": getattr(startupinfo, "dwFlags", None),
        "classification": "interactive" if interactive else "non-interactive",
    }
    try:
        process = subprocess.Popen(args, **options)
    except Exception as exc:
        _write_process_event(
            log,
            {**metadata, "status": "start_failed", "pid": None, "error_class": type(exc).__name__},
        )
        raise
    _write_process_event(
        log, {**metadata, "status": "started", "pid": getattr(process, "pid", None)}
    )
    if log is not None and isinstance(getattr(process, "pid", None), int):

        def observe_exit() -> None:
            try:
                code = process.wait()
                _write_process_event(
                    log, {**metadata, "status": "exited", "pid": process.pid, "returncode": code}
                )
            except Exception:
                pass

        threading.Thread(target=observe_exit, name="process-metadata", daemon=True).start()
    return process


def run_process(
    args: Any,
    *,
    input: Any = None,
    capture_output: bool = False,
    timeout: float | None = None,
    check: bool = False,
    **options: Any,
) -> subprocess.CompletedProcess:
    """subprocess.run semantics, using the same observed non-interactive launcher."""
    if input is not None:
        if options.get("stdin") is not None:
            raise ValueError("stdin and input arguments may not both be used.")
        options["stdin"] = subprocess.PIPE
    if capture_output:
        if options.get("stdout") is not None or options.get("stderr") is not None:
            raise ValueError("stdout and stderr arguments may not be used with capture_output.")
        options["stdout"] = options["stderr"] = subprocess.PIPE
    with spawn_process(args, **options) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            if _WINDOWS:
                exc.stdout, exc.stderr = process.communicate()
            else:
                process.wait()
            raise
        except BaseException:
            process.kill()
            raise
        code = process.poll()
        if check and code:
            raise subprocess.CalledProcessError(code, process.args, output=stdout, stderr=stderr)
        return subprocess.CompletedProcess(process.args, cast(int, code), stdout, stderr)


def record_current_process() -> None:
    """Link Python venv launchers to their actual interpreter; no command-line access."""
    if not os.environ.get(PROCESS_LOG_ENV):
        return
    path = Path(os.environ[PROCESS_LOG_ENV])
    metadata: dict = {
        "pid": os.getpid(),
        "parent_pid": os.getppid(),
        "executable": sys.executable,
        "process_name": Path(sys.executable).name,
        "launcher_identity": "python.interpreter",
        "shell": None,
        "creationflags": None,
        "startupinfo": None,
        "classification": os.environ.get("MATH_RESEARCH_PROCESS_CLASSIFICATION", "non-interactive"),
        "flags_source": "external_launcher_not_observable",
    }
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.GetModuleFileNameW.argtypes = [wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD]
        buffer = ctypes.create_unicode_buffer(32768)
        if kernel.GetModuleFileNameW(None, buffer, len(buffer)):
            metadata["executable"] = buffer.value
        kernel.GetConsoleWindow.restype = wintypes.HWND
        handle = kernel.GetConsoleWindow()
        user = ctypes.WinDLL("user32", use_last_error=True)
        user.IsWindowVisible.argtypes = [wintypes.HWND]
        metadata.update(
            console_handle=int(handle or 0), console_visible=bool(user.IsWindowVisible(handle))
        )
    _write_process_event(path, {**metadata, "status": "interpreter_started"})
    atexit.register(_write_process_event, path, {**metadata, "status": "interpreter_exited"})


record_current_process()
