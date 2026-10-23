"""Explicitly prepare a bundle-local Python runtime; never touch research or DSH auth."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def verify(python: Path) -> None:
    subprocess.run([str(python), "-B", "-c", "import math_research.mcp.server, mcp"], check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python", type=Path, help="Reuse an already installed interpreter explicitly."
    )
    parser.add_argument("--no-index", action="store_true")
    parser.add_argument(
        "--find-links", type=Path, help="Optional offline dependency wheel directory."
    )
    args = parser.parse_args()
    if args.python:
        python = args.python.expanduser().resolve(strict=True)
    else:
        wheels = list((ROOT / "runtime").glob("math_research_ledger-*.whl"))
        if len(wheels) != 1:
            parser.error(
                "Expected one bundled Ledger wheel. Use scripts/build_dsh_bundle.py first."
            )
        if sys.version_info < (3, 11):  # noqa: UP036 -- standalone installer, before pip checks
            parser.error("Python 3.11+ is required.")
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
        python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        # A rebuilt local wheel can retain its version during pre-release work.
        # Never keep old code merely because that version is already installed.
        command = [str(python), "-m", "pip", "install", "--force-reinstall"]
        if args.no_index:
            command.append("--no-index")
        if args.find_links:
            command.extend(["--find-links", str(args.find_links.resolve())])
        subprocess.run([*command, f"{wheels[0]}[mcp]"], check=True)
    verify(python)
    temporary = ROOT / ".runtime.json.tmp"
    temporary.write_text(json.dumps({"python": str(python)}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(ROOT / ".runtime.json")
    print("Ledger Python ready. Install this directory with dsh plugin --profile PROFILE add PATH.")
    print("No workspace was initialized; no DSH configuration or authentication was changed.")


if __name__ == "__main__":
    main()
