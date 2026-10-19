"""Thin stdio adapter for installed Codex dynamic tools and sandboxed command/exec.

No model protocol emulation: a pending native item/tool/call pauses Codex until
the existing loop supplies its structured observation. Private reasoning events
are discarded, never recorded. No server daemon, shell tool, or MCP auto-load.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from math_research.agent.providers.base import BaseProvider, ProviderResponse, TokenUsage
from math_research.agent.session import SessionMessage
from math_research.agent.transport import (
    CodexCLIExecutor,
    _codex_env,
    _terminate,
    _validate_codex_options,
)
from math_research.core.errors import ResearchError
from math_research.core.process import hidden_process_kwargs, spawn_process
from math_research.memory.records.write_boundary import automated_research


class CommandExecutionTimeout(ResearchError):
    """The sandbox reported a command deadline, not an isolation failure."""


class McpPolicyRejection(ResearchError):
    """A valid native MCP request was outside the registered research tool identities."""

    def __init__(self, metadata: dict):
        self.metadata = metadata
        super().__init__(
            "Requested MCP tool is not available in research_standard: "
            f"server={metadata['server']}; tool={metadata['tool']}. "
            "Use one of the allowed research tools instead."
        )


class CodexRPC:
    """Owned bounded pipe transport; unsupported methods fail closed."""

    def __init__(
        self,
        cwd: Path,
        *,
        env: dict,
        overrides: list[str] | None = None,
        deadline: float | None = None,
    ):
        binary = shutil.which("codex")
        if not binary:
            raise ResearchError("Codex CLI unavailable.")
        argv = [binary]
        for value in overrides or []:
            argv += ["-c", value]
        argv += ["app-server", "--strict-config", "--listen", "stdio://"]
        self.process = spawn_process(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=os.name != "nt",
            **hidden_process_kwargs(),
        )
        self.messages: queue.Queue[dict] = queue.Queue(maxsize=256)
        self.dead = threading.Event()
        self.sequence = 0
        self.deadline = deadline
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.call(
                "initialize",
                {
                    "clientInfo": {"name": "mch_research", "version": "0"},
                    "capabilities": {"experimentalApi": True},
                },
            )
            self.send({"method": "initialized", "params": {}})
        except Exception:
            self.close()
            raise

    def _read(self) -> None:
        assert self.process.stdout is not None
        try:
            while line := self.process.stdout.readline(2_000_001):
                if len(line) > 2_000_000:
                    break
                obj = json.loads(line)
                # Exclude reasoning and raw internal events before queuing or persistence.
                method = obj.get("method", "")
                if "reasoning" in method.lower() or method.startswith("codex/event/"):
                    continue
                item = obj.get("params", {}).get("item", {})
                if item.get("type") == "reasoning":
                    continue
                while not self.dead.is_set():
                    try:
                        self.messages.put(obj, timeout=0.1)
                        break
                    except queue.Full:
                        continue
        except (ValueError, OSError):
            pass
        finally:
            self.dead.set()

    def send(self, obj: dict) -> None:
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def next(
        self,
        deadline: float,
        stop: Callable[[], bool] | None = None,
        on_tick: Callable[[], None] | None = None,
    ) -> dict:
        while time.monotonic() < deadline:
            if on_tick:
                on_tick()
            if stop and stop():
                raise InterruptedError("USER_STOP")
            try:
                return self.messages.get(timeout=0.1)
            except queue.Empty:
                if self.dead.is_set():
                    raise ResearchError("Codex app-server pipe closed.") from None
        raise TimeoutError("Codex request exceeded run deadline.")

    def call(
        self,
        method: str,
        params: dict,
        *,
        timeout: float = 15,
        on_event: Callable[[dict], None] | None = None,
        on_tick: Callable[[], None] | None = None,
    ) -> dict:
        self.sequence += 1
        call_id = self.sequence
        self.send({"id": call_id, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        if self.deadline:
            deadline = min(deadline, self.deadline)
        while True:
            obj = self.next(deadline, on_tick=on_tick)
            if on_event:
                on_event(obj)
            if obj.get("id") == call_id:
                if "error" in obj:
                    message = str(obj["error"].get("message", "Codex RPC failed"))
                    if (
                        method == "command/exec"
                        and message == "exec failed: sandbox error: command timed out"
                    ):
                        raise CommandExecutionTimeout(message)
                    raise ResearchError(message)
                return obj.get("result", {})

    def close(self) -> None:
        self.dead.set()
        _terminate(self.process)
        for pipe in (self.process.stdin, self.process.stdout):
            if pipe:
                pipe.close()


class CodexToolProvider(BaseProvider):
    name = "codex"

    def __init__(
        self,
        model: str | None,
        effort: str | None,
        *,
        deadline: float,
        should_stop: Callable[[], bool],
        tool_free: bool = False,
        allowed_mcp_tools: frozenset[tuple[str, str]] = frozenset(),
    ):
        _validate_codex_options(model, effort)
        self.model_name = model
        self.effort = effort
        self.deadline = deadline
        self.should_stop = should_stop
        self.tool_free = tool_free
        self.allowed_mcp_tools = allowed_mcp_tools if not tool_free else frozenset()
        self.mcp_items: dict[str, tuple[str, str]] = {}
        self.rejection_instruction: str | None = None
        self.rpc: CodexRPC | None = None
        self.home: tempfile.TemporaryDirectory | None = None
        self.pending: dict | None = None
        self.thread_id: str | None = None
        self.turn_id: str | None = None
        self.usage: dict = {}
        self.version: str | None = None
        self.on_public: Callable[[str], None] | None = None
        self.on_diagnostic: Callable[[dict], None] | None = None
        self.on_mcp_outcome: Callable[[dict, bool], None] | None = None
        self.reported_usage: dict = {}

    def _start(self, messages: list[SessionMessage], tools: list[dict]) -> None:
        self.version = CodexCLIExecutor().preflight(deadline=self.deadline)
        self.home = tempfile.TemporaryDirectory(prefix="mch-codex-agent-")
        folder = Path(self.home.name)
        env = _codex_env()
        original_home = Path(env["CODEX_HOME"])
        # File auth remains ephemeral; never copied to persisted run/artifact storage.
        auth = original_home / "auth.json"
        if not auth.is_file():
            raise ResearchError("V0 needs Codex file-backed ChatGPT login (auth.json).")
        isolated_home = folder / "codex"
        isolated_home.mkdir()
        shutil.copyfile(auth, isolated_home / "auth.json")
        disabled = ""
        if self.tool_free:
            disabled = "".join(
                f"{feature} = false\n"
                for feature in (
                    "shell_tool",
                    "unified_exec",
                    "browser_use",
                    "computer_use",
                    "hooks",
                    "skill_search",
                    "memories",
                    "image_generation",
                    "view_image",
                    "goals",
                    "sleep_tool",
                    "workspace_dependencies",
                )
            )
        (isolated_home / "config.toml").write_text(
            'default_permissions = ":read-only"\nweb_search = "disabled"\n'
            # No external apps/plugins are part of today's custom research registry.
            # Exclude them at launch, before an item/started notification could arrive.
            "[apps._default]\nenabled = false\n"
            "[features]\napps = false\nplugins = false\nmulti_agent = false\n" + disabled,
            encoding="utf-8",
        )
        env["CODEX_HOME"] = str(isolated_home)
        self.rpc = CodexRPC(folder, env=env, deadline=self.deadline)
        result = self.rpc.call(
            "thread/start",
            {
                "cwd": str(folder),
                "ephemeral": True,
                "environments": [],
                "permissions": ":read-only",
                "approvalPolicy": "never",
                "model": self.model_name,
                "baseInstructions": messages[0].content,
                "dynamicTools": [
                    {
                        "type": "function",
                        "name": s["name"],
                        "description": s["description"],
                        "inputSchema": s["parameters"],
                    }
                    for s in tools
                ],
            },
        )
        self.thread_id = result["thread"]["id"]
        self.model_name = result.get("model") or self.model_name
        self.rpc.call(
            "turn/start",
            {
                "threadId": self.thread_id,
                "effort": self.effort,
                "environments": [],
                "input": [{"type": "text", "text": "\n\n".join(m.content for m in messages[1:])}],
            },
        )

    @automated_research
    def generate(
        self, messages: list[SessionMessage], tools: list[dict] | None = None
    ) -> ProviderResponse:
        if self.rpc is None:
            self._start(messages, tools or [])
        elif self.pending:
            observation = next(
                (
                    m
                    for m in reversed(messages)
                    if m.role == "tool"
                    and m.metadata.get("tool_call_id") == self.pending["params"]["callId"]
                ),
                None,
            )
            if observation is None:
                raise ResearchError("Missing native tool observation.")
            content_items = [{"type": "inputText", "text": observation.content}]
            # A policy reminder rides the matching dynamic-tool response inside
            # the live native turn. No new thread/turn or hidden context replay.
            content_items.extend(
                {"type": "inputText", "text": m.content}
                for m in messages
                if m.metadata.get("research_reflection")
            )
            self.rpc.send(
                {
                    "id": self.pending["id"],
                    "result": {
                        "success": observation.metadata.get("ok", True),
                        "contentItems": content_items,
                    },
                }
            )
            self.pending = None
        else:
            # The previous native turn ended with a premature final message.
            # Continue this SAME thread with only the new instruction, not history.
            instruction = self.rejection_instruction or next(
                m.content
                for m in reversed(messages)
                if m.role == "user" and not m.metadata.get("research_reflection")
            )
            reminders = [m.content for m in messages if m.metadata.get("research_reflection")]
            self.rpc.call(
                "turn/start",
                {
                    "threadId": self.thread_id,
                    "effort": self.effort,
                    "environments": [],
                    "input": [{"type": "text", "text": "\n\n".join([instruction, *reminders])}],
                },
            )
            self.rejection_instruction = None
        assert self.rpc is not None
        final = ""
        while True:
            obj = self.rpc.next(self.deadline, self.should_stop)
            method = obj.get("method")
            params = obj.get("params", {})
            if method == "turn/started":
                self.turn_id = params["turn"]["id"]
            elif method == "thread/tokenUsage/updated":
                self.usage = params.get("tokenUsage", {}).get("total", {})
            elif (
                method in {"item/started", "item/completed"}
                and params.get("item", {}).get("type") == "mcpToolCall"
            ):
                metadata = self.mcp_event(obj)
                if metadata["allowed"]:
                    if method == "item/completed" and self.on_mcp_outcome:
                        self.on_mcp_outcome(metadata, metadata["status"] == "completed")
                elif method == "item/started":
                    self.reject_mcp_turn(metadata, params)
            elif method == "item/tool/call":
                self.pending = obj
                self.turn_id = params["turnId"]
                if not isinstance(params.get("arguments"), dict):
                    raise ResearchError("Codex dynamic tool arguments must be an object.")
                return ProviderResponse(
                    kind="tool_call",
                    tool_name=params["tool"],
                    tool_args=params["arguments"],
                    tool_call_id=params["callId"],
                    model=self.model_name,
                )
            elif (
                method == "item/completed" and params.get("item", {}).get("type") == "agentMessage"
            ):
                item = params["item"]
                public_phase = item.get("phase") in {None, "commentary", "final_answer"}
                if public_phase and self.on_public and item.get("text"):
                    self.on_public(item["text"])
                if public_phase and item.get("phase") != "commentary":
                    final = item.get("text", "")
            elif method == "item/started" and params.get("item", {}).get("type") not in {
                "userMessage",
                "agentMessage",
                "dynamicToolCall",
                "reasoning",
            }:
                item = params.get("item", {})
                # Explicit projection only: never persist the event or item payload.
                diagnostic = {
                    "method": method,
                    "item_type": item.get("type"),
                    "provider": self.name,
                    "model": self.model_name,
                    "reasoning_effort": self.effort,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
                for key, value in (
                    ("item_id", item.get("id")),
                    ("request_id", obj.get("id", params.get("requestId"))),
                    ("event_sequence", obj.get("sequenceNumber", params.get("sequenceNumber"))),
                ):
                    if isinstance(value, (str, int)) and not isinstance(value, bool):
                        diagnostic[key] = value
                if self.on_diagnostic:
                    self.on_diagnostic(diagnostic)
                raise ResearchError(
                    "Native item rejected by research_standard: "
                    f"item_type={item.get('type')}; event={method}"
                )
            elif method == "turn/completed":
                if self.mcp_items:
                    raise ResearchError("MCP lifecycle ended with unfinished items.")
                if params["turn"]["status"] != "completed":
                    raise ResearchError("Codex turn failed or interrupted.")
                self.turn_id = None
                usage = TokenUsage(
                    prompt_tokens=max(
                        0,
                        self.usage.get("inputTokens", 0)
                        - self.reported_usage.get("inputTokens", 0),
                    ),
                    completion_tokens=max(
                        0,
                        self.usage.get("outputTokens", 0)
                        - self.reported_usage.get("outputTokens", 0),
                    ),
                )
                self.reported_usage = dict(self.usage)
                return ProviderResponse(
                    kind="message",
                    content=final,
                    model=self.model_name,
                    usage=usage,
                )
            elif "id" in obj and "method" in obj:
                self.rpc.send(
                    {
                        "id": obj["id"],
                        "error": {"code": -32601, "message": "Denied by research_standard"},
                    }
                )

    def mcp_event(self, obj: dict) -> dict:
        """Validate lifecycle and project identities only, never arguments or results."""
        method = obj.get("method")
        item = obj.get("params", {}).get("item", {})
        required = ("id", "server", "tool", "status")
        if "arguments" not in item or not all(
            isinstance(item.get(k), str) and item[k] for k in required
        ):
            raise ResearchError("Malformed MCP item: missing required identity/status.")
        ident = item["id"]
        identity = (item["server"], item["tool"])
        if method == "item/started":
            if item["status"] != "inProgress" or ident in self.mcp_items:
                raise ResearchError("Invalid MCP started lifecycle transition.")
            self.mcp_items[ident] = identity
        elif method == "item/completed":
            if (
                item["status"] not in {"completed", "failed"}
                or self.mcp_items.get(ident) != identity
            ):
                raise ResearchError("Invalid MCP completed lifecycle transition.")
            del self.mcp_items[ident]
        else:
            raise ResearchError("Invalid MCP event method.")
        metadata = {
            "method": method,
            "item_type": "mcpToolCall",
            "item_id": ident,
            "server": item["server"],
            "tool": item["tool"],
            "status": item["status"],
            "provider": self.name,
            "model": self.model_name,
            "reasoning_effort": self.effort,
            "timestamp": datetime.now(UTC).isoformat(),
            "protocol_item": "KNOWN_PROTOCOL_ITEM",
            "allowed": identity in self.allowed_mcp_tools,
            "action": "allow" if identity in self.allowed_mcp_tools else "recoverable_reject",
        }
        context = item.get("appContext")
        context = context if isinstance(context, dict) else {}
        for dest, value in (
            ("plugin_id", item.get("pluginId")),
            ("connector_id", context.get("connectorId")),
            ("app_name", context.get("appName")),
            ("action_name", context.get("actionName")),
            ("read_only_hint", item.get("readOnlyHint")),
        ):
            if isinstance(value, (str, bool)):
                metadata[dest] = value
        if self.on_diagnostic:
            self.on_diagnostic(metadata)
        return metadata

    def reject_mcp_turn(self, metadata: dict, params: dict) -> None:
        """Interrupt an unauthorized native turn, then let the existing runtime recover.

        Notifications cannot grant/deny an execution: launch configuration is the
        prevention boundary. Never pretend an item/started event is an approval RPC.
        """
        assert self.rpc is not None
        thread = params.get("threadId", self.thread_id)
        turn = params.get("turnId", self.turn_id)
        if not isinstance(thread, str) or not isinstance(turn, str):
            raise ResearchError("MCP rejection lacks thread/turn identity.")
        ended = False

        def observe(obj: dict) -> None:
            nonlocal ended
            if obj.get("method") == "item/completed":
                item = obj.get("params", {}).get("item", {})
                if item.get("type") == "mcpToolCall":
                    self.mcp_event(obj)
            elif obj.get("method") == "turn/completed":
                status = obj.get("params", {}).get("turn", {}).get("status")
                if status not in {"interrupted", "failed", "completed"}:
                    raise ResearchError("Invalid MCP interruption lifecycle.")
                ended = True

        try:
            self.rpc.call(
                "turn/interrupt", {"threadId": thread, "turnId": turn}, timeout=10, on_event=observe
            )
            deadline = min(self.deadline, time.monotonic() + 10)
            while not ended:
                observe(self.rpc.next(deadline, self.should_stop))
        except TimeoutError as exc:
            raise ResearchError(
                "MCP interruption did not complete within its protocol deadline."
            ) from exc
        # Interrupted turns can leave an item inProgress; cancellation closes it locally.
        self.mcp_items.clear()
        self.turn_id = None
        rejection = McpPolicyRejection(metadata)
        self.rejection_instruction = str(rejection)
        raise rejection

    def close(self) -> None:
        if self.rpc:
            if self.thread_id and self.turn_id:
                try:
                    self.rpc.call(
                        "turn/interrupt",
                        {"threadId": self.thread_id, "turnId": self.turn_id},
                        timeout=2,
                    )
                except (OSError, ResearchError, TimeoutError):
                    pass
            self.rpc.close()
            self.rpc = None
        if self.home:
            self.home.cleanup()
            self.home = None
