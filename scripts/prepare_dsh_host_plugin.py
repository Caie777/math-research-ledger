"""Prepare only the recommended DSH Host plugin; never install runtime or select workspace."""

import argparse
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "integrations/deepseek-harness/host-plugin"


def prepare(destination: Path, python: Path) -> None:
    destination = destination.resolve()
    interpreter = python.expanduser().absolute()
    if not interpreter.is_file():
        raise ValueError(
            "Select an existing persistent Python executable with Ledger+[mcp] installed."
        )
    if destination.exists():
        raise ValueError("Choose a new package directory; never overwrite an installation.")
    shutil.copytree(TEMPLATE, destination)
    shutil.copyfile(ROOT / "LICENSE", destination / "LICENSE")
    patch = destination / "cordis.patch.yml"
    rows = yaml.safe_load(patch.read_text("utf-8"))
    rows[0]["insert"][0]["config"]["python"] = str(interpreter)
    patch.write_text(yaml.safe_dump(rows, sort_keys=False), "utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--python", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.out, args.python)
    out_literal = "'" + str(args.out.resolve()).replace("'", "''") + "'"
    print(
        "Prepared only the recommended Host plugin; no fallback Bundle was prepared or installed."
    )
    print("Run in ordinary PowerShell; preparation never changes the Profile or runs DSH.")
    print("# Replace desktop with the target Profile; remove each package only if installed.")
    print("# Migrate from the old fallback: OFF can leave both installation candidates visible.")
    print("dsh plugin --profile desktop remove dsh-math-research-ledger")
    print("# Upgrade an existing Host plugin only:")
    print("dsh plugin --profile desktop remove dsh-math-research-ledger-host")
    print("dsh plugin --profile desktop add " + out_literal)
