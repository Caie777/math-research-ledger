"""Visible Windows entry: build React, serve it in this process, open when ready.

No backend child can outlive this console. No model is called during startup.
"""

from __future__ import annotations

import argparse
import json
import shutil
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def health(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url + "/api/health?metadata_only=true", timeout=1) as response:
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError):
        return None


def port_available(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def build_frontend(root: Path) -> None:
    from math_research.core.process import run_process

    web = root / "web"
    built = web / "dist" / "index.html"
    sources = [
        *web.joinpath("src").rglob("*"),
        web / "index.html",
        web / "package-lock.json",
        web / "package.json",
        web / "vite.config.ts",
        web / "tsconfig.json",
        root / "README.md",
    ]
    if built.exists() and all(
        p.stat().st_mtime_ns <= built.stat().st_mtime_ns for p in sources if p.is_file()
    ):
        print("Frontend: existing build is current.")
        return
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm or not shutil.which("node"):
        raise RuntimeError("Node.js/npm missing. Install Node.js, then run npm --prefix web ci.")
    if not (web / "node_modules").is_dir():
        raise RuntimeError("Frontend dependencies missing. Run: npm --prefix web ci")
    print("Frontend: building (diagnostics remain visible)...", flush=True)
    # Attached to the visible console: Ctrl+C/window close reaches the build too.
    completed = run_process([npm, "run", "build"], cwd=web, check=False, interactive=True)
    if completed.returncode or not built.is_file():
        raise RuntimeError("Frontend build failed. Fix the diagnostics above and launch again.")


def wait_ready(url: str, identity: str, thread: threading.Thread, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = health(url)
        if result and result.get("workspace_identity") == identity:
            return
        if not thread.is_alive():
            raise RuntimeError("Backend stopped before health became ready. See diagnostics above.")
        time.sleep(0.2)
    raise RuntimeError("Backend health timed out. Check port, permissions and diagnostics above.")


def launch(
    root: Path,
    port: int = 8000,
    *,
    open_browser=webbrowser.open,
    builder=build_frontend,
    server_factory=None,
) -> None:
    import uvicorn

    from math_research.app.api.runs import workspace_identity
    from math_research.app.api.server import create_app
    from math_research.core.workspace import init_workspace

    root = root.resolve()
    state = root / ".math-research"
    identity = workspace_identity(state)
    url = f"http://127.0.0.1:{port}"
    if not port_available(port):
        result = health(url)
        if result and result.get("workspace_identity") == identity:
            # An API-only instance must not be mistaken for a working Web entry.
            try:
                with urllib.request.urlopen(url, timeout=2) as response:
                    if "text/html" not in response.headers.get("Content-Type", ""):
                        raise RuntimeError("Existing backend does not serve the frontend.")
            except OSError as exc:
                raise RuntimeError(
                    "Existing backend has no frontend. Stop it and relaunch."
                ) from exc
            print(f"This workspace is already running: {url}")
            open_browser(url)
            return
        raise RuntimeError(
            f"Port {port} is occupied by another service. Use start.bat --port 8001."
        )
    builder(root)
    if not state.exists():
        init_workspace(root)
    factory = server_factory or (
        lambda app, port: uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info")
        )
    )
    server = factory(create_app(state), port)
    thread = threading.Thread(target=server.run, name="local-web", daemon=True)
    print(
        f"Workspace: {root}\nStarting {url}; keep this console open. Ctrl+C stops the server.",
        flush=True,
    )
    thread.start()
    try:
        wait_ready(url, identity, thread)
        print(f"Ready: {url}", flush=True)
        open_browser(url)
        while thread.is_alive():
            thread.join(0.5)
    finally:
        server.should_exit = True
        thread.join(10)
        if thread.is_alive():
            server.force_exit = True
        print("Web server stopped.", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if sys.version_info < (3, 11):  # noqa: UP036 - launcher diagnoses older runtimes
        print("Python 3.11+ is required.")
        return 1
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        launch(repo_root(), args.port)
        return 0
    except KeyboardInterrupt:
        return 0
    except (ImportError, RuntimeError, OSError) as exc:
        print(
            f"Startup failed: {exc}\nInstall: python -m pip install -e .[openai,anthropic]",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
