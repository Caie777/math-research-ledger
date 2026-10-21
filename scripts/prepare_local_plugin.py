"""Stage a portable local plugin; optionally pin a developer Python interpreter.

The staged package contains source and instructions, never a workspace or venv.
Install .[mcp] dependencies into the selected interpreter before starting a host.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(destination: Path, python: str = "python") -> None:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Choose a new package directory; never overwrite an existing install.")
    destination.mkdir(parents=True)
    for filename in ("plugin.json", "LICENSE"):
        shutil.copyfile(ROOT / filename, destination / filename)
    for directory in ("skills", ".codex-plugin"):
        shutil.copytree(ROOT / directory, destination / directory)
    shutil.copytree(
        ROOT / "src/math_research",
        destination / "src/math_research",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (destination / "scripts").mkdir()
    shutil.copyfile(ROOT / "scripts/smr_mcp.py", destination / "scripts/smr_mcp.py")
    config = json.loads((ROOT / "mcp.json").read_text("utf-8"))
    if python != "python":
        config["mcpServers"]["math-research-ledger"]["env"] = {"MRL_PYTHON": python}
    (destination / "mcp.json").write_text(json.dumps(config, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    prepare(args.destination, args.python)
