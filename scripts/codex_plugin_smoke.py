"""Windows Codex 0.160.0 native-plugin acceptance; isolated home, no model.

Use a NEW directory under dist/ and an existing wheel+[mcp] Python runtime.
Commands run from this checkout; thread cwd values are synthetic workspaces.
No user authentication/configuration is copied. Evidence remains ignored.
"""

import argparse
import concurrent.futures
import ctypes
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

from prepare_local_plugin import prepare

ROOT = Path(__file__).resolve().parents[1]
SERVER = "math-research-ledger"
IDENTITY = SERVER + "@ledger-session-acceptance"


class Host:
    def __init__(self, environment):
        self.process = subprocess.Popen(
            ["codex", "app-server"],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.lines = queue.Queue()
        self.seq = 0
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain, daemon=True).start()
        self.request(
            "initialize",
            {
                "clientInfo": {"name": "ledger-session-acceptance", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self.send({"method": "initialized"})

    def _read(self):
        for line in self.process.stdout:
            try:
                self.lines.put(json.loads(line))
            except ValueError:
                self.lines.put({"invalid_protocol": True})

    def _drain(self):
        # Do not capture unrelated Host catalog/authentication warmup logs.
        for _ in self.process.stderr:
            pass

    def send(self, value):
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", **value}) + "\n")
        self.process.stdin.flush()

    def request(self, method, params, timeout=45):
        self.seq += 1
        seq = self.seq
        self.send({"id": seq, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = self.lines.get(timeout=max(0.1, deadline - time.monotonic()))
            except queue.Empty:
                break
            if value.get("invalid_protocol"):
                raise RuntimeError("Non-JSON Host stdout")
            if value.get("id") == seq:
                if "error" in value:
                    raise RuntimeError(f"{method}: {value['error']['code']}")
                return value["result"]
            if "method" in value and "id" in value:
                self.send({"id": value["id"], "error": {"code": -32601, "message": "Unsupported"}})
        raise TimeoutError(method)

    def start(self, root, *, ephemeral=True):
        return self.request(
            "thread/start",
            {
                "cwd": str(root),
                "ephemeral": ephemeral,
                "approvalPolicy": "never",
                "sandbox": "read-only",
            },
        )["thread"]["id"]

    def inventory(self, thread):
        data = self.request("mcpServerStatus/list", {"threadId": thread})["data"]
        assert all(x.get("pluginId") == IDENTITY for x in data), "Unexpected direct/other MCP"
        return data

    def call(self, thread, tool="research_status", **arguments):
        result = self.request(
            "mcpServer/tool/call",
            {
                "threadId": thread,
                "server": SERVER,
                "tool": tool,
                "arguments": arguments,
            },
        )
        return result.get("structuredContent") or json.loads(result["content"][0]["text"])

    def check(self, thread, root):
        inventory = self.inventory(thread)
        assert len(inventory) == 1 and len(inventory[0]["tools"]) == 11
        assert inventory[0]["runtimeStatus"] == "connected"
        result = self.call(thread)
        assert Path(result["workspace_root"]).resolve() == Path(root).resolve()
        return result

    def skill(self, root):
        result = self.request("skills/list", {"cwds": [str(root)], "forceReload": True})
        return any(
            x.get("enabled") and x.get("pluginId") == IDENTITY
            for row in result["data"]
            for x in row["skills"]
        )

    def enabled(self, value, config):
        self.request(
            "config/value/write",
            {
                "keyPath": f'plugins."{IDENTITY}".enabled',
                "mergeStrategy": "upsert",
                "value": value,
                "filePath": str(config),
            },
        )
        self.request("config/mcpServer/reload", None)

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)


def processes():
    """Windows PID/parent/executable names only; no command lines or environment."""
    from ctypes import wintypes

    class Entry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("pid", wintypes.DWORD),
            ("heap", ctypes.c_size_t),
            ("module", wintypes.DWORD),
            ("threads", wintypes.DWORD),
            ("parent", wintypes.DWORD),
            ("priority", wintypes.LONG),
            ("flags", wintypes.DWORD),
            ("exe", wintypes.WCHAR * 260),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == wintypes.HANDLE(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    entry = Entry()
    entry.size = ctypes.sizeof(entry)
    data = {}
    try:
        ok = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while ok:
            data[entry.pid] = (entry.parent, entry.exe)
            ok = kernel.Process32NextW(handle, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(handle)
    return data


def python_pids(host):
    data = processes()
    family = {host.process.pid}
    for _ in range(8):
        family.update(pid for pid, (parent, _) in data.items() if parent in family)
    return sorted(pid for pid in family if data.get(pid, (0, ""))[1].lower() == "python.exe")


def gone(pids):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not set(pids) & processes().keys():
            return True
        time.sleep(0.2)
    return False


def run(destination, python):
    if os.name != "nt":
        raise RuntimeError("This Host lifecycle script currently requires Windows.")
    base = destination.resolve()
    if not base.is_relative_to(ROOT / "dist") or base == ROOT / "dist":
        raise ValueError("Use a NEW evidence directory strictly inside checkout dist/.")
    base.mkdir(parents=True, exist_ok=False)
    home, temp = base / "home", base / "temp"
    home.mkdir()
    temp.mkdir()
    # Pass OS launch settings only; never forward API keys or a real Codex profile.
    environment = {
        name: os.environ[name]
        for name in (
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "HOMEDRIVE",
            "HOMEPATH",
            "OS",
            "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE",
        )
        if name in os.environ
    }
    environment.update(CODEX_HOME=str(home), TEMP=str(temp), TMP=str(temp))

    def command(args):
        value = subprocess.run(
            args,
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
        if value.returncode:
            raise RuntimeError(f"{args[:2]} failed: exit {value.returncode}")
        return value.stdout.strip()

    report = {"codex": command(["codex", "--version"]), "cases": {}}

    def record(name, **facts):
        report["cases"][name] = facts
        (base / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
        print(name, json.dumps(facts), flush=True)

    roots = [base / name for name in ("workspace-A", "workspace-B", "ordinary")]
    for root in roots:
        root.mkdir()
        command(["git", "init", "--quiet", str(root)])
    a, b, empty = roots
    command(
        [
            str(Path(python).resolve()),
            "-B",
            "-c",
            "import sys; from pathlib import Path; "
            "from math_research.core.workspace import init_workspace; "
            "from math_research.services.research import create_problem; "
            "[(init_workspace(Path(p)), create_problem(Path(p)/'.math-research-ledger', "
            "'SYNTHETIC_'+Path(p).name)) for p in sys.argv[1:]]",
            str(a),
            str(b),
        ]
    )
    (b / "subdir").mkdir()
    market = base / "marketplace"
    prepare(market / "plugins" / SERVER, python)
    index = market / ".agents/plugins"
    index.mkdir(parents=True)
    (index / "marketplace.json").write_text(
        json.dumps(
            {
                "name": "ledger-session-acceptance",
                "interface": {"displayName": "Ledger acceptance"},
                "plugins": [
                    {
                        "name": SERVER,
                        "source": {"source": "local", "path": "./plugins/" + SERVER},
                        "category": "Developer Tools",
                        "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                    }
                ],
            }
        ),
        "utf-8",
    )
    config = home / "config.toml"
    config.write_text(
        "\n".join(
            "[projects." + json.dumps(str(root)) + ']\ntrust_level="trusted"\n' for root in roots
        ),
        "utf-8",
    )
    command(["codex", "plugin", "marketplace", "add", str(market), "--json"])
    command(["codex", "plugin", "add", IDENTITY, "--json"])
    hosts = []

    def new():
        host = Host(environment)
        hosts.append(host)
        return host

    try:
        h1, h2 = new(), new()
        t1, t2 = h1.start(a), h2.start(b)
        sa, sb = h1.check(t1, a), h2.check(t2, b)
        assert "workspace-B" not in json.dumps(sa) and "workspace-A" not in json.dumps(sb)
        assert h1.call(t1, workspace=str(b))["error"]["code"] == "WORKSPACE_OUT_OF_SCOPE"
        pa, pb = python_pids(h1), python_pids(h2)
        assert pa and pb and not set(pa) & set(pb)
        record("different_workspace_concurrent", passed=True, tools=[11, 11], pids=[pa, pb])
        h3 = new()
        t3 = h3.start(a)
        h3.check(t3, a)
        marker = a / ".math-research-ledger/.checkpoint-generation"
        before = marker.read_bytes() if marker.exists() else None

        def write(item):
            host, thread, label = item
            return host.call(
                thread,
                "research_create_problem",
                title=label,
                statement="Synthetic fixture only.",
                primary_target="Writer consistency.",
            )

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            writes = list(pool.map(write, [(h1, t1, "WRITER_A"), (h3, t3, "WRITER_B")]))
        assert all("error" not in item for item in writes), writes
        assert len({item["problem_id"] for item in writes}) == 2
        assert h1.check(t1, a) == h3.check(t3, a)
        assert h1.call(t1)["problems"] == 3 and marker.read_bytes() != before
        assert not (marker.parent / ".checkpoint.lock").exists()
        search = h1.call(t1, "research_search", query="WRITER_A", limit=1)
        assert "WRITER_A" in json.dumps(search) and "workspace-B" not in json.dumps(search)
        record(
            "same_workspace_concurrent",
            passed=True,
            tools=[11, 11],
            problems=3,
            generation_changed=True,
            lock_released=True,
            status_search=True,
        )
        for name, root in (
            ("subdirectory_exact_root", b / "subdir"),
            ("state_directory_exact_root", b / ".math-research-ledger"),
            ("uninitialized", empty),
        ):
            thread = h2.start(root)
            assert len(h2.inventory(thread)[0]["tools"]) == 11
            assert h2.call(thread)["error"]["code"] == "NO_WORKSPACE"
            assert not (root / ".math-research-ledger").exists()
            record(name, passed=True, tools=11, error="NO_WORKSPACE", auto_init=False)
        h1.check(h1.start(str(a).swapcase()), a)
        link = base / "workspace-A-junction"
        command(["cmd", "/c", "mklink", "/J", str(link), str(a)])
        try:
            h1.check(h1.start(link), a)
        finally:
            link.rmdir()  # Remove only this new link, never its target.
        record(
            "windows_paths",
            passed=True,
            absolute=True,
            case_equivalent=True,
            junction_equivalent=True,
            unc="untested",
        )
        pids = python_pids(h1)
        h1.request("config/mcpServer/reload", None)
        h1.check(t1, a)
        record("reload", passed=True, same_processes=pids == python_pids(h1), rebind=False)
        escaped = str(b).replace("'", "''")
        shell = h1.request(
            "command/exec",
            {
                "command": [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Set-Location -LiteralPath '{escaped}'; (Get-Location).Path",
                ],
                "cwd": str(a),
                "timeoutMs": 10000,
                "outputBytesCap": 1000,
                "sandboxPolicy": {"type": "readOnly"},
            },
            timeout=18,
        )
        assert shell["exitCode"] == 0 and str(b) in shell["stdout"]
        h1.check(t1, a)
        record(
            "shell_cd_immutability",
            passed=True,
            bound="workspace-A",
            surface="standalone command/exec; not a model turn",
        )
        assert h1.skill(a)
        h1.enabled(False, config)
        assert not h1.inventory(t1) and not h1.skill(a)
        record(
            "plugin_OFF_existing_session",
            passed=True,
            tools=0,
            skill=False,
            idle_processes_retained=bool(python_pids(h1)),
        )
        off = new()
        assert not off.inventory(off.start(a)) and not off.skill(a) and not python_pids(off)
        record("plugin_OFF", passed=True, tools=0, skill=False, processes=0)
        h1.enabled(True, config)
        h1.check(t1, a)
        assert h1.skill(a)
        record(
            "plugin_ON_existing_session",
            passed=True,
            tools=11,
            skill=True,
            reuses_idle_processes=python_pids(h1) == pids,
        )
        on = new()
        ton = on.start(a, ephemeral=False)
        on.check(ton, a)
        assert on.skill(a)
        record("plugin_ON", passed=True, tools=11, skill=True)
        active = python_pids(on)
        on.request("thread/archive", {"threadId": ton})
        record("session_dispose", passed=gone(active), surface="thread/archive", pids=active)
        assert report["cases"]["session_dispose"]["passed"]
        restart = new()
        restart.check(restart.start(b), b)
        record("restart", passed=True, tools=11, bound="workspace-B")
    finally:
        active = []
        for host in hosts:
            active.extend(python_pids(host))
            host.close()
        record("host_dispose", passed=gone(active), pids=active)
    assert all(item.get("passed") for item in report["cases"].values()), report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="Persistent wheel+[mcp] Python")
    parser.add_argument("--output", type=Path, required=True, help="NEW directory under dist/")
    arguments = parser.parse_args()
    run(arguments.output, arguments.python)
