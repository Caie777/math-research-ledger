"""Build an allowlisted DSH bundle directory with the actual Python wheel, without publishing."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "integrations/deepseek-harness/bundle"
FILES = (
    "package.json",
    "index.mjs",
    "transport.mjs",
    "cordis.patch.yml",
    "install.py",
    "README.md",
)


def build(destination: Path) -> None:
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Destination must not exist; choose a fresh output directory.")
    destination.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(BUNDLE / name, destination / name)
    shutil.copy2(ROOT / "LICENSE", destination / "LICENSE")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(destination / "runtime"),
        ],
        cwd=ROOT,
        check=True,
    )
    print(f"DSH bundle ready: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    build(parser.parse_args().destination)
