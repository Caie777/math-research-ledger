"""Read-only diagnostics and portable exports, derived from existing file stores."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

import yaml

from math_research import __version__
from math_research.agent.state import AgentRun
from math_research.app.workflows.actions import preflight_episode
from math_research.core.config import load_config
from math_research.core.errors import ResearchError
from math_research.core.process import hidden_process_kwargs, run_process
from math_research.ledger.archive import _verified_bytes
from math_research.ledger.episodes import Proposal, list_candidates, list_episodes
from math_research.ledger.handoff import current_research_state
from math_research.ledger.records import store
from math_research.ledger.state import KnowledgeStateResolver
from math_research.ledger.target import ResearchTarget
from math_research.retrieval.recall import ResearchRecall

RESEARCH_PROTOCOL = "freeze-v1"
MAX_PACK_BYTES = 512 * 1024 * 1024
_SECRET = re.compile(
    r"api[_-]?key|password|passwd|secret|credential|authorization|access[_-]?token|refresh[_-]?token|^token$",
    re.I,
)
_EXCLUDED = {
    ".codex",
    ".venv",
    ".venv-win",
    "node_modules",
    "__pycache__",
    ".cache",
    "sandbox",
    ".sandbox",
    "tmp",
    "temp",
    "index",
}


def _secrets(value: object) -> list[bytes]:
    found: list[bytes] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if _SECRET.search(str(key)) and isinstance(child, str) and child:
                found.append(child.encode())
            else:
                found.extend(_secrets(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_secrets(child))
    return found


def _redact(value: object, secrets: list[bytes]) -> object:
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if _SECRET.search(str(k)) and v else _redact(v, secrets)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v, secrets) for v in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret.decode(), "[REDACTED]")
        value = re.sub(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", value)
    return value


def _sanitize(raw: bytes, suffix: str, secrets: list[bytes]) -> tuple[bytes | None, bool]:
    try:
        text = raw.decode("utf-8")
    except UnicodeError:
        return (None, True) if any(s in raw for s in secrets) else (raw, False)
    if suffix in {".yaml", ".yml", ".json", ".jsonl"}:
        try:
            if suffix == ".jsonl":
                original = [json.loads(line) for line in text.splitlines() if line.strip()]
                cleaned = _redact(original, secrets)
                if cleaned != original:
                    assert isinstance(cleaned, list)
                    text = "\n".join(json.dumps(row, ensure_ascii=False) for row in cleaned) + "\n"
            elif suffix == ".json":
                original = json.loads(text)
                cleaned = _redact(original, secrets)
                if cleaned != original:
                    text = json.dumps(cleaned, ensure_ascii=False, indent=2)
            else:
                original = yaml.safe_load(text)
                cleaned = _redact(original, secrets)
                if cleaned != original:
                    text = yaml.safe_dump(cleaned, allow_unicode=True, sort_keys=False)
        except (ValueError, yaml.YAMLError):
            return None, True
    else:
        for secret in secrets:
            text = text.replace(secret.decode(), "[REDACTED]")
        text = re.sub(
            r"(?im)((?:api[_-]?key|password|secret|access[_-]?token|authorization)\s*[:=]\s*)[^\s,;]+",
            r"\1[REDACTED]",
            text,
        )
        text = re.sub(r"\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", text)
    result = text.encode()
    return result, result != raw


def _pack(
    files: dict[str, bytes],
    metadata: dict,
    required: list[str],
    directories: list[str] | None = None,
) -> bytes:
    if sum(map(len, files.values())) > MAX_PACK_BYTES:
        raise ResearchError("Export exceeds the 512 MiB limit; export a smaller handoff pack.")
    inventory = {
        name: {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        for name, raw in sorted(files.items())
    }
    manifest = {
        "schema": RESEARCH_PROTOCOL,
        "created_at": datetime.now(UTC).isoformat(),
        **metadata,
        "required_paths": required,
        "files": inventory,
    }
    files = {
        **files,
        "sha256_inventory.json": json.dumps(inventory, indent=2).encode(),
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
    }
    out = BytesIO()
    with ZipFile(out, "w", ZIP_DEFLATED) as archive:
        for directory in directories or []:
            archive.writestr(directory.rstrip("/") + "/", b"")
        for name, raw in sorted(files.items()):
            archive.writestr(name, raw)
    return out.getvalue()


def workspace_snapshot(ot_dir: Path) -> bytes:
    load_config(ot_dir / "config.yaml")
    config = yaml.safe_load((ot_dir / "config.yaml").read_text("utf-8"))
    secrets = _secrets(config) + [
        v.encode() for k, v in os.environ.items() if _SECRET.search(k) and v
    ]
    files: dict[str, bytes] = {}
    excluded: list[str] = []
    redacted: list[str] = []
    directories = [".math-research/"]
    for path in sorted(ot_dir.rglob("*")):
        relative = path.relative_to(ot_dir)
        name = ".math-research/" + relative.as_posix()
        if path.is_symlink() or not path.resolve().is_relative_to(ot_dir.resolve()):
            excluded.append(name)
            continue
        parts = set(relative.parts)
        persistent_run = (
            len(relative.parts) >= 3
            and relative.parts[0] == "research_runs"
            and relative.parts[2] in {"artifacts", "checkpoint"}
        )
        temporary_run = (
            len(relative.parts) >= 3
            and relative.parts[0] == "research_runs"
            and relative.parts[2] == "work"
        )
        if (
            not persistent_run
            and parts & _EXCLUDED
            or temporary_run
            or path.name.endswith(".lock")
            or path.name.lower() in {"auth.json", "credentials.json"}
            or path.name.lower().startswith(".env")
            or path.suffix in {".pem", ".key"}
        ):
            excluded.append(name)
            continue
        if path.is_dir():
            directories.append(name + "/")
            continue
        if not path.is_file():
            continue
        if (
            path.stat().st_size > MAX_PACK_BYTES
            or sum(map(len, files.values())) + path.stat().st_size > MAX_PACK_BYTES
        ):
            raise ResearchError("Snapshot exceeds 512 MiB; nothing was modified.")
        raw, changed = _sanitize(path.read_bytes(), path.suffix, secrets)
        if raw is None:
            excluded.append(name)
        else:
            files[name] = raw
            if changed:
                redacted.append(name)
    required = [".math-research/", ".math-research/config.yaml"]
    if (ot_dir / "problems").exists():
        required.append(".math-research/problems/")
    # Explicit project configuration allowlist; never copy arbitrary root dotfiles.
    for filename in ("pyproject.toml", "web/package.json", "web/package-lock.json"):
        path = ot_dir.parent / filename
        if path.is_file():
            raw, changed = _sanitize(path.read_bytes(), path.suffix, secrets)
            if raw is not None:
                files[filename] = raw
                if changed:
                    redacted.append(filename)
    files["environment.json"] = json.dumps(
        {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "research_protocol": RESEARCH_PROTOCOL,
            "math_research_version": __version__,
        },
        indent=2,
    ).encode()
    return _pack(
        files,
        {
            "kind": "workspace-snapshot-v1",
            "excluded": excluded,
            "redacted": redacted,
            "credential_policy": (
                "Credentials redacted/excluded; authentication must be configured separately."
            ),
        },
        required,
        directories,
    )


def verify_snapshot(raw: bytes) -> dict:
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate zip paths")
            if len(infos) > 100000 or sum(i.file_size for i in infos) > MAX_PACK_BYTES:
                raise ValueError("Snapshot exceeds verification limits")
            for info in infos:
                path = PurePosixPath(info.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in info.orig_filename
                    or ":" in info.filename
                    or (info.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise ValueError("Unsafe zip path")
            manifest = json.loads(archive.read("manifest.json"))
            if not isinstance(manifest, dict):
                raise ValueError("Manifest must be an object")
            if (
                manifest.get("schema") != RESEARCH_PROTOCOL
                or manifest.get("kind") != "workspace-snapshot-v1"
            ):
                raise ValueError("Unsupported snapshot manifest")
            inventory = manifest["files"]
            if not isinstance(inventory, dict) or not inventory:
                raise ValueError("Missing file inventory")
            if json.loads(archive.read("sha256_inventory.json")) != inventory:
                raise ValueError("Inventory differs from manifest")
            if not isinstance(manifest.get("required_paths"), list) or any(
                not isinstance(p, str) for p in manifest["required_paths"]
            ):
                raise ValueError("Invalid required structural paths")
            required = {
                ".math-research/",
                ".math-research/config.yaml",
                *manifest["required_paths"],
            }
            if not required.issubset(names):
                raise ValueError("Required structural paths missing")
            actual = {i.filename for i in infos if not i.is_dir()} - {
                "manifest.json",
                "sha256_inventory.json",
            }
            if actual != set(inventory):
                raise ValueError("Files differ from manifest")
            for name, entry in inventory.items():
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get("size"), int)
                    or not isinstance(entry.get("sha256"), str)
                ):
                    raise ValueError("Invalid SHA256 inventory entry")
                content = archive.read(name)
                if (
                    len(content) != entry["size"]
                    or hashlib.sha256(content).hexdigest() != entry["sha256"]
                ):
                    raise ValueError(f"SHA256 mismatch: {name}")
            return {"valid": True, "file_count": len(inventory), "kind": manifest["kind"]}
    except (BadZipFile, KeyError, ValueError, TypeError, OSError, RuntimeError) as exc:
        raise ResearchError(f"Snapshot verification failed: {exc}") from exc


def handoff_pack(ot_dir: Path, pid: str, tid: str) -> bytes:
    if not re.fullmatch(r"CLAIM-\d+", tid):
        raise ResearchError("Choose an existing Claim / Gap ID.")
    target = ResearchTarget(kind="claim", problem_id=pid, node_id=tid)
    state = current_research_state(ot_dir, target)
    files = {"current_research_state.md": state.markdown.encode()}
    missing: list[str] = []
    sources: list[str] = []
    relevant = ResearchRecall(ot_dir, pid).find_files(tid, limit=100).files
    index = [
        "# Object / source index",
        "",
        "Canonical / provisional labels are preserved; source material is not a theorem.",
    ]
    for resource in relevant:
        index.append(
            f"- {resource.artifact_id} [{resource.kind}; {resource.authority}; "
            f"{resource.state.research_state}; {resource.state.verification}] {resource.title}"
        )
        if resource.path:
            sources.append(resource.artifact_id)
    episodes = {e.episode_id: e for e in list_episodes(ot_dir, pid)}
    latest = state.latest_handoff_episode_id or next(
        (i for i in state.cold_episode_ids if i in episodes), None
    )
    if latest:
        files["latest_episode.md"] = _verified_bytes(ot_dir, episodes[latest])
        sources.append(latest)
    else:
        missing.append("latest relevant Episode / Handoff not recorded")
    states = KnowledgeStateResolver(ot_dir).resolve(pid)
    for candidate in list_candidates(ot_dir, pid, latest) if latest else []:
        item = states.get(candidate.candidate_id)
        if item:
            index.append(
                f"- {candidate.candidate_id} [{item.kind}; {item.authority}; "
                f"{item.research_state}; {item.verification}] {candidate.title}"
            )
    # The original pinned raw papers are scoped source context, never new math objects.
    from math_research.ledger.sources import read_source, source_papers

    for paper in source_papers(ot_dir, pid):
        try:
            _, path, content = read_source(ot_dir, pid, paper.id)
            files[f"sources/{paper.id}{path.suffix}"] = content
            sources.append(paper.id)
        except (OSError, ResearchError):
            missing.append(f"source {paper.id}: missing or SHA256 mismatch")
    # Include only public files referenced by the latest relevant run; never its OS work sandbox.
    runs = [
        AgentRun.model_validate_json(p.read_text("utf-8"))
        for p in (ot_dir / "research_runs").glob("*/run.json")
    ]
    matched = sorted(
        (r for r in runs if latest and r.request.target == target and r.episode_id == latest),
        key=lambda r: r.started_at,
        reverse=True,
    )
    if matched:
        run = matched[0]
        base = (ot_dir / "research_runs" / run.run_id).resolve()
        refs = re.findall(
            r"(?<![\w/])(?:artifacts|checkpoint)/[A-Za-z0-9_./-]+",
            files.get("latest_episode.md", b"").decode("utf-8"),
        )
        for relative in dict.fromkeys(
            [*run.artifacts, *refs, *([run.latest_checkpoint] if run.latest_checkpoint else [])]
        ):
            path = (base / relative).resolve()
            if (
                not base.is_relative_to(ot_dir.resolve())
                or not path.is_relative_to(base)
                or not relative.startswith(("artifacts/", "checkpoint/"))
                or not path.is_file()
            ):
                missing.append(f"{run.run_id}/{relative}")
            else:
                if path.stat().st_size > MAX_PACK_BYTES:
                    raise ResearchError("Handoff artifact exceeds the 512 MiB export limit.")
                files[f"artifacts/{run.run_id}/{relative}"] = path.read_bytes()
    files["object_index.md"] = ("\n".join(index) + "\n").encode()
    files["README.md"] = (
        f"# {tid} research handoff\n\nTarget status: {state.research_status}\n\n"
        "Canonical != provisional; model relation confirmation != Human Accept "
        "!= theorem verification.\n"
        "Deterministic assembly of public state; no model summary. "
        "Full recorded state is in current_research_state.md.\n\n"
        "## Latest obstacles\n"
        + "\n".join(state.active_obstacles or ["Not recorded"])
        + "\n\n## Latest worthwhile directions\n"
        + "\n".join(state.next_directions or ["Not recorded"])
        + "\n\n## Included sources\n"
        + "\n".join(dict.fromkeys(sources))
        + "\n\n## Missing\n"
        + "\n".join(missing or ["None recorded"])
        + "\n"
    ).encode()
    config = yaml.safe_load((ot_dir / "config.yaml").read_text("utf-8"))
    secrets = _secrets(config) + [
        v.encode() for k, v in os.environ.items() if _SECRET.search(k) and v
    ]
    redacted = []
    for name in list(files):
        clean, changed = _sanitize(files[name], Path(name).suffix, secrets)
        if clean is None:
            missing.append(f"{name} excluded: sensitive/unreadable structured content")
            del files[name]
        else:
            files[name] = clean
            if changed:
                redacted.append(name)
    return _pack(
        files,
        {
            "kind": "research-handoff-v1",
            "problem_id": pid,
            "target_id": tid,
            "target_status": state.research_status,
            "latest_episode_id": latest,
            "missing": missing,
            "redacted": redacted,
        },
        ["README.md", "current_research_state.md", "object_index.md"],
    )


def probe_codex() -> dict[str, tuple[str, str]]:
    """Initialize app-server and probe only command/exec; never thread/start or turn/start."""
    binary = shutil.which("codex")
    result = {
        k: ("warning", "Codex unavailable; install/login locally when research is needed.")
        for k in ("codex_cli", "codex_app_server", "python_sandbox")
    }
    if not binary:
        return result
    from math_research.agent.codex import CodexRPC
    from math_research.agent.transport import _codex_env

    try:
        version = run_process(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
            **hidden_process_kwargs(),
        )
        result["codex_cli"] = ("ok", version.stdout.strip()[:100])
    except (OSError, subprocess.SubprocessError):
        return result
    with tempfile.TemporaryDirectory(prefix="research-health-") as directory:
        root = Path(directory)
        work = root / "work"
        work.mkdir()
        denied = root / "denied.txt"
        denied.write_text("unchanged", encoding="utf-8")
        overrides = [
            'default_permissions="health_compute"',
            "",
            "permissions.health_compute.network.enabled=false",
            'shell_environment_policy={inherit="none"}',
        ]
        # TOML inline table uses key=value rather than JSON key:value.
        overrides[1] = (
            "permissions.health_compute.filesystem={"
            + ",".join(
                json.dumps(k) + "=" + json.dumps(v)
                for k, v in {
                    ":root": "read",
                    str(work): "write",
                    str(Path.home() / ".codex"): "deny",
                }.items()
            )
            + "}"
        )
        if os.name == "nt":
            overrides.append('windows.sandbox="elevated"')
        rpc = None
        try:
            rpc = CodexRPC(
                work, env=_codex_env(), overrides=overrides, deadline=time.monotonic() + 15
            )
            result["codex_app_server"] = ("ok", "initialize succeeded; no model turn started")
            code = (
                'from pathlib import Path; Path("allowed.txt").write_text("ok");\ntry: Path('
                + repr(str(denied))
                + ').write_text("BAD")\nexcept PermissionError: pass\n'
            )
            rpc.call(
                "command/exec",
                {
                    "command": [sys.executable, "-B", "-c", code],
                    "cwd": str(work),
                    "permissionProfile": "health_compute",
                    "env": _codex_env(),
                    "timeoutMs": 10000,
                },
                timeout=10,
            )
            if (work / "allowed.txt").read_text("utf-8") == "ok" and denied.read_text(
                "utf-8"
            ) == "unchanged":
                result["python_sandbox"] = (
                    "ok",
                    "Allowed/denied temporary-file probe passed; network disabled",
                )
        except Exception:
            result["python_sandbox"] = (
                "warning",
                "OS sandbox unavailable/unverified; research computation will fail closed. "
                "Check local Codex sandbox setup.",
            )
        finally:
            if rpc:
                rpc.close()
    return result


def system_health(ot_dir: Path) -> dict:
    checks = []

    def check(name: str, fn: Callable[[], object]) -> None:
        try:
            value = fn()
            checks.append({"name": name, "status": "ok", "detail": str(value)})
        except Exception:
            checks.append(
                {
                    "name": name,
                    "status": "failure",
                    "detail": (
                        f"Cannot validate {name}. Check workspace access / "
                        ".math-research/config.yaml and stored records; no repair was performed."
                    ),
                }
            )

    checks.append({"name": "backend", "status": "ok", "detail": "Backend reachable"})
    check("workspace_root", lambda: str(ot_dir.parent.resolve()))
    check(
        "workspace",
        lambda: (
            f"{ot_dir.resolve()} readable/writable"
            if ot_dir.is_dir() and os.access(ot_dir, os.R_OK | os.W_OK)
            else (_ for _ in ()).throw(OSError())
        ),
    )
    check("config", lambda: load_config(ot_dir / "config.yaml") and "Config parsed")

    def archive_check() -> str:
        root = ot_dir / "research_archive"
        if root.exists():
            list(root.iterdir())  # Inaccessible/malformed archive is not an empty archive.
        episodes = list_episodes(ot_dir)
        for episode in episodes:
            _verified_bytes(ot_dir, episode)
        return f"{len(episodes)} archived sources verified"

    check("archive", archive_check)
    dossiers = []
    try:
        dossiers = store.list_dossiers(ot_dir)
    except Exception:
        checks.append(
            {
                "name": "problem_store",
                "status": "failure",
                "detail": "Cannot parse Problem metadata",
            }
        )

    def candidate_check() -> int:
        count = 0
        for dossier in dossiers:
            path = store.dossier_dir(ot_dir, dossier.id) / "archive/episodes/proposals.jsonl"
            if path.exists():
                for line in path.read_text("utf-8").splitlines():
                    if line.strip():
                        Proposal.model_validate_json(line)
                        count += 1
        return count

    check("candidate_store", candidate_check)
    from math_research.app.maintenance.integrity import canonical_integrity

    check("canonical_integrity", lambda: canonical_integrity(ot_dir))
    check(
        "resolver", lambda: sum(len(KnowledgeStateResolver(ot_dir).resolve(d.id)) for d in dossiers)
    )
    check(
        "research_runs",
        lambda: len(
            [
                AgentRun.model_validate_json(p.read_text("utf-8"))
                for p in (ot_dir / "research_runs").glob("*/run.json")
            ]
        ),
    )

    # Existing parser self-check in a temporary workspace, never the real ledger.
    def parser_check() -> str:
        from math_research.core.workspace import init_workspace, workspace_dir

        with tempfile.TemporaryDirectory(prefix="research-parser-health-") as directory:
            root = Path(directory)
            init_workspace(root)
            temporary = workspace_dir(root)
            problem = store.create_dossier(temporary, "Parser self-check")
            data = preflight_episode(
                temporary,
                problem.id,
                "check.md",
                b"## RESULT-1\n\n**Statement**\n\nSynthetic parser self-check\n",
            )
            if data["parse_summary"] != {"claim": 1}:
                raise ValueError("Parser self-check mismatch")
        return "Existing deterministic parser self-check passed"

    check("episode_parser", parser_check)
    for name, (status, detail) in probe_codex().items():
        checks.append({"name": name, "status": status, "detail": detail})
    for name in ("gap", "Singular"):
        binary = shutil.which(name)
        checks.append(
            {
                "name": name.lower(),
                "status": "ok" if binary else "warning",
                "detail": binary or "Optional tool unavailable",
            }
        )
    checks.append({"name": "protocol", "status": "ok", "detail": RESEARCH_PROTOCOL})
    return {
        "protocol": RESEARCH_PROTOCOL,
        "status": "failure"
        if any(c["status"] == "failure" for c in checks)
        else "warning"
        if any(c["status"] == "warning" for c in checks)
        else "ok",
        "checks": checks,
    }
