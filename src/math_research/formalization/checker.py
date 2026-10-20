"""Fixed Lean/Lake checks for trusted local repositories, never bundle-supplied commands."""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, BinaryIO

from math_research.core.process import spawn_process

from .freeze import repo_root, verify_frozen
from .models import FormalCheckResult, FrozenManifest

STANDARD_AXIOMS = frozenset({"propext", "Classical.choice", "Quot.sound"})
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_']*(?:\.[A-Za-z_][A-Za-z0-9_']*)*\Z")


def validate_name(name: str) -> str:
    if not _NAME.fullmatch(name):
        raise ValueError("Expected a simple dotted Lean declaration/module name")
    return name


def code_only(source: str) -> str:
    """Erase nested comments, strings/raw strings, and character literals before token scan."""
    result: list[str] = []
    i = 0
    while i < len(source):
        if source.startswith("--", i):
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
            result.append(" ")
        elif source.startswith("/-", i):
            depth = 1
            i += 2
            while i < len(source) and depth:
                if source.startswith("/-", i):
                    depth += 1
                    i += 2
                elif source.startswith("-/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            result.append(" ")
        elif raw := re.match(r'r(#+)?"', source[i:]) if source[i] == "r" else None:
            terminator = '"' + (raw.group(1) or "")
            end = source.find(terminator, i + raw.end())
            i = len(source) if end < 0 else end + len(terminator)
            result.append(" ")
        elif source[i] == '"':
            i += 1
            while i < len(source):
                if source[i] == "\\":
                    i += 2
                elif source[i] == '"':
                    i += 1
                    break
                else:
                    i += 1
            result.append(" ")
        elif source[i] == "'" and (char := re.match(r"'(?:\\.|[^'\\\n])'", source[i:])):
            i += char.end()
            result.append(" ")
        else:
            result.append(source[i])
            i += 1
    return "".join(result)


def scan_sources(root: Path) -> tuple[tuple[str, ...], bool]:
    violations: list[str] = []
    native = False
    for directory, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in {".git", ".lake"}]
        for name in sorted(files):
            if not name.endswith(".lean"):
                continue
            path = Path(directory) / name
            if not path.resolve().is_relative_to(root):
                raise ValueError("Lean source symlink escapes repository")
            tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_']*", code_only(path.read_text("utf-8"))))
            native |= "native_decide" in tokens
            for forbidden in sorted(tokens & {"sorry", "admit", "axiom"}):
                violations.append(f"{path.relative_to(root).as_posix()}: {forbidden}")
    return tuple(sorted(violations)), native


def parse_probe(output: str, declaration: str) -> tuple[bool, bool, tuple[str, ...]]:
    """Require the exact checked name and a complete, unambiguous axiom report."""
    name = re.escape(validate_name(declaration))
    exists = re.search(rf"(?m)^{name}(?:\s|:)", output) is not None
    reports = re.findall(rf"'{name}' depends on axioms:\s*\[([^\]]*)\]", output)
    empty = re.findall(rf"'{name}' does not depend on any axioms", output)
    if len(reports) + len(empty) != 1:
        return exists, False, ()
    if empty:
        return exists, True, ()
    axioms = tuple(part.strip() for part in reports[0].split(",") if part.strip())
    if not all(_NAME.fullmatch(axiom) for axiom in axioms):
        return exists, False, ()
    return exists, True, axioms


@dataclass(frozen=True)
class CommandResult:
    exit_code: int | None
    output: str
    timed_out: bool = False
    truncated: bool = False


