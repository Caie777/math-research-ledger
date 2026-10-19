"""Small research_standard registry over existing memory, literature and permissions."""

from __future__ import annotations

import getpass
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from math_research.agent.codex import CodexRPC, CommandExecutionTimeout
from math_research.agent.egress import EgressGuard
from math_research.agent.literature.arxiv import ArxivSource
from math_research.agent.literature.base import SourceError
from math_research.agent.literature.openalex import OpenAlexSource
from math_research.agent.permissions.policy import evaluate_write
from math_research.agent.policy import (
    COMPLETION_STATES,
    CONTINUE_AFTER_MILESTONE,
    CompletionState,
    assess_finalization,
)
from math_research.agent.state import AgentRequest
from math_research.agent.tooling.base import Tool, ToolCall, ToolResult, validate_tool_args
from math_research.agent.tooling.registry import ToolRegistry
from math_research.agent.transport import _codex_env
from math_research.core.atomicio import atomic_write_text
from math_research.core.errors import RecoverableToolError, ResearchError
from math_research.core.process import hidden_process_kwargs, run_process
from math_research.memory.assets import (
    AssetNotFoundError,
    AssetNotRetainedError,
    find_research_assets,
    read_research_asset,
)
from math_research.memory.decomposition import has_numbered_headings
from math_research.memory.handoff import ensure_handoff
from math_research.memory.records.write_boundary import automated_research, execution_env
from math_research.retrieval.context import ResearchContextBuilder
from math_research.retrieval.recall import MemoryObjectNotFound, ResearchRecall

PREVIEW_CHARS = 4000
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
DEFAULT_PYTHON_TIMEOUT = 120
MAX_COMPUTE_TIMEOUT = 300


def run_path(run_dir: Path, value: str, *, area: str | None = None) -> Path:
    base = (run_dir / area if area else run_dir).resolve()
    relative = Path(value)
    path = (base / relative).resolve()
    if relative.is_absolute() or ".." in relative.parts or not path.is_relative_to(base):
        raise ResearchError("Path outside run workspace.")
    if not evaluate_write(path, "trusted").allowed:
        raise ResearchError("Run file permission denied.")
    return path


class ResearchTool(Tool):
    def __init__(self, name: str, description: str, properties: dict, required: list[str], handler):  # noqa: ANN001
        self.name, self.description, self.handler = name, description, handler
        self.input_schema: dict = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    @automated_research
    def run(self, call: ToolCall) -> ToolResult:
        error = validate_tool_args(self.input_schema, call.args)
        if error or set(call.args) - set(self.input_schema["properties"]):
            return self.fail(call, error or "Unknown argument.", error_class="ValueError")
        try:
            data = self.handler(**call.args)
            return self.ok(call, json.dumps(data, ensure_ascii=False, default=str))
        except RecoverableToolError as exc:
            return self.fail(call, str(exc)[:PREVIEW_CHARS], **exc.metadata)
        except SourceError as exc:
            return self.fail(
                call,
                str(exc)[:PREVIEW_CHARS],
                error_class=type(exc).__name__,
                http_status=exc.status,
                attempts=exc.attempts,
            )
        except TimeoutError as exc:
            return self.fail(call, str(exc)[:PREVIEW_CHARS], error_class=type(exc).__name__)
        except (ResearchError, OSError, ValueError) as exc:
            return self.fail(
                call, str(exc)[:PREVIEW_CHARS], error_class=type(exc).__name__, fatal=True
            )


