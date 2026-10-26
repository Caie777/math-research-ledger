"""Stage the Codex-native plugin with an existing persistent Python runtime.

Install the Ledger wheel with [mcp] into that runtime first. No research path,
runtime, source copy or credentials enter the package. Do not add root plugin.json:
its Agent Plugins loader defaults cwd to PLUGIN_ROOT rather than session cwd.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def prepare(destination: Path, python: str = sys.executable) -> None:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Choose a new package directory; never overwrite an existing install.")
    # Preserve a POSIX venv's python symlink: resolving it selects the base Python.
    interpreter = Path(python).expanduser().absolute()
    interpreter.stat()
    if not interpreter.is_file():
        raise ValueError("Select the persistent runtime's Python executable.")
    destination.mkdir(parents=True)
    shutil.copyfile(ROOT / "LICENSE", destination / "LICENSE")
    for directory in ("skills", ".codex-plugin"):
        shutil.copytree(ROOT / directory, destination / directory)
    config = json.loads((ROOT / ".mcp.json").read_text("utf-8"))
    config["mcpServers"]["math-research-ledger"]["command"] = str(interpreter)
    (destination / ".mcp.json").write_text(json.dumps(config, indent=2) + "\n", "utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    prepare(args.destination, args.python)
