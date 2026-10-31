"""Required Core + standard MCP + real DSH gate; Codex-only checks are advisory.

Use an installed, persistent dev+[mcp] interpreter. No real profile is changed.
Only --real-workspace opts into status/search and byte/mtime inventory checks.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

from workspace_inventory import inventory, is_link

ROOT = Path(__file__).resolve().parents[1]


def configuration(args: argparse.Namespace) -> dict[str, str]:
    values = {
        "MRL_DSH_EXECUTABLE": args.dsh_executable,
        "MRL_DSH_NODE_MODULES": args.dsh_node_modules,
        "MRL_DSH_PYTHON": args.python,
    }
    if not all(values.values()):
        raise ValueError(
            "A real DSH executable, its node_modules and persistent Python are required."
        )
    for name in ("MRL_DSH_EXECUTABLE", "MRL_DSH_PYTHON"):
        if not Path(values[name]).is_absolute() or not Path(values[name]).is_file():
            raise ValueError(f"{name} must name an existing absolute executable.")
    # ASAR node_modules is a virtual path: only Electron can validate its contents.
    if not Path(values["MRL_DSH_NODE_MODULES"]).is_absolute():
        raise ValueError("DSH node_modules must be absolute (ASAR virtual paths are supported).")
    return {**values, "MRL_DSH_REQUIRED": "1", "PYTHONDONTWRITEBYTECODE": "1"}


def new_output(path: Path) -> Path:
    output = path.resolve()
    if not output.is_relative_to(ROOT / "dist"):
        raise ValueError("Gate reports and test storage must be inside checkout dist/.")
    output.mkdir(parents=True, exist_ok=False)
    return output


def save(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), "utf-8")


def verify_dsh_evidence(output: Path, *, readonly: bool) -> str:
    reports = list(
        (output / "pytest").glob("test_actual_dsh_agent_factory_*/host-acceptance/acceptance.json")
    )
    if len(reports) != 1:
        raise RuntimeError(
            "Required actual DSH acceptance did not produce exactly one fresh report."
        )
    report = json.loads(reports[0].read_text("utf-8"))
    cases = report.get("cases", {})
    if (
        report.get("dsh") != "0.2.1-rc.3"
        or report.get("model_called") is not False
        or len(cases) < 17
        or not all(case.get("passed") is True for case in cases.values())
        or (readonly and not cases.get("real_workspace_readonly", {}).get("passed"))
    ):
        raise RuntimeError("Incomplete or failed actual DSH acceptance evidence.")
    return str(reports[0].relative_to(output))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsh-executable", default=os.environ.get("MRL_DSH_EXECUTABLE"))
    parser.add_argument("--dsh-node-modules", default=os.environ.get("MRL_DSH_NODE_MODULES"))
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--real-workspace", type=Path)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dist/_run" / f"release-{uuid.uuid4().hex}"
    )
    args = parser.parse_args()
    try:
        env = {**os.environ, **configuration(args)}
        # Do not inherit a real-workspace opt-in from an unrelated shell.
        env.pop("MRL_DSH_READONLY_WORKSPACE", None)
        # Ambient local filters must never silently deselect the required Host test.
        env.pop("PYTEST_ADDOPTS", None)
        state = None
        if args.real_workspace:
            workspace = args.real_workspace.resolve(strict=True)
            state = workspace / ".math-research-ledger"
            if not state.is_dir() or is_link(state):
                raise ValueError("Read-only smoke requires an existing exact Ledger workspace.")
            if args.output.resolve().is_relative_to(workspace):
                raise ValueError("Reports must not be written inside the research workspace.")
            env["MRL_DSH_READONLY_WORKSPACE"] = str(workspace)
        output = new_output(args.output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    result: dict = {"required_passed": False, "checks": {}, "readonly_enabled": state is not None}
    before = inventory(state) if state else None
    if before is not None:
        save(output / "readonly-before.json", before)
    python = args.python
    commands = [
        ("lint", [python, "-m", "ruff", "check", "src", "tests", "scripts", "benchmarks"]),
        (
            "format",
            [python, "-m", "ruff", "format", "--check", "src", "tests", "scripts", "benchmarks"],
        ),
        ("typing", [python, "-m", "mypy"]),
        (
            "core_mcp_dsh",
            [
                python,
                "-m",
                "pytest",
                "-m",
                "not codex_compat",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(output / "pytest"),
            ],
        ),
        ("build", [python, "-m", "build", "--no-isolation", "--outdir", str(output / "artifacts")]),
        ("diff", ["git", "diff", "--check"]),
    ]
    try:
        for name, command in commands:
            print(f"Required check: {name}", flush=True)
            completed = subprocess.run(command, cwd=ROOT, env=env, check=False, timeout=1800)
            result["checks"][name] = completed.returncode
            if completed.returncode:
                return completed.returncode
            if name == "core_mcp_dsh":
                result["dsh_acceptance_report"] = verify_dsh_evidence(
                    output, readonly=state is not None
                )
                result["checks"]["dsh_evidence"] = 0
        # These two packaging tests do not excuse failures of any shared MCP test.
        try:
            compatibility = subprocess.run(
                [
                    python,
                    "-m",
                    "pytest",
                    "-m",
                    "codex_compat",
                    "-p",
                    "no:cacheprovider",
                    "--basetemp",
                    str(output / "codex-compat"),
                ],
                cwd=ROOT,
                env=env,
                check=False,
                timeout=180,
            )
            result["codex_compat_returncode"] = compatibility.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            result["codex_compat_returncode"] = None
            result["codex_compat_error"] = str(exc)[:1200]
        result["required_passed"] = True
        return 0
    finally:
        if state is not None:
            after = inventory(state)
            save(output / "readonly-after.json", after)
            result["readonly_unchanged"] = before == after
            if before != after:
                result["required_passed"] = False
        save(output / "result.json", result)
        print(f"Gate report: {output / 'result.json'}", flush=True)
        if result.get("readonly_unchanged") is False:
            raise RuntimeError("Real Ledger changed: read-only acceptance failed.")


if __name__ == "__main__":
    raise SystemExit(main())