class ResearchTools:
    def __init__(self, ot_dir: Path, run_dir: Path, request: AgentRequest):
        self.ot_dir, self.run_dir, self.request = ot_dir, run_dir, request
        self.registry = ToolRegistry()
        self.availability = {
            "gap": shutil.which("gap") or "unavailable",
            "singular": shutil.which("Singular") or "unavailable",
            "python": "Codex OS sandbox (checked before execution)"
            if shutil.which("codex")
            else "unavailable",
        }
        self.guard = EgressGuard(
            "trusted",
            confirm=lambda host: host in {ArxivSource.host, OpenAlexSource.host, "arxiv.org"},
            daily_request_budget=request.budget.max_web_calls,
            ledger_path=run_dir / "egress.json",
        )
        self.emitted: str | None = None
        self.deadline: float | None = None
        self._register()

    def _register(self) -> None:
        string = {"type": "string"}
        integer = {"type": "integer"}
        specs: list[tuple[str, str, dict, list[str], Any]] = [
            (
                "find_related",
                "Read scoped related research; authority and provenance retained.",
                {"query": string},
                [],
                self.related,
            ),
            (
                "check_history",
                "Read current scoped history, including rejected/stale warnings.",
                {"query": string},
                [],
                self.history,
            ),
            (
                "build_context",
                "Rebuild scoped ContextBuilder bundle; provisional is explicitly labeled.",
                {},
                [],
                self.context,
            ),
            (
                "read_object",
                "Read scoped original by ID/kind (episode or dossier:episode for archive sources), "
                "bounded excerpt and authority. Valid absent objects return recoverable NOT_FOUND; "
                "choose another retrieval route. Permission/storage failures remain fatal.",
                {"object_id": string, "kind": string, "offset": integer, "length": integer},
                ["object_id", "kind"],
                self.object,
            ),
            (
                "python",
                "Run Python code in isolated work; "
                "managed paths and network blocked by OS sandbox. "
                "Execution timeout defaults to 120 seconds; request at most 300 seconds.",
                {
                    "code": string,
                    "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
                },
                ["code"],
                self.python,
            ),
            (
                "search_arxiv",
                "Search arXiv metadata; selected PDF fetch is a separate request.",
                {"query": string},
                ["query"],
                self.arxiv,
            ),
            (
                "search_web",
                "Search scholarly web metadata via existing OpenAlex connector.",
                {"query": string},
                ["query"],
                self.web,
            ),
            (
                "fetch_paper",
                "Fetch selected public arXiv PDF to run artifact; at most 16 MiB.",
                {"arxiv_id": string},
                ["arxiv_id"],
                self.fetch,
            ),
            (
                "read_paper",
                "Read a selected PDF page (existing pdf_text parser), bounded preview.",
                {"path": string, "page": integer},
                ["path"],
                self.paper,
            ),
            (
                "read_artifact",
                "Read selected run artifact slice; no arbitrary host paths.",
                {"path": string, "offset": integer, "length": integer},
                ["path"],
                self.read,
            ),
            (
                "read_research_asset",
                "Read retained historical execution bytes by ASSET ID from manifests. "
                "Hash match is byte identity, never mathematical verification or Human Accept. "
                "Discover IDs with list_research_assets or read_object. No filesystem paths.",
                {"asset_id": string, "offset": integer, "length": integer},
                ["asset_id"],
                self.research_asset,
            ),
            (
                "list_research_assets",
                "Discover retained execution ASSET IDs linked to a scoped Episode, "
                "candidate, proof or evidence ID. Metadata only; never inject script bodies.",
                {"object_id": string, "offset": integer, "limit": integer},
                ["object_id"],
                self.research_assets,
            ),
            (
                "save_notes",
                "保存本次 run 的公开研究笔记与阶段成果；保存后继续研究，不结束 Explore Session。",
                {"text": string},
                ["text"],
                self.save,
            ),
            (
                "save_experiment_result",
                "保存本次 run 的公开实验与阶段成果；保存后继续研究，不结束 Explore Session。",
                {"result": {"type": "object"}},
                ["result"],
                self.experiment,
            ),
            (
                "emit_research_episode",
                "这是本次 Explore Session 的最终交接输出，不应仅因中间 RESULT 而调用。"
                "主目标未解决且仍有明确值得执行的 next_action 时，会保存 milestone 并要求继续。"
                "completion_state 说明结束依据；TARGET_RESOLVED 是公开报告，不授予数学权威。"
                "最终输出只进入 pending staging，不执行 Human Accept。",
                {
                    "markdown": string,
                    "completion_state": {"type": "string", "enum": list(COMPLETION_STATES)},
                    "next_action": string,
                },
                ["markdown"],
                self.emit,
            ),
        ]
        for name, desc, props, required, handler in specs:
            self.registry.register(ResearchTool(name, desc, props, required, handler))
        for name in ("gap", "singular"):
            if self.availability[name] != "unavailable":
                self.registry.register(
                    ResearchTool(
                        name,
                        "Sandboxed local CAS; no installation.",
                        {"code": string},
                        ["code"],
                        lambda code, n=name: self.compute(n, code),
                    )
                )

    def bounded(self, data: Any, prefix: str = "result") -> dict:
        text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
        path = self.artifact(prefix, text)
        return {
            "artifact": path,
            "chars": len(text),
            "truncated": len(text) > PREVIEW_CHARS,
            "preview": text[:PREVIEW_CHARS],
        }

    def artifact(self, prefix: str, text: str) -> str:
        folder = self.run_dir / "artifacts"
        folder.mkdir(exist_ok=True)
        index = len(list(folder.iterdir())) + 1
        path = run_path(self.run_dir, f"artifacts/{index:04d}-{prefix}.txt")
        atomic_write_text(path, text[:MAX_ARTIFACT_BYTES], encoding="utf-8")
        return path.relative_to(self.run_dir).as_posix()

    def related(self, query: str = "") -> dict:
        result = ResearchRecall(self.ot_dir, self.request.target.problem_id).find_files(
            self.request.target.node_id, query=query, limit=15
        )
        if not self.request.include_provisional:
            result.files = [f for f in result.files if f.authority == "CANONICAL"]
        return self.bounded(result.model_dump(mode="json"), "memory")

    def history(self, query: str = "") -> dict:
        result = ResearchRecall(self.ot_dir, self.request.target.problem_id).check_history(
            self.request.target.node_id, query=query, limit=15
        )
        if not self.request.include_provisional:
            for name in (
                "canonical_matches",
                "open_matches",
                "failed_routes",
                "counterexamples",
                "proofs",
                "source_files",
                "soft_overlaps",
            ):
                setattr(
                    result, name, [f for f in getattr(result, name) if f.authority == "CANONICAL"]
                )
        return self.bounded(result.model_dump(mode="json"), "history")

    def context(self) -> dict:
        result = ResearchContextBuilder(self.ot_dir).build(
            self.request.target,
            token_budget=self.request.context_tokens,
            include_provisional=self.request.include_provisional,
            thread_id=self.request.thread_id,
            explore=True,
        )
        return self.bounded(result.model_dump(mode="json"), "context")

    def object(
        self, object_id: str, kind: str, offset: int = 0, length: int = PREVIEW_CHARS
    ) -> dict:
        # Model input is an opaque ID, never a path. Reject unsafe/malformed input
        # before it can be mistaken for an ordinary scoped retrieval miss.
        if len(object_id) > 256 or not re.fullmatch(
            r"[A-Z][A-Z0-9_]*(?:-[A-Za-z0-9_]+)+", object_id
        ):
            raise ResearchError("Invalid memory object ID; filesystem paths are not accepted.")
        if len(kind) > 128 or not re.fullmatch(r"[a-z][a-z0-9_]*(?::[a-z][a-z0-9_]*)?", kind):
            raise ResearchError("Invalid memory object kind.")
        resolved_kind = "dossier:episode" if kind == "episode" else kind
        try:
            meta, raw = ResearchRecall(
                self.ot_dir, self.request.target.problem_id
            ).read_original_file(
                object_id,
                resolved_kind,
                # Existing fallback admits only Problem-independent archive
                # sources; it does not admit objects owned by another Problem.
                cross_problem=resolved_kind == "dossier:episode",
            )
        except MemoryObjectNotFound as exc:
            return {
                "status": "NOT_FOUND",
                "recoverable": True,
                "object_id": object_id,
                "kind": kind,
                "problem_id": self.request.target.problem_id,
                "reason": str(exc),
            }
        if not self.request.include_provisional and meta.authority != "CANONICAL":
            raise ResearchError("Provisional memory requires include_provisional=true.")
        text = raw.decode(
            "utf-8", errors="strict" if resolved_kind == "dossier:episode" else "replace"
        )
        return {
            "metadata": meta.model_dump(mode="json"),
            "offset": max(0, offset),
            "preview": text[max(0, offset) : max(0, offset) + min(max(1, length), PREVIEW_CHARS)],
            "chars": len(text),
            "research_assets": self.research_assets(object_id),
        }

    def research_assets(self, object_id: str, offset: int = 0, limit: int = 12) -> dict:
        if len(object_id) > 256 or not re.fullmatch(
            r"[A-Z][A-Z0-9_]*(?:-[A-Za-z0-9_]+)+", object_id
        ):
            raise ResearchError("Invalid memory object ID; paths are not accepted.")
        refs = find_research_assets(self.ot_dir, self.request.target.problem_id, object_id)
        offset, limit = max(0, offset), min(20, max(1, limit))
        return {
            "assets": [ref.model_dump(mode="json") for ref in refs[offset : offset + limit]],
            "total": len(refs),
            "offset": offset,
            "truncated": offset + limit < len(refs),
        }

    def research_asset(self, asset_id: str, offset: int = 0, length: int = PREVIEW_CHARS) -> dict:
        try:
            return read_research_asset(
                self.ot_dir, self.request.target.problem_id, asset_id, offset=offset, length=length
            )
        except (AssetNotFoundError, AssetNotRetainedError) as exc:
            return {"status": "NOT_FOUND", "recoverable": True, "reason": str(exc)}

    def python(self, code: str, timeout_seconds: int = DEFAULT_PYTHON_TIMEOUT) -> dict:
        if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= MAX_COMPUTE_TIMEOUT:
            raise RecoverableToolError("timeout_seconds must be an integer from 1 to 300.")
        return self.compute("python", code, timeout_seconds=timeout_seconds)

    def compute(self, language: str, code: str, *, timeout_seconds: int = 30) -> dict:
        if not code.strip() or len(code.encode()) > 200000:
            raise ResearchError("Script must contain 1–200000 bytes.")
        work = (self.run_dir / "work").resolve()
        if os.name == "nt":
            # Files created by Codex's low-privilege Windows account must remain
            # readable by the research workspace owner. Grant inheritance only inside work.
            acl = run_process(
                ["icacls", str(work), "/grant", f"{getpass.getuser()}:(OI)(CI)R"],
                capture_output=True,
                timeout=5,
                check=False,
                **hidden_process_kwargs(),
            )
            if acl.returncode:
                raise ResearchError("Cannot retain owner access to sandbox artifacts.")
        suffix = {"python": "py", "gap": "g", "singular": "sing"}[language]
        script = run_path(
            self.run_dir,
            f"script-{len(list(work.iterdir()))}.{suffix}",
            area="work",
        )
        script.write_text(code, encoding="utf-8")
        binary = sys.executable if language == "python" else self.availability[language]
        if binary == "unavailable":
            return {"availability": "unavailable"}
        files = {":root": "read", str(work): "write", str(Path.home() / ".codex"): "deny"}
        table = ",".join(json.dumps(k) + "=" + json.dumps(v) for k, v in files.items())
        overrides = [
            'default_permissions="research_compute"',
            f"permissions.research_compute.filesystem={{{table}}}",
            "permissions.research_compute.network.enabled=false",
            'shell_environment_policy={inherit="none"}',
        ]
        if os.name == "nt":
            overrides.append('windows.sandbox="elevated"')
        rpc = CodexRPC(work, env=_codex_env(), overrides=overrides, deadline=self.deadline)
        try:
            # Verify both sides with sacrificial files; never probe mathematical record writes.
            sentinel = self.run_dir / ".sandbox-denied"
            sentinel.write_text("unchanged", encoding="utf-8")
            probe = (
                'from pathlib import Path; Path(".sandbox-ok").write_text("ok");\ntry: Path('
                + repr(str(sentinel))
                + ').write_text("BAD")\nexcept PermissionError: pass\n'
            )
            try:
                probe_result = rpc.call(
                    "command/exec",
                    {
                        "command": [sys.executable, "-B", "-c", probe],
                        "cwd": str(work),
                        "permissionProfile": "research_compute",
                        "env": execution_env(_codex_env()),
                        "timeoutMs": 10000,
                    },
                )
            except (CommandExecutionTimeout, TimeoutError) as exc:
                raise ResearchError(
                    "OS sandbox validation timed out; refusing computation."
                ) from exc
            if probe_result.get("exitCode") != 0:
                raise ResearchError("OS sandbox validation command failed; refusing computation.")
            if not (work / ".sandbox-ok").is_file() or sentinel.read_text("utf-8") != "unchanged":
                raise ResearchError("OS sandbox validation failed; refusing computation.")
            output = run_path(self.run_dir, f"artifacts/{script.stem}-output.txt")
            raw_output = run_path(self.run_dir, f"{script.stem}-output.txt", area="work")
            raw_output.write_bytes(b"")
            stderr = run_path(self.run_dir, f"{script.stem}-stderr.txt", area="work")
            stderr.write_bytes(b"")

            def observe() -> None:
                if any(p.stat().st_size > MAX_ARTIFACT_BYTES for p in (raw_output, stderr)):
                    raise ResearchError("Computation output exceeded artifact limit; terminated.")

            argv = (
                [binary, "-B", str(script)] if language == "python" else [binary, "-q", str(script)]
            )
            # Windows sandbox cannot stream command/exec. Capture inside the sandbox
            # so full stdout is preserved while RPC/model only sees bounded metadata.
            wrapper = (
                "import subprocess,sys,os; "
                "from math_research.core.process import hidden_process_kwargs, run_process; "
                f"handle=open({str(raw_output)!r},'wb'); "
                f"errors=open({str(stderr)!r},'wb'); "
                f"result=run_process({argv!r},stdout=handle,stderr=errors,"
                "env=dict(os.environ),**hidden_process_kwargs()); "
                "handle.close(); errors.close(); sys.exit(result.returncode)"
            )
            remaining = self.deadline - time.monotonic() if self.deadline else timeout_seconds
            if remaining <= 0:
                raise TimeoutError("Research computation budget exhausted.")
            effective_timeout = min(timeout_seconds, MAX_COMPUTE_TIMEOUT, remaining)
            try:
                result = rpc.call(
                    "command/exec",
                    {
                        "command": [sys.executable, "-B", "-c", wrapper],
                        "cwd": str(work),
                        "permissionProfile": "research_compute",
                        "env": execution_env(_codex_env()),
                        "timeoutMs": max(1, int(1000 * effective_timeout)),
                    },
                    timeout=effective_timeout + 5,
                    on_tick=observe,
                )
            except (CommandExecutionTimeout, TimeoutError) as exc:
                raise RecoverableToolError(
                    f"{language} execution timed out after {effective_timeout:g} seconds. "
                    "Reduce the computation, optimize the script, split the search, "
                    "or request a larger permitted timeout. No automatic replay.",
                    error="execution_timeout",
                    error_class="ExecutionTimeout",
                    timeout_seconds=effective_timeout,
                ) from exc
            if type(result.get("exitCode")) is not int:
                raise ResearchError("Invalid sandbox execution result: missing integer exitCode.")
            observe()
            shutil.copyfile(raw_output, output)
            total = output.stat().st_size
            if result.get("exitCode") != 0:
                with stderr.open("rb") as handle:
                    handle.seek(max(0, stderr.stat().st_size - 2000))
                    diagnostic = handle.read(2000).decode("utf-8", errors="replace")
                classes = re.findall(r"^([A-Za-z_][\w.]*(?:Error|Exception)):", diagnostic, re.M)
                raise RecoverableToolError(
                    f"Computation exit {result.get('exitCode')}; output {output.name}\n"
                    f"stderr (bounded tail):\n{diagnostic}",
                    error_class=classes[-1] if classes else "SubprocessError",
                    exit_code=result.get("exitCode"),
                )
            return {
                "exit_code": result["exitCode"],
                "artifact": output.relative_to(self.run_dir).as_posix(),
                "bytes": total,
                "truncated": total > PREVIEW_CHARS,
                "preview": output.read_bytes()[:PREVIEW_CHARS].decode("utf-8", errors="replace"),
            }
        finally:
            rpc.close()

    def _search(self, source, query: str) -> dict:  # noqa: ANN001
        if not query.strip() or len(query) > 1000:
            raise ResearchError("Query must contain 1–1000 characters.")
        self.guard.authorize(source.host)
        records = source.search(query, limit=5)
        return self.bounded(
            {
                "query": query,
                "results": [
                    {
                        "title": r.title[:300],
                        "source": r.source,
                        "date": r.year,
                        "url": r.url,
                        "snippet": (r.abstract or "")[:500],
                        "arxiv_id": r.arxiv_id,
                    }
                    for r in records[:5]
                ],
            },
            "literature",
        )

    def arxiv(self, query: str) -> dict:
        return self._search(ArxivSource(), query)

    def web(self, query: str) -> dict:
        return self._search(OpenAlexSource(), query)

    def fetch(self, arxiv_id: str) -> dict:
        import re
        import urllib.request

        from math_research.agent.literature.base import USER_AGENT

        if not re.fullmatch(r"(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?", arxiv_id):
            raise ResearchError("Invalid arXiv identifier.")
        url = f"https://arxiv.org/pdf/{arxiv_id}"
        self.guard.authorize("arxiv.org")
        path = run_path(self.run_dir, f"artifacts/paper-{arxiv_id.replace('/', '-')}.pdf")
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.geturl().split("/")[2] != "arxiv.org":
                raise ResearchError("Paper redirect outside allowed source.")
            raw = response.read(MAX_ARTIFACT_BYTES + 1)
        if len(raw) > MAX_ARTIFACT_BYTES or not raw.startswith(b"%PDF"):
            raise ResearchError("PDF missing or exceeds 16 MiB.")
        path.write_bytes(raw)
        return {
            "artifact": path.relative_to(self.run_dir).as_posix(),
            "bytes": len(raw),
            "source": url,
        }

    def paper(self, path: str, page: int = 1) -> dict:
        from pypdf import PdfReader

        selected = run_path(self.run_dir, path)
        reader = PdfReader(selected)
        if not 1 <= page <= len(reader.pages):
            raise ResearchError("Page outside PDF.")
        # Reuse existing parser through a one-page document, never context-fill the full PDF.
        from math_research.memory.source_reader import parse_structure

        text = reader.pages[page - 1].extract_text() or ""
        structure = parse_structure([text])
        return self.bounded(
            {
                "page": page,
                "page_count": len(reader.pages),
                "text": text,
                "structure": structure.model_dump(mode="json"),
            },
            "paper-page",
        )

    def read(self, path: str, offset: int = 0, length: int = PREVIEW_CHARS) -> dict:
        selected = run_path(self.run_dir, path)
        # Internal credentials/session/logs are never exposed as artifact reads.
        if selected.relative_to(self.run_dir).parts[0] not in {"artifacts", "work", "checkpoint"}:
            raise ResearchError("Only research artifacts may be read.")
        with selected.open("rb") as handle:
            handle.seek(max(0, offset))
            raw = handle.read(min(max(1, length), PREVIEW_CHARS))
        return {
            "path": path,
            "offset": max(0, offset),
            "bytes": selected.stat().st_size,
            "preview": raw.decode("utf-8", errors="replace"),
        }

    def save(self, text: str) -> dict:
        return self.bounded(text, "notes")

    def experiment(self, result: dict) -> dict:
        return self.bounded(result, "experiment")

    def emit(
        self,
        markdown: str,
        completion_state: CompletionState | None = None,
        next_action: str | None = None,
    ) -> dict:
        if not has_numbered_headings(markdown) or len(markdown.encode()) > 200000:
            raise ResearchError(
                "Checkpoint must use Episode V4 numbered object headings, at most 200000 bytes."
            )
        decision = assess_finalization(
            self.ot_dir,
            self.request.target,
            markdown,
            completion_state=completion_state,
            next_action=next_action,
        )
        if decision.continue_research:
            return {
                **self.bounded(markdown, "milestone"),
                "status": "MILESTONE_SAVED",
                "session_completed": False,
                "reason": decision.reason,
                "next_action": decision.next_action,
                "instruction": CONTINUE_AFTER_MILESTONE,
                "authority": "PROVISIONAL",
            }
        markdown = ensure_handoff(
            markdown, self.request.target.node_id, "COMPLETED", completion_state=completion_state
        )
        self.emitted = markdown
        path = run_path(self.run_dir, "checkpoint/episode.md")
        atomic_write_text(path, markdown, encoding="utf-8")
        return {
            "checkpoint": "checkpoint/episode.md",
            "authority": "PROVISIONAL",
            "review": "PENDING",
            "status": "FINAL_EPISODE",
            "session_completed": True,
        }
