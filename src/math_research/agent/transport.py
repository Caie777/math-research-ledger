"""Bounded Codex CLI transport, shared by research and semantic model execution.

This module never reads or writes Problem Record mathematical state.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from math_research.core.atomicio import atomic_write_text
from math_research.core.errors import ResearchError
from math_research.core.process import hidden_process_kwargs, run_process, spawn_process
from math_research.ledger.records.write_boundary import automated_research

_MAX_LOG_CHARS = 200_000
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_REASONING_EFFORTS = frozenset({"low", "medium", "high", "xhigh", "max"})


class ResearchExecutionError(ResearchError):
    def __init__(self, code: str, message: str, *, stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.stdout = stdout
        self.stderr = stderr


class ResearchBudget(BaseModel):
    timeout_seconds: int = Field(default=180, ge=5, le=3600)
    max_calls: int = Field(default=1, ge=1, le=2)
    max_context_chars: int = Field(default=30_000, ge=1000, le=200_000)
    max_output_chars: int = Field(default=100_000, ge=1000, le=1_000_000)


def _codex_env() -> dict[str, str]:
    # A fresh allowlist avoids passing API keys and unrelated service credentials
    # into an agent process. CODEX_HOME is a location, not a copied login token.
    allowed = (
        "PATH",
        "ELAN_HOME",
        "HOME",
        "CODEX_HOME",
        "MATH_RESEARCH_PROCESS_LOG",
        "USER",
        "LOGNAME",
        "LANG",
        "LC_ALL",
        "XDG_RUNTIME_DIR",
        "SSL_CERT_FILE",
        "USERPROFILE",
        "HOMEDRIVE",
        "HOMEPATH",
        "SYSTEMROOT",
        "WINDIR",
        "TEMP",
        "TMP",
        "LOCALAPPDATA",
        "APPDATA",
    )
    child = {key: os.environ[key] for key in allowed if key in os.environ}
    from math_research.ledger.records.write_boundary import execution_env

    child = execution_env(child)
    # An explicit location also works under restricted Windows tokens for which
    # the CLI cannot resolve Known Folders. Do not read/copy authentication here.
    child.setdefault("CODEX_HOME", str(Path.home() / ".codex"))
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        value = os.environ.get(key)
        if value:
            try:
                parsed = urlsplit(value)
            except ValueError:
                continue
            if parsed.username is None and parsed.password is None:
                child[key] = value
    for key in ("NO_PROXY", "no_proxy"):
        if key in os.environ:
            child[key] = os.environ[key]
    return child


def _classify_failure(message: str) -> str:
    text = message.lower()
    if any(
        term in text
        for term in (
            "unknown model",
            "model not found",
            "model is not supported",
            "unsupported model",
            "invalid model",
        )
    ):
        return "unsupported_model"
    if any(
        term in text
        for term in (
            "unsupported reasoning effort",
            "unsupported reasoning level",
            "invalid reasoning effort",
            "reasoning effort is not supported",
        )
    ):
        return "unsupported_reasoning_effort"
    if "read-only file system" in text or "permission denied" in text:
        return "environment_error"
    if any(
        term in text
        for term in ("usage limit", "quota exceeded", "rate limit", "credits exhausted")
    ):
        return "quota_limit"
    if any(term in text for term in ("not logged in", "authentication required", "unauthorized")):
        return "not_logged_in"
    if any(term in text for term in ("connection", "network", "dns", "timed out", "tls")):
        return "network_error"
    return "cli_error"


def _validate_codex_options(model: str | None, reasoning_effort: str | None) -> None:
    if model is not None and not _MODEL_NAME.fullmatch(model):
        raise ResearchError(
            "Invalid Codex model ID; use a nonempty model identifier without spaces or flags."
        )
    if reasoning_effort is not None and reasoning_effort not in _REASONING_EFFORTS:
        raise ResearchError(
            "Unsupported Codex reasoning effort; choose low, medium, high, xhigh, or max."
        )


def _reported_settings(events: str) -> tuple[str | None, str | None, dict[str, int] | None]:
    model = None
    effort = None
    usage = None
    for line in events.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        # JSONL event formats vary by CLI version. Only treat explicit fields as
        # observed settings; do not infer defaults from an account or model name.
        if event.get("type") in {"thread.started", "turn.started", "turn.completed"}:
            if isinstance(event.get("model"), str):
                model = event["model"]
            if isinstance(event.get("model_reasoning_effort"), str):
                effort = event["model_reasoning_effort"]
            if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
                usage = {
                    key: value
                    for key, value in event["usage"].items()
                    if isinstance(value, int) and not isinstance(value, bool)
                }
    return model, effort, usage


def _terminate(proc: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if sys.platform == "win32":
        # Windows has no killpg; terminate the owned process tree, including any
        # child the CLI started. Fall back if taskkill is unavailable.
        try:
            run_process(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=5,
                check=False,
                **hidden_process_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            proc.kill()
        proc.wait()


def _global_instructions_present() -> bool:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    return any(
        (codex_home / name).is_file() and (codex_home / name).stat().st_size > 0
        for name in ("AGENTS.override.md", "AGENTS.md")
    )


class CodexCLIExecutor:
    """Official non-interactive CLI, ChatGPT auth only, with no repository mount."""

    def __init__(self, binary: str | list[str] | None = None) -> None:
        resolved = binary or shutil.which("codex")
        self.command = resolved if isinstance(resolved, list) else [resolved] if resolved else []
        self.binary = self.command[0] if self.command else None

    def preflight(self, *, deadline: float | None = None) -> str:
        if not self.binary:
            raise ResearchExecutionError("cli_missing", "Codex CLI not found on PATH.")
        env = _codex_env()
        try:
            version = run_process(
                [*self.command, "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=min(10, max(0.1, deadline - time.monotonic())) if deadline else 10,
                env=env,
                **hidden_process_kwargs(),
            )
            login = run_process(
                [*self.command, "login", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=min(10, max(0.1, deadline - time.monotonic())) if deadline else 10,
                env=env,
                **hidden_process_kwargs(),
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ResearchExecutionError("cli_missing", f"Cannot inspect Codex CLI: {exc}") from exc
        if version.returncode != 0:
            raise ResearchExecutionError("cli_missing", "Codex CLI version check failed.")
        if login.returncode != 0:
            raise ResearchExecutionError(
                "not_logged_in", "Codex CLI is not logged in. Run `codex login` interactively."
            )
        # Some CLI builds print login status to stderr (often after a benign
        # PATH-alias warning), so inspect both streams without persisting them.
        if "logged in using chatgpt" not in (login.stdout + login.stderr).lower():
            raise ResearchExecutionError(
                "not_logged_in",
                "Codex CLI is not using ChatGPT login. Run `codex login` with your "
                "ChatGPT account; "
                "API-key login is not used by this backend.",
            )
        if _global_instructions_present():
            raise ResearchExecutionError(
                "global_instructions",
                "Nonempty global Codex AGENTS.md is active. Review/disable it before isolated "
                "research; --ignore-user-config does not remove global instructions.",
            )
        return version.stdout.strip()

    @automated_research
    def execute(
        self,
        prompt: str,
        budget: ResearchBudget,
        *,
        model: str | None = None,
        reasoning_effort: str | None = None,
        cancel: Event | None = None,
        output_schema: dict[str, object] | None = None,
    ) -> tuple[str, str, dict[str, int] | None, str, str, float, str | None, str | None]:
        _validate_codex_options(model, reasoning_effort)
        version = self.preflight()
        assert self.binary is not None
        if model is not None or reasoning_effort is not None:
            try:
                help_result = run_process(
                    [*self.command, "exec", "--help"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    env=_codex_env(),
                    **hidden_process_kwargs(),
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise ResearchExecutionError(
                    "cli_error", f"Cannot inspect Codex exec options: {exc}"
                ) from exc
            help_text = help_result.stdout + help_result.stderr
            if help_result.returncode != 0 or (model is not None and "--model" not in help_text):
                raise ResearchExecutionError(
                    "unsupported_model", "This Codex CLI does not support --model."
                )
            if reasoning_effort is not None and "--config" not in help_text:
                raise ResearchExecutionError(
                    "unsupported_reasoning_effort",
                    "This Codex CLI does not support -c/--config for model_reasoning_effort.",
                )
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="mch-codex-") as temporary:
            workdir = Path(temporary)
            schema = workdir / "schema.json"
            final = workdir / "last-message.json"
            stdout_path = workdir / "events.jsonl"
            stderr_path = workdir / "stderr.log"
            prompt_path = workdir / "prompt.txt"
            if output_schema is None:
                raise ResearchExecutionError(
                    "invalid_output", "An explicit output schema is required."
                )
            atomic_write_text(schema, json.dumps(output_schema))
            atomic_write_text(prompt_path, prompt)
            command = [
                *self.command,
                "exec",
                "--ignore-user-config",
                "--ephemeral",
                "--sandbox",
                "read-only",
                "--skip-git-repo-check",
                "-C",
                str(workdir),
                "--output-schema",
                str(schema),
                "--output-last-message",
                str(final),
                "--json",
            ]
            if model:
                command.extend(["--model", model])
            if reasoning_effort:
                command.extend(["--config", f'model_reasoning_effort="{reasoning_effort}"'])
            command.append("-")
            with (
                prompt_path.open("rb") as stdin,
                stdout_path.open("wb") as stdout,
                stderr_path.open("wb") as stderr,
            ):
                proc = spawn_process(
                    command,
                    cwd=workdir,
                    env=_codex_env(),
                    stdin=stdin,
                    stdout=stdout,
                    stderr=stderr,
                    start_new_session=os.name != "nt",
                    **hidden_process_kwargs(),
                )
                stopped: tuple[str, str] | None = None
                try:
                    while proc.poll() is None:
                        if cancel is not None and cancel.is_set():
                            _terminate(proc)
                            stopped = ("cancelled", "Research task cancelled.")
                            break
                        if time.monotonic() - started >= budget.timeout_seconds:
                            _terminate(proc)
                            stopped = ("timeout", "Codex research task timed out.")
                            break
                        time.sleep(0.1)
                except KeyboardInterrupt:
                    _terminate(proc)
                    stopped = ("cancelled", "Research task interrupted.")
            stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace")[:_MAX_LOG_CHARS]
            stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")[:_MAX_LOG_CHARS]
            if stopped is not None:
                raise ResearchExecutionError(
                    stopped[0], stopped[1], stdout=stdout_text, stderr=stderr_text
                )
            if proc.returncode != 0:
                code = _classify_failure(stderr_text + "\n" + stdout_text)
                if code == "unsupported_model":
                    message = f"Codex CLI does not support model {model!r} for this login."
                elif code == "unsupported_reasoning_effort":
                    message = (
                        f"Codex CLI does not support reasoning effort {reasoning_effort!r} "
                        "for this model."
                    )
                else:
                    message = f"Codex CLI exited with code {proc.returncode} ({code})."
                raise ResearchExecutionError(
                    code,
                    message,
                    stdout=stdout_text,
                    stderr=stderr_text,
                )
            if not final.is_file():
                raise ResearchExecutionError(
                    "invalid_output",
                    "Codex did not write a final structured message.",
                    stdout=stdout_text,
                    stderr=stderr_text,
                )
            result = final.read_text(encoding="utf-8")
            reported_model, reported_effort, usage = _reported_settings(stdout_text)
            return (
                result,
                version,
                usage,
                stdout_text,
                stderr_text,
                time.monotonic() - started,
                reported_model,
                reported_effort,
            )