class LeanChecker:
    def __init__(
        self,
        lake_executable: Path | None = None,
        *,
        elan_home: Path = Path("D:/Tools/elan"),
        timeout: float = 600,
        capture_limit: int = 65536,
    ) -> None:
        executable = lake_executable or Path(shutil.which("lake") or "lake")
        self.lake = executable.resolve(strict=True)
        if self.lake.name.lower() not in {"lake", "lake.exe"} or not self.lake.is_file():
            raise ValueError("Expected the configured Lake executable")
        if not 0 < timeout <= 3600 or not 1024 <= capture_limit <= 1048576:
            raise ValueError("Invalid checker timeout/capture limit")
        self.elan_home = elan_home.resolve()
        self.timeout = timeout
        self.capture_limit = capture_limit

    def _run(
        self,
        arguments: list[str],
        root: Path,
        env: dict[str, str],
        log: BinaryIO,
        input_text: str | None = None,
    ) -> CommandResult:
        # Fixed argument arrays only. Output goes directly to disk, never to an unbounded pipe.
        log.write(("\n$ " + " ".join(arguments) + "\n").encode("utf-8"))
        if input_text:
            log.write(input_text.encode("utf-8"))
        log.flush()
        offset = log.tell()
        timed_out = False
        platform_options: dict[str, Any] = {"start_new_session": True} if os.name != "nt" else {}
        with spawn_process(
            arguments,
            cwd=root,
            env=env,
            stdin=subprocess.PIPE if input_text else subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            shell=False,
            **platform_options,
        ) as process:
            try:
                process.communicate(
                    input_text.encode("utf-8") if input_text else None, timeout=self.timeout
                )
            except subprocess.TimeoutExpired:
                timed_out = True
                if sys.platform == "win32":
                    # Lifecycle cleanup only; this command cannot come from a bundle.
                    taskkill = (
                        Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/taskkill.exe"
                    )
                    with spawn_process(
                        [str(taskkill), "/PID", str(process.pid), "/T", "/F"],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=env,
                        shell=False,
                    ) as cleanup:
                        try:
                            cleanup.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            cleanup.kill()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.kill()
                process.wait()
            code = process.returncode
        log.flush()
        end = log.seek(0, os.SEEK_END)
        size = end - offset
        log.seek(max(offset, end - self.capture_limit))
        output = log.read(self.capture_limit).decode("utf-8", errors="replace")
        log.seek(0, os.SEEK_END)
        log.write(f"\nexit_code={code} timed_out={timed_out}\n".encode())
        log.flush()
        return CommandResult(code, output, timed_out, size > self.capture_limit)

    def check(
        self,
        repo: Path,
        module: str,
        declaration: str,
        frozen: FrozenManifest,
        log_path: Path,
        *,
        expected_type: str | None = None,
    ) -> FormalCheckResult:
        root = repo_root(repo)
        validate_name(module)
        validate_name(declaration)
        if expected_type is not None and (
            len(expected_type) > 2000
            or not re.fullmatch(r"[A-Za-z0-9_'.() :∀→ℕℤℚℝ,+-]+", expected_type)
        ):
            raise ValueError("Expected a restricted type ascription, not Lean commands")
        log_path = log_path.resolve()
        # Logs cannot overwrite a source, lock file, or a file inside the checked repository.
        if log_path.is_relative_to(root):
            raise ValueError("Check log must be outside the Lean repository")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {"checked_at": datetime.now(UTC).isoformat(), "log": str(log_path)}
        reasons: list[str] = []
        env = dict(os.environ)
        env["ELAN_HOME"] = str(self.elan_home)
        env["ELAN_TOOLCHAIN"] = frozen.lean_toolchain
        env["PATH"] = str(self.lake.parent) + os.pathsep + env.get("PATH", "")
        # Cache is not downloaded during verification; keep any incidental tool cache on D.
        env["MATHLIB_CACHE_DIR"] = str(self.elan_home / "mathlib-cache")
        with log_path.open("x+b") as log:
            try:
                drift = verify_frozen(root, frozen)
                if drift:
                    reasons.append("FROZEN_SOURCE_DRIFT")
                    log.write(("FROZEN_SOURCE_DRIFT: " + ", ".join(drift) + "\n").encode())
                else:
                    violations, native = scan_sources(root)
                    data.update(source_violations=violations, native_decide=native)
                    build = self._run([str(self.lake), "build"], root, env, log)
                    data.update(build_exit_code=build.exit_code, timed_out=build.timed_out)
                    data["output_tail"] = build.output
                    if build.timed_out:
                        reasons.append("TIMEOUT")
                    elif build.exit_code != 0:
                        reasons.append("BUILD_FAILED")
                    else:
                        probe_text = (
                            f"import {module}\n#check {declaration}\n#print axioms {declaration}\n"
                        )
                        if expected_type is not None:
                            probe_text += f"#check ({declaration} : {expected_type})\n"
                        probe = self._run(
                            [str(self.lake), "env", "lean", "--stdin"], root, env, log, probe_text
                        )
                        exists, parsed, axioms = parse_probe(probe.output, declaration)
                        data.update(
                            target_exit_code=probe.exit_code,
                            target_exists=exists,
                            axioms_parsed=parsed and not probe.truncated,
                            axioms=axioms,
                            sorry_ax="sorryAx" in axioms,
                            custom_axioms=tuple(a for a in axioms if a not in STANDARD_AXIOMS),
                            timed_out=probe.timed_out,
                            output_tail=probe.output,
                        )
                        if probe.timed_out:
                            reasons.append("TIMEOUT")
                        if probe.exit_code != 0:
                            reasons.append("TARGET_CHECK_FAILED")
                        if not exists:
                            reasons.append("MISSING_DECLARATION")
                        if not parsed or probe.truncated:
                            reasons.append("AXIOM_REPORT_UNREADABLE")
                    # Detect changes during the subprocess calls as well as before them.
                    drift = verify_frozen(root, frozen)
                    data["hashes_match"] = not drift
                    if drift:
                        reasons.append("FROZEN_SOURCE_DRIFT")
                    after_violations, after_native = scan_sources(root)
                    data["source_violations"] = tuple(sorted(set(violations + after_violations)))
                    data["native_decide"] = native or after_native
            except (OSError, ValueError, KeyError, StopIteration) as exc:
                reasons.append("CHECKER_ERROR")
                log.write(f"CHECKER_ERROR: {type(exc).__name__}: {exc}\n".encode())
            data["reasons"] = tuple(reasons)
            result = FormalCheckResult(**data)
            log.write(("\nRESULT\n" + result.model_dump_json(indent=2) + "\n").encode("utf-8"))
            return result
