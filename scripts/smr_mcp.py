"""Stable checkout launcher; preserve host cwd for multi-project discovery."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from math_research.mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
