"""Exercise installed plugin discovery through a fresh real Codex app-server.

No model or real research payload is used. Reports contain only Ledger tool names
and explicitly requested synthetic calls. Overrides are invocation-local.
"""

import argparse
import json
import queue
import subprocess
import threading
import time
from pathlib import Path


class Host:
    def __init__(self, workspace: Path, enabled: bool):
        self.workspace = workspace.resolve()
        self.process = subprocess.Popen(
            [
                "codex",
                "app-server",
                "-c",
                f"plugins.math-research-ledger@math-research-ledger-local.enabled={str(enabled).lower()}",
            ],
            cwd=self.workspace,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.lines: queue.Queue = queue.Queue()
        self.seq = 0
        self.errors = []
        threading.Thread(target=self._errors, daemon=True).start()
        threading.Thread(target=self._read, daemon=True).start()
        self.request(
            "initialize",
            {
                "clientInfo": {"name": "ledger-smoke", "version": "1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        self.send({"method": "initialized"})
        value = self.request(
            "thread/start",
            {
                "cwd": str(self.workspace),
                "ephemeral": True,
                "approvalPolicy": "never",
                "sandbox": "workspace-write",
            },
        )
        self.thread_id = value["thread"]["id"]

    def _read(self):
        for line in self.process.stdout:
            try:
                self.lines.put(json.loads(line))
            except ValueError:
                self.lines.put({"bad_protocol": line[:300]})

    def _errors(self):
        for line in self.process.stderr:
            self.errors.append(line[:500])

    def send(self, payload):
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", **payload}) + "\n")
        self.process.stdin.flush()

    def request(self, method, params, timeout=50):
        self.seq += 1
        seq = self.seq
        self.send({"id": seq, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                value = self.lines.get(timeout=max(0.1, deadline - time.monotonic()))
            except queue.Empty:
                break
            if value.get("id") == seq:
                if "error" in value:
                    raise RuntimeError(value["error"])
                return value["result"]
        self.process.terminate()
        raise TimeoutError(method + ": " + "".join(self.errors)[-2000:])

    def inventory(self):
        return self.request("mcpServerStatus/list", {"threadId": self.thread_id})

    def call(self, tool, arguments):
        arguments = {"workspace": str(self.workspace), **arguments}
        return self.request(
            "mcpServer/tool/call",
            {
                "threadId": self.thread_id,
                "server": "math-research-ledger",
                "tool": tool,
                "arguments": arguments,
            },
        )

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--off", action="store_true")
    args = parser.parse_args()
    host = Host(args.workspace, not args.off)
    try:
        value = host.inventory()
        print(
            json.dumps(
                {
                    "servers": [
                        {
                            "name": item["name"],
                            "connectionStatus": item.get("connectionStatus"),
                            "tools": list(item.get("tools", {})),
                            "error": item.get("error"),
                        }
                        for item in value["data"]
                        if "math" in item["name"]
                    ],
                    "server_count": len(value["data"]),
                },
                ensure_ascii=True,
            )
        )
        if not args.off:
            print(json.dumps(host.call("research_status", {}), ensure_ascii=True))
    finally:
        host.close()
