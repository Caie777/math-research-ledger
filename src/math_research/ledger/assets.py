"""Retained execution files, addressed by run/path/content, never mathematical truth.

The manifest is the only cross-run registry. Building it is read-only; publishing
is explicit. A matching SHA-256 identifies bytes, not correct code, a correct
output, a proof, general verification, or Human Accept.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError

MAX_ASSET_PREVIEW = 4000
INTEGRITY_NOTE = "Byte identity only; not mathematical verification or Human Accept."
_RUN = re.compile(r"AGENT-[0-9A-F]{16}")
_ASSET = re.compile(r"ASSET-[0-9A-F]{16}")
_AREAS = {"work", "artifacts", "checkpoint"}
_SCRIPTS = {".py": "python", ".g": "gap", ".sing": "singular"}
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {
    f"{prefix}{i}" for prefix in ("COM", "LPT") for i in range(1, 10)
}
_PATH = re.compile(
    r"(?<![\w./\\:%-])(?:work|artifacts|checkpoint)/[A-Za-z0-9_./-]+"
    r"(?![\w/\\:%?=-])"
)


class AssetIntegrityError(ResearchError):
    """A pinned file/manifest no longer has the recorded identity; never rebaseline."""


class AssetNotFoundError(ResearchError):
    """A missing file or an ID absent from the manifest registry."""


class AssetNotRetainedError(ResearchError):
    """Scratch files are not exposed through the cross-run reader."""


def validate_asset_path(value: str) -> str:
    """Require a canonical portable run-relative path, including on POSIX hosts."""
    windows = PureWindowsPath(value)
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 512
        or windows.drive
        or windows.root
        or path.is_absolute()
        or path.as_posix() != value
        or len(path.parts) < 2
        or path.parts[0] not in _AREAS
        or any(part in {".", ".."} or part.endswith((".", " ")) for part in path.parts)
        or any(ord(c) < 32 or c in '\\:<>"|?*' for c in value)
        or any(part.split(".")[0].upper() in _RESERVED for part in path.parts)
    ):
        raise ValueError("Asset path must be within run work/artifacts/checkpoint.")
    return value


def asset_id(run_id: str, path: str, sha256: str) -> str:
    """Location-independent identity; content hashes do not address a blob store."""
    return (
        "ASSET-" + hashlib.sha256(f"{run_id}\0{path}\0{sha256}".encode()).hexdigest()[:16].upper()
    )


class ResearchAssetRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str = Field(pattern=r"^AGENT-[0-9A-F]{16}$")
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size: int = Field(ge=0)
    asset_id: str = ""
    kind: str | None = None
    producer_tool: str | None = None
    execution_status: Literal["success", "failure", "timeout"] | None = None
    related_script: str | None = None
    related_input: list[str] = Field(default_factory=list)
    related_output: list[str] = Field(default_factory=list)
    retained: bool = False

    @field_validator("path", "related_script")
    @classmethod
    def safe_path(cls, value: str | None) -> str | None:
        return validate_asset_path(value) if value is not None else None

    @field_validator("related_input", "related_output")
    @classmethod
    def safe_relations(cls, values: list[str]) -> list[str]:
        return sorted({validate_asset_path(value) for value in values})

    @model_validator(mode="after")
    def identity(self) -> ResearchAssetRef:
        expected = asset_id(self.run_id, self.path, self.sha256)
        if self.asset_id and self.asset_id != expected:
            raise ValueError("Asset ID does not match run/path/content identity.")
        object.__setattr__(self, "asset_id", expected)
        return self


class ResearchAssetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    run_id: str = Field(pattern=r"^AGENT-[0-9A-F]{16}$")
    problem_id: str | None = None
    assets: list[ResearchAssetRef] = Field(default_factory=list)
    object_assets: dict[str, list[str]] = Field(default_factory=dict)
    broken_refs: list[str] = Field(default_factory=list)
    unresolved_relations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def scoped_unique_records(self) -> ResearchAssetManifest:
        by_id = {ref.asset_id: ref for ref in self.assets}
        if len(by_id) != len(self.assets) or any(r.run_id != self.run_id for r in self.assets):
            raise ValueError("Manifest has duplicate IDs or foreign run assets.")
        for ids in self.object_assets.values():
            if len(ids) != len(set(ids)) or any(
                i not in by_id or not by_id[i].retained for i in ids
            ):
                raise ValueError("Object links must name unique retained manifest assets.")
        return self


def _run_root(ot_dir: Path, run_id: str) -> Path:
    if not _RUN.fullmatch(run_id):
        raise ResearchError("Invalid research run ID.")
    base = ot_dir.resolve() / "research_runs"
    root = base / run_id
    if base.resolve() != base or root.resolve() != root:
        raise ResearchError("Research run directory must not redirect.")
    return root


def _path(ot_dir: Path, run_id: str, relative: str) -> Path:
    try:
        validate_asset_path(relative)
    except ValueError as exc:
        raise ResearchError(str(exc)) from exc
    root = _run_root(ot_dir, run_id)
    selected = root / relative
    # Reject symlinks/junctions even if their target stays inside another run area.
    if selected.resolve() != selected or not selected.resolve().is_relative_to(root):
        raise ResearchError("Asset paths must not redirect or escape their run.")
    return selected


def _verified_slice(
    ot_dir: Path, ref: ResearchAssetRef, offset: int = 0, length: int = 0
) -> tuple[Path, bytes]:
    ref = ResearchAssetRef.model_validate(ref.model_dump())
    path = _path(ot_dir, ref.run_id, ref.path)
    if not path.is_file():
        raise AssetNotFoundError(f"Missing research asset: {ref.asset_id}")
    digest, size, preview = hashlib.sha256(), 0, bytearray()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            digest.update(chunk)
            start, end = max(0, offset - size), min(len(chunk), offset + length - size)
            if end > start:
                preview.extend(chunk[start:end])
            size += len(chunk)
    if size != ref.size or digest.hexdigest() != ref.sha256:
        raise AssetIntegrityError(f"Research asset size/SHA-256 mismatch: {ref.asset_id}")
    return path, bytes(preview)


def resolve_research_asset(ot_dir: Path, ref: ResearchAssetRef) -> Path:
    """Read-only byte integrity check. It grants no mathematical authority."""
    return _verified_slice(ot_dir, ref)[0]


def _json(path: Path) -> dict:
    if path.resolve() != path:
        raise ResearchError("Operational metadata must not redirect.")
    if not path.is_file():
        return {}
    value = json.loads(path.read_text("utf-8"))
    if not isinstance(value, dict):
        raise ResearchError(f"Expected an object in {path.name}.")
    return value


def _rows(path: Path) -> list[dict]:
    if path.resolve() != path:
        raise ResearchError("Operational ledger must not redirect.")
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def explicit_asset_paths(text: str) -> set[str]:
    """Parse exact portable paths only; never repair truncated or unsafe references."""
    found = set()
    for match in _PATH.finditer(text):
        value = match.group().rstrip(".")
        try:
            found.add(validate_asset_path(value))
        except ValueError:
            pass
    return found


def _object_sources(ot_dir: Path, run_id: str, run: dict) -> dict[str, str]:
    """Existing Episodes/candidates and their accepted Proof/Evidence projections."""
    from math_research.ledger.archive import _verified_bytes
    from math_research.ledger.episodes import list_candidates, list_episodes, list_reviews
    from math_research.ledger.records import store

    pid = run.get("request", {}).get("target", {}).get("problem_id")
    if not pid or store.get_dossier(ot_dir, pid) is None:
        return {}
    ids = {run.get("episode_id"), *run.get("episode_history", [])}
    episodes = [
        e
        for e in list_episodes(ot_dir, pid)
        if e.episode_id in ids
        or (e.provenance or "").startswith(f"automated Research Agent {run_id};")
    ]
    sources = {e.episode_id: _verified_bytes(ot_dir, e).decode("utf-8") for e in episodes}
    candidates = [c for c in list_candidates(ot_dir, pid) if c.episode_id in sources]
    for c in candidates:
        sources[c.candidate_id] = c.body
        if c.object_id:
            sources[c.object_id] = c.body
    mapped = {
        r.mapped_id
        for r in list_reviews(ot_dir, pid)
        if r.candidate_id in sources and r.decision == "accept" and r.mapped_id
    }
    for proof in store.list_proof_attempts(ot_dir, pid):
        if proof.id in mapped and proof.body_path:
            base = store.dossier_dir(ot_dir, pid).resolve()
            path = (base / proof.body_path).resolve()
            if not path.is_relative_to(base / "proof_attempts"):
                raise ResearchError("Accepted Proof body redirects outside its store.")
            sources[proof.id] = path.read_text("utf-8")
    for reader in (store.list_claims, store.list_evidence):
        for record in reader(ot_dir, pid):
            if record.id in mapped or set(record.source_artifacts).intersection(sources):
                sources[record.id] = record.model_dump_json()
    return sources


def _execution_metadata(run_dir: Path, refs: dict[str, ResearchAssetRef]) -> None:
    calls: dict[str, dict] = {}
    scripts: dict[tuple[str, str], list[str]] = {}
    for path, ref in refs.items():
        if ref.kind == "script":
            code = (run_dir / path).read_text("utf-8")
            scripts.setdefault((ref.producer_tool or "", code), []).append(path)
    for event in _rows(run_dir / "events.jsonl"):
        call_id = event.get("call_id")
        if not isinstance(call_id, str):
            continue
        if event.get("event") == "tool_call" and event.get("name") in _SCRIPTS.values():
            calls[call_id] = event
        if event.get("event") != "tool_observation" or call_id not in calls:
            continue
        call = calls[call_id]
        matching = scripts.get((call["name"], call.get("args", {}).get("code", "")), [])
        if len(matching) != 1:
            continue  # Duplicate code cannot establish which execution produced this file.
        path = matching[0]
        try:
            result = json.loads(event.get("content", ""))
        except (ValueError, TypeError):
            result = {}
        result = result if isinstance(result, dict) else {}
        metadata = event.get("failure_metadata") or {}
        timeout = (
            result.get("error") == "execution_timeout"
            or metadata.get("error") == "execution_timeout"
            or result.get("error_class") in {"ExecutionTimeout", "CommandExecutionTimeout"}
            or metadata.get("error_class") in {"ExecutionTimeout", "CommandExecutionTimeout"}
            # Exact legacy transport outcome, not a guess from mathematical prose.
            or result.get("error") == "exec failed: sandbox error: command timed out"
        )
        status = (
            "timeout"
            if timeout
            else "success"
            if event.get("ok") is True
            else "failure"
            if event.get("ok") is False
            else None
        )
        if not timeout and type(result.get("exit_code")) is int and result["exit_code"] != 0:
            status = "failure"
        refs[path] = refs[path].model_copy(update={"execution_status": status})
        for output in refs[path].related_output:
            refs[output] = refs[output].model_copy(update={"execution_status": status})


def collect_retained_assets(
    run_dir: Path, refs: Iterable[ResearchAssetRef], *, sources: Iterable[str] = ()
) -> set[tuple[str, str]]:
    """Explicit references plus one output→script step, never recursive propagation."""
    by_path = {ref.path: ref for ref in refs}
    run_id = run_dir.name
    texts = list(sources)
    for relative in ("checkpoint/episode.md", "checkpoint/latest.md"):
        path = _path(run_dir.parent.parent, run_id, relative)
        if path.is_file():
            texts.append(path.read_text("utf-8"))
    for row in _rows(run_dir / "public_progress.jsonl"):
        for key in ("artifact", "summary"):
            if isinstance(row.get(key), str):
                texts.append(row[key])
    state = _json(run_dir / "checkpoint/state.json")
    if isinstance(state.get("file"), str):
        texts.append(state["file"])
    for group in state.get("groups", {}).values():
        texts.extend(value for value in group if isinstance(value, str))
    # Inventory is discovery metadata, not a citation: size/mtime alone does not
    # turn every collected scratch file into retained research evidence.
    direct = set().union(*(explicit_asset_paths(text) for text in texts)) if texts else set()
    closure = {
        by_path[path].related_script
        for path in direct
        if path in by_path and by_path[path].kind == "output" and by_path[path].related_script
    }
    return {(run_id, path) for path in direct | closure if path is not None}


def load_asset_manifest(ot_dir: Path, run_id: str) -> ResearchAssetManifest | None:
    root = _run_root(ot_dir, run_id)
    path = root / "assets.json"
    if not path.exists():
        return None
    if path.resolve() != path:
        raise ResearchError("Asset manifest must not redirect.")
    manifest = ResearchAssetManifest.model_validate_json(path.read_text("utf-8"))
    if manifest.run_id != run_id:
        raise AssetIntegrityError("Asset manifest belongs to a different run.")
    pid = _json(root / "run.json").get("request", {}).get("target", {}).get("problem_id")
    if pid != manifest.problem_id:
        raise AssetIntegrityError("Asset manifest Problem scope mismatch.")
    return manifest


def build_asset_manifest(run_dir: Path) -> ResearchAssetManifest:
    """Rebuild in memory from existing files/explicit records; never persist or migrate."""
    ot_dir, run_id = run_dir.parent.parent, run_dir.name
    root = _run_root(ot_dir, run_id)
    if run_dir.resolve() != root or not root.is_dir():
        raise ResearchError("Expected an existing research_runs/<run_id> directory.")
    run = _json(root / "run.json")
    if run.get("run_id", run_id) != run_id:
        raise AssetIntegrityError("Run metadata belongs to a different run.")
    refs: dict[str, ResearchAssetRef] = {}
    for area in sorted(_AREAS):
        for path in sorted((root / area).rglob("*")):
            if not path.is_file() or path.name.startswith(".sandbox"):
                continue
            relative = path.relative_to(root).as_posix()
            selected = _path(ot_dir, run_id, relative)
            raw = selected.read_bytes()
            script = area == "work" and re.fullmatch(r"script-\d+\.(py|g|sing)", path.name)
            output = area == "artifacts" and re.fullmatch(r"script-\d+-output\.txt", path.name)
            public = area == "artifacts" and re.fullmatch(r"public-[A-Za-z0-9-]+\.txt", path.name)
            refs[relative] = ResearchAssetRef(
                run_id=run_id,
                path=relative,
                sha256=hashlib.sha256(raw).hexdigest(),
                size=len(raw),
                kind="script" if script else "output" if output else "public" if public else None,
                producer_tool=_SCRIPTS[path.suffix]
                if script
                else "public_progress"
                if public
                else None,
            )
    unresolved = []
    for relative, ref in list(refs.items()):
        if ref.kind != "output":
            continue
        stem = Path(relative).name.removesuffix("-output.txt")
        producers = [
            f"work/{stem}{suffix}" for suffix in _SCRIPTS if f"work/{stem}{suffix}" in refs
        ]
        if len(producers) != 1:
            unresolved.append(relative)
            continue
        script_path = producers[0]
        refs[relative] = ref.model_copy(
            update={
                "related_script": script_path,
                "producer_tool": refs[script_path].producer_tool,
            }
        )
        refs[script_path] = refs[script_path].model_copy(update={"related_output": [relative]})
    _execution_metadata(root, refs)
    unresolved.extend(
        path for path, ref in refs.items() if ref.kind == "script" and not ref.related_output
    )
    sources = _object_sources(ot_dir, run_id, run)
    final = root / "checkpoint/episode.md"
    if final.is_file():
        sources[run_id] = final.read_text("utf-8")
    retained = collect_retained_assets(root, refs.values(), sources=sources.values())
    for relative in refs:
        refs[relative] = refs[relative].model_copy(
            update={"retained": (run_id, relative) in retained}
        )
    links = {}
    for oid, text in sorted(sources.items()):
        direct = explicit_asset_paths(text)
        closure = {
            refs[p].related_script
            for p in direct
            if p in refs and refs[p].kind == "output" and refs[p].related_script
        }
        links[oid] = sorted({refs[p].asset_id for p in direct | closure if p in refs})
    # Previously published identities are never silently rebound to new bytes.
    # Mutable checkpoint paths can acquire a new ID; the old ID still fails its
    # original hash check. Retention and old immutable Episode links remain pinned.
    previous = load_asset_manifest(ot_dir, run_id)
    by_id = {r.asset_id: r for r in refs.values()}
    if previous:
        for ref in previous.assets:
            if ref.retained:
                by_id[ref.asset_id] = by_id.get(ref.asset_id, ref).model_copy(
                    update={"retained": True}
                )
        links = {
            **previous.object_assets,
            **{
                oid: ids
                for oid, ids in links.items()
                if oid == run_id or oid not in previous.object_assets
            },
        }
    return ResearchAssetManifest(
        run_id=run_id,
        problem_id=run.get("request", {}).get("target", {}).get("problem_id"),
        assets=sorted(by_id.values(), key=lambda r: (r.path, r.asset_id)),
        object_assets=links,
        broken_refs=sorted(path for _, path in retained if path not in refs),
        unresolved_relations=sorted(unresolved),
    )


def publish_asset_manifest(run_dir: Path) -> ResearchAssetManifest:
    """Explicit finalization only. Reads/polls/retrieval never create a manifest."""
    root = _run_root(run_dir.parent.parent, run_dir.name)
    with file_lock(root / "assets.json"):
        manifest = build_asset_manifest(root)
        atomic_write_text(root / "assets.json", manifest.model_dump_json(indent=2) + "\n")
    return manifest


def _manifests(ot_dir: Path, problem_id: str) -> Iterable[ResearchAssetManifest]:
    for path in sorted((ot_dir / "research_runs").glob("*/assets.json")):
        manifest = load_asset_manifest(ot_dir, path.parent.name)
        if manifest and manifest.problem_id == problem_id:
            yield manifest


def find_research_assets(ot_dir: Path, problem_id: str, object_id: str) -> list[ResearchAssetRef]:
    """Small metadata discovery by existing object ID; no body/context injection."""
    from math_research.ledger.episodes import list_reviews

    # Review aliases may postdate finalization; follow existing provenance without
    # rewriting the manifest or changing retention on a read.
    owners = {object_id}
    owners.update(
        review.candidate_id
        for review in list_reviews(ot_dir, problem_id)
        if review.decision == "accept" and review.mapped_id == object_id
    )
    found = {}
    for manifest in _manifests(ot_dir, problem_id):
        ids = {ident for oid in owners for ident in manifest.object_assets.get(oid, [])}
        for ref in manifest.assets:
            if ref.asset_id in ids and ref.retained:
                found[ref.asset_id] = ref
    return sorted(found.values(), key=lambda r: (r.run_id, r.path, r.asset_id))


def lookup_research_asset(ot_dir: Path, problem_id: str, ident: str) -> ResearchAssetRef:
    if not _ASSET.fullmatch(ident):
        raise ResearchError("Invalid research asset ID; paths are not accepted.")
    for manifest in _manifests(ot_dir, problem_id):
        for ref in manifest.assets:
            if ref.asset_id == ident:
                if not ref.retained:
                    raise AssetNotRetainedError("Research asset is scratch, not retained.")
                return ref
    raise AssetNotFoundError("Research asset not found in this Problem's manifests.")


def read_research_asset(
    ot_dir: Path, problem_id: str, ident: str, *, offset: int = 0, length: int = MAX_ASSET_PREVIEW
) -> dict:
    ref = lookup_research_asset(ot_dir, problem_id, ident)
    offset, length = max(0, offset), min(MAX_ASSET_PREVIEW, max(1, length))
    _, raw = _verified_slice(ot_dir, ref, offset, length)
    text = raw.decode("utf-8", errors="replace")
    return {
        "metadata": ref.model_dump(mode="json"),
        "preview": text,
        "chars": len(text),
        "offset": offset,
        "size": ref.size,
        "sha256": ref.sha256,
        "run_id": ref.run_id,
        "kind": ref.kind,
        "status": ref.execution_status,
        "truncated": offset + len(raw) < ref.size,
        "integrity_note": INTEGRITY_NOTE,
    }


def can_delete_asset(ot_dir: Path, run_id: str, relative: str) -> bool:
    """Automatic deletion guard only; no deletion/force path is implemented."""
    root = _run_root(ot_dir, run_id)
    _path(ot_dir, run_id, relative)
    manifest = build_asset_manifest(root)
    return not (
        any(r.path == relative and r.retained for r in manifest.assets)
        or relative in manifest.broken_refs
    )


def can_delete_run(ot_dir: Path, run_id: str) -> bool:
    manifest = build_asset_manifest(_run_root(ot_dir, run_id))
    return not (any(r.retained for r in manifest.assets) or manifest.broken_refs)
