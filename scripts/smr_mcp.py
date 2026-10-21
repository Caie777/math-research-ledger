"""Stable checkout launcher; preserve host cwd for multi-project discovery."""

import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
interpreter = os.environ.get("MRL_PYTHON")
if interpreter and Path(interpreter).resolve() != Path(sys.executable).resolve():
    # Optional developer deployment interpreter; never change the harness cwd.
    os.execv(interpreter, [interpreter, "-B", str(Path(__file__).resolve()), *sys.argv[1:]])
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from math_research.mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
