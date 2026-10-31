"""Prepare the manual single-workspace fallback only; prefer prepare_dsh_host_plugin.py.

Render static configuration and an external Python runtime; never invoke DSH.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "integrations/deepseek-harness/config-bundle"
FILES = (
    "package.json",
    "cordis.patch.yml",
    "locale/en.json",
    "locale/zh.json",
    "icon.svg",
    "README.md",
    "LICENSE",
)


def run(command: list[str], *, timeout: int = 30) -> str:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=timeout,
    )
    if result.returncode:
        raise ValueError(
            f"{Path(command[0]).name} failed (exit {result.returncode}): {result.stderr[-1200:]}"
        )
    return result.stdout.strip()


def python_info(python: Path) -> dict:
    if not python.is_file():
        raise ValueError("Python executable does not exist; provide --python PATH.")
    info = json.loads(
        run(
            [
                str(python),
                "-I",
                "-B",
                "-c",
                "import sys,json;print(json.dumps({'version':list(sys.version_info[:2]),"
                "'executable':sys.executable}))",
            ]
        )
    )
    if info["version"][0] != 3 or not 11 <= info["version"][1] <= 13:
        raise ValueError("Use Python 3.11–3.13; Python 3.12 is recommended, not 3.14.")
    return info


def select_python(explicit: Path | None) -> Path:
    if explicit is not None:
        python = explicit.expanduser().absolute()
    else:
        try:
            python = Path(run(["py", "-3.12", "-c", "import sys;print(sys.executable)"]))
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise ValueError(
                "Python 3.12 not found. Install Python 3.12 or pass --python; "
                "no download or 3.14 fallback is performed."
            ) from exc
    info = python_info(python)
    if explicit is None and info["version"] != [3, 12]:
        raise ValueError("The automatic launcher must select Python 3.12.")
    if info["version"] != [3, 12]:
        print("Python 3.12 is recommended for DSH.", file=sys.stderr)
    # Do not resolve a POSIX venv's python symlink to its base interpreter.
    return python


def quote(value: str) -> str:
    if any(c in value for c in "\n\r\x00"):
        raise ValueError("Deployment paths cannot contain control characters.")
    return "'" + value.replace("'", "''") + "'"


def workspace_root(path: Path) -> Path:
    root = path.expanduser().resolve(strict=True)
    if not root.is_dir() or not any(
        (root / name).is_dir() for name in (".math-research-ledger", ".math-research")
    ):
        raise ValueError(
            "Workspace must already contain .math-research-ledger or .math-research; "
            "initialize separately. Preparation never creates state."
        )
    return root


def wheel_version(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("Expected one Ledger wheel METADATA.")
        metadata = Parser().parsestr(archive.read(names[0]).decode("utf-8"))
    if metadata["Name"] != "math-research-ledger":
        raise ValueError("--wheel must contain math-research-ledger.")
    return str(metadata["Version"])


def verify_runtime(python: Path, version: str) -> None:
    actual = run(
        [
            str(python),
            "-I",
            "-B",
            "-c",
            "import math_research,mcp,math_research.mcp.server;print(math_research.__version__)",
        ]
    )
    if actual != version:
        raise ValueError(
            f"Runtime version {actual!r} differs from Bundle {version}; "
            "install the matching wheel before rendering."
        )


def prepare(args: argparse.Namespace) -> Path:
    workspace = workspace_root(args.workspace)
    wheel = args.wheel.expanduser().resolve(strict=True)
    version = json.loads((TEMPLATE / "package.json").read_text("utf-8"))["version"]
    if wheel_version(wheel) != version:
        raise ValueError("Wheel/Bundle version mismatch; use the matching local candidate.")
    out, runtime = args.out.expanduser().resolve(), args.runtime.expanduser().absolute()
    for other in (workspace, runtime.resolve()):
        if out.is_relative_to(other) or other.is_relative_to(out):
            raise ValueError("Bundle output must be separate from workspace and runtime.")
    if not args.no_install:
        if runtime.resolve().is_relative_to((ROOT / "dist").resolve()):
            raise ValueError("Keep the persistent runtime outside the repository dist directory.")
        if runtime.resolve().is_relative_to(workspace) or workspace.is_relative_to(
            runtime.resolve()
        ):
            raise ValueError("Runtime must be separate from the research workspace.")
    if out.exists():
        if not args.force:
            raise ValueError("Output exists; use a new --out or explicitly --force.")
        existing = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
        if existing != set(FILES) or any(
            p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in out.rglob("*")
        ):
            raise ValueError(
                "--force only replaces a complete prepared Bundle, without extra files."
            )
        if (
            json.loads((out / "package.json").read_text("utf-8"))["name"]
            != "dsh-math-research-ledger"
        ):
            raise ValueError("Refusing to replace an unrelated directory.")
    if args.no_install and args.python is None:
        raise ValueError("--no-install requires --python pointing to an installed runtime.")
    python = select_python(args.python)
    if not args.no_install:
        target = runtime / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if runtime.exists() and not (runtime / "pyvenv.cfg").is_file():
            raise ValueError("Existing runtime is not a venv; choose a dedicated empty path.")
        if not target.is_file():
            run([str(python), "-I", "-B", "-m", "venv", str(runtime)], timeout=180)
        python_info(target)
        python = target
        command = [str(python), "-I", "-B", "-m", "pip", "install", "--force-reinstall"]
        if args.no_index:
            command.append("--no-index")
        if args.find_links:
            command.extend(["--find-links", str(args.find_links.expanduser().resolve(strict=True))])
        run([*command, f"{wheel}[mcp]"], timeout=900)
    verify_runtime(python, version)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mrl-config-", dir=out.parent) as temporary:
        stage = Path(temporary) / "bundle"
        for name in FILES:
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / "LICENSE" if name == "LICENSE" else TEMPLATE / name, target)
        patch = stage / "cordis.patch.yml"
        text = patch.read_text("utf-8").replace("__MRL_PYTHON__", quote(str(python)))
        text = text.replace("__MRL_WORKSPACE__", quote(str(workspace)))
        if "__MRL_" in text:
            raise ValueError("Unresolved deployment placeholder.")
        patch.write_text(text, encoding="utf-8")
        rows = json.loads(
            run(
                [
                    str(python),
                    "-I",
                    "-B",
                    "-c",
                    "import yaml,json,sys;from pathlib import Path;"
                    "print(json.dumps(yaml.safe_load(Path(sys.argv[1]).read_text('utf-8'))))",
                    str(patch),
                ]
            )
        )
        expected = [
            {
                "insert": [
                    {
                        "id": "mcp-math-research-ledger",
                        "name": "@deepseek-ai/dsh-mcp-client",
                        "config": {
                            "serverName": "math-research-ledger",
                            "transport": "stdio",
                            "command": str(python),
                            "args": [
                                "-B",
                                "-m",
                                "math_research.mcp.server",
                                "--workspace",
                                str(workspace),
                            ],
                            "failOnStartupError": True,
                            "toolCallTimeoutMs": 120000,
                        },
                    }
                ]
            }
        ]
        if rows != expected:
            raise ValueError("Rendered patch does not match the single pinned MCP contract.")
        if out.exists():
            shutil.rmtree(out)  # Only the exact managed allowlist checked above.
        stage.rename(out)
    return out


def main() -> None:
    local = (
        Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "MathResearchLedger"
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=local / "bundle")
    parser.add_argument("--runtime", type=Path, default=local / "runtime")
    parser.add_argument("--python", type=Path)
    for flag in ("force", "no-install", "no-index"):
        parser.add_argument("--" + flag, action="store_true")
    parser.add_argument("--find-links", type=Path)
    args = parser.parse_args()
    print(
        "WARNING: FALLBACK / manual single-workspace integration, not the recommended Host plugin. "
        "Remove dsh-math-research-ledger-host from the target Profile before adding this Bundle; "
        "OFF alone can leave both installation candidates visible. "
        "Preparation never changes the Profile or runs DSH.",
        file=sys.stderr,
    )
    try:
        out = prepare(args)
    except (OSError, ValueError, subprocess.TimeoutExpired, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Preparation failed: {exc}\n")
    # Single quotes are PowerShell literals, including spaces and apostrophes.
    print(
        "Run in ordinary PowerShell; do not run DSH plugin installation from a sandboxed DSH shell."
    )
    print("# Replace desktop with the target Profile; remove each package only if installed.")
    print("# Required for fallback: remove the alternative Host plugin first (OFF is not removal).")
    print("dsh plugin --profile desktop remove dsh-math-research-ledger-host")
    print("# Upgrade an existing fallback only:")
    print("dsh plugin --profile desktop remove dsh-math-research-ledger")
    print("dsh plugin --profile desktop add " + quote(str(out)))


if __name__ == "__main__":
    main()
