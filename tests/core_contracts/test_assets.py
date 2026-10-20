"""Retained pure identity/provenance contracts; no old runtime dependency."""

import hashlib
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from math_research.core.errors import ResearchError
from math_research.ledger.assets import (
    AssetIntegrityError,
    AssetNotFoundError,
    ResearchAssetManifest,
    ResearchAssetRef,
    build_asset_manifest,
    can_delete_asset,
    can_delete_run,
    collect_retained_assets,
    explicit_asset_paths,
    load_asset_manifest,
    lookup_research_asset,
    publish_asset_manifest,
    read_research_asset,
    resolve_research_asset,
)

OLD = "AGENT-" + "A" * 16

NEW = "AGENT-" + "B" * 16


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def seed_run(ot: Path, pid: str = "PROBLEM-0001") -> Path:
    folder = ot / "research_runs" / OLD
    for area in ("work", "artifacts", "checkpoint"):
        (folder / area).mkdir(parents=True)
    (folder / "run.json").write_text(
        json.dumps(
            {
                "run_id": OLD,
                "request": {"target": {"problem_id": pid}},
            }
        )
    )
    (folder / "work/script-0.py").write_text("print(7)\n")
    (folder / "artifacts/script-0-output.txt").write_text("7\n")
    (folder / "work/scratch.txt").write_text("unreferenced scratch")
    (folder / "artifacts/unknown.dat").write_bytes(b"unknown")
    (folder / "checkpoint/episode.md").write_text(
        "## EVIDENCE-1\n\n**Result**\n\nFinite computation: artifacts/script-0-output.txt\n"
    )
    events = [
        {"event": "tool_call", "call_id": "c1", "name": "python", "args": {"code": "print(7)\n"}},
        {
            "event": "tool_observation",
            "call_id": "c1",
            "name": "python",
            "ok": True,
            "content": json.dumps({"exit_code": 0, "artifact": "artifacts/script-0-output.txt"}),
        },
    ]
    (folder / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    return folder


@pytest.fixture
def asset_run(tmp_path):
    ot = tmp_path / ".math-research"
    return ot, seed_run(ot)


def by_path(manifest, path):
    return next(r for r in manifest.assets if r.path == path)


def test_identity_deterministic_and_content_bound(asset_run):
    ot, folder = asset_run
    before = snapshot(ot)
    first = build_asset_manifest(folder)
    assert first == build_asset_manifest(folder) and snapshot(ot) == before
    ref = by_path(first, "work/script-0.py")
    expected = (
        "ASSET-"
        + hashlib.sha256(f"{OLD}\0{ref.path}\0{ref.sha256}".encode()).hexdigest()[:16].upper()
    )
    assert ref.asset_id == expected and resolve_research_asset(ot, ref).is_file()
    (folder / ref.path).touch()
    assert by_path(build_asset_manifest(folder), ref.path).asset_id == ref.asset_id
    (folder / ref.path).write_text("print(8)\n")
    changed = by_path(build_asset_manifest(folder), ref.path)
    assert changed.asset_id != ref.asset_id
    with pytest.raises(AssetIntegrityError):
        resolve_research_asset(ot, ref)


@pytest.mark.parametrize(
    "path",
    [
        "/work/x",
        "C:/work/x",
        "C:work/x",
        "\\\\host\\work\\x",
        "../artifacts/x",
        "work/../artifacts/x",
        "work/./x",
        "work//x",
        "work\\x",
        "events.jsonl",
        "loop/auth.json",
        "artifacts/x:stream",
        "work/NUL.txt",
        "work/x.",
    ],
)
def test_asset_ref_rejects_unsafe_paths(path):
    with pytest.raises(ValidationError):
        ResearchAssetRef(run_id=OLD, path=path, sha256="a" * 64, size=1)


def test_wrong_run_and_tampered_id(asset_run):
    ot, folder = asset_run
    ref = by_path(build_asset_manifest(folder), "work/script-0.py")
    with pytest.raises(ValidationError):
        ResearchAssetRef(**(ref.model_dump() | {"run_id": "../escape"}))
    with pytest.raises(ValidationError):
        ResearchAssetRef(**(ref.model_dump() | {"run_id": NEW}))
    other = ResearchAssetRef(**(ref.model_dump() | {"run_id": NEW, "asset_id": ""}))
    with pytest.raises(AssetNotFoundError):
        resolve_research_asset(ot, other)
    with pytest.raises(ValidationError):
        ResearchAssetManifest(run_id=NEW, assets=[ref])


def test_manifest_association_unknown_and_no_duplicate_records(asset_run):
    ot, folder = asset_run
    manifest = publish_asset_manifest(folder)
    script = by_path(manifest, "work/script-0.py")
    output = by_path(manifest, "artifacts/script-0-output.txt")
    assert output.related_script == script.path and script.related_output == [output.path]
    assert script.producer_tool == output.producer_tool == "python"
    assert script.execution_status == output.execution_status == "success"
    assert by_path(manifest, "artifacts/unknown.dat").kind is None
    raw = (folder / "assets.json").read_bytes()
    assert publish_asset_manifest(folder) == manifest
    assert (folder / "assets.json").read_bytes() == raw
    assert len({r.asset_id for r in manifest.assets}) == len(manifest.assets)
    assert load_asset_manifest(ot, OLD) == manifest


@pytest.mark.parametrize(
    "status,detail",
    [
        ("failure", {"exit_code": 1}),
        (
            "timeout",
            {"error": "execution_timeout", "error_class": "ExecutionTimeout", "exit_code": -9},
        ),
        ("timeout", {"error": "exec failed: sandbox error: command timed out"}),
    ],
)
def test_failed_and_timeout_metadata(asset_run, status, detail):
    _, folder = asset_run
    events = [json.loads(line) for line in (folder / "events.jsonl").read_text().splitlines()]
    events[1].update(ok=False, content=json.dumps(detail), failure_metadata=detail)
    (folder / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    manifest = build_asset_manifest(folder)
    assert by_path(manifest, "work/script-0.py").execution_status == status
    assert by_path(manifest, "artifacts/script-0-output.txt").execution_status == status


def test_unknown_execution_is_not_inferred_from_output_text(asset_run):
    _, folder = asset_run
    (folder / "events.jsonl").unlink()
    (folder / "artifacts/script-0-output.txt").write_text("success! verified!")
    manifest = build_asset_manifest(folder)
    assert by_path(manifest, "work/script-0.py").execution_status is None
    (folder / "artifacts/script-9-output.txt").write_text("orphan")
    manifest = build_asset_manifest(folder)
    assert manifest.unresolved_relations == ["artifacts/script-9-output.txt"]
    assert by_path(manifest, "artifacts/script-9-output.txt").related_script is None


def test_retention_output_closure_and_scratch(asset_run):
    ot, folder = asset_run
    manifest = build_asset_manifest(folder)
    assert by_path(manifest, "artifacts/script-0-output.txt").retained
    assert by_path(manifest, "work/script-0.py").retained
    assert not by_path(manifest, "work/scratch.txt").retained
    assert not by_path(manifest, "artifacts/unknown.dat").retained
    assert not can_delete_run(ot, OLD)
    assert not can_delete_asset(ot, OLD, "work/script-0.py")
    assert can_delete_asset(ot, OLD, "work/scratch.txt")
    script = by_path(manifest, "work/script-0.py").model_copy(
        update={
            "related_input": ["work/scratch.txt"],
            "related_output": ["artifacts/unknown.dat"],
        }
    )
    refs = [script, *[r for r in manifest.assets if r.path != script.path]]
    retained = collect_retained_assets(folder, refs)
    assert (OLD, "work/script-0.py") in retained
    assert (OLD, "work/scratch.txt") not in retained
    assert (OLD, "artifacts/unknown.dat") not in retained  # No recursive/forward closure.
    (folder / "checkpoint/episode.md").write_text("No asset references.")
    assert can_delete_run(ot, OLD)  # No manifest yet, builder/guard never publish.
    assert not (folder / "assets.json").exists()


def test_public_and_checkpoint_explicit_references_not_inventory(asset_run):
    _, folder = asset_run
    (folder / "artifacts/public-1-abc.txt").write_text("public")
    (folder / "public_progress.jsonl").write_text(
        json.dumps(
            {
                "artifact": "artifacts/public-1-abc.txt",
                "summary": "artifacts/missing.txt",
            }
        )
    )
    (folder / "checkpoint/state.json").write_text(
        json.dumps(
            {
                "groups": {"Artifacts": ["- work/scratch.txt\n"]},
                "artifact_inventory": {"artifacts/unknown.dat": "7:1000"},
            }
        )
    )
    manifest = build_asset_manifest(folder)
    assert by_path(manifest, "artifacts/public-1-abc.txt").producer_tool == "public_progress"
    assert by_path(manifest, "work/scratch.txt").retained
    assert not by_path(manifest, "artifacts/unknown.dat").retained
    assert manifest.broken_refs == ["artifacts/missing.txt"]


def test_exact_reference_parsing():
    assert explicit_asset_paths(
        "`artifacts/a.txt`; work/script-1.py checkpoint/0003.md. "
        "../artifacts/escape.txt /artifacts/absolute.txt "
        "artifacts/../bad.txt https://host/artifacts/remote.txt"
    ) == {"artifacts/a.txt", "work/script-1.py", "checkpoint/0003.md"}


def test_missing_manifest_is_not_implicitly_built(asset_run):
    ot, folder = asset_run
    ref = by_path(build_asset_manifest(folder), "artifacts/script-0-output.txt")
    with pytest.raises(AssetNotFoundError):
        lookup_research_asset(ot, "PROBLEM-0001", ref.asset_id)
    assert not (folder / "assets.json").exists()


def test_integrity_changed_same_size_size_mismatch_and_missing(asset_run):
    ot, folder = asset_run
    ref = by_path(publish_asset_manifest(folder), "artifacts/script-0-output.txt")
    wrong_size = ResearchAssetRef(**(ref.model_dump() | {"size": ref.size + 1}))
    with pytest.raises(AssetIntegrityError, match="size/SHA-256"):
        resolve_research_asset(ot, wrong_size)
    path = folder / ref.path
    path.write_bytes(b"8\n")
    with pytest.raises(AssetIntegrityError):
        read_research_asset(ot, "PROBLEM-0001", ref.asset_id)
    path.unlink()
    with pytest.raises(AssetNotFoundError, match="Missing"):
        read_research_asset(ot, "PROBLEM-0001", ref.asset_id)
    assert not can_delete_run(ot, OLD)


def test_published_ids_never_rebaseline_and_retention_is_monotone(asset_run):
    ot, folder = asset_run
    ref = by_path(publish_asset_manifest(folder), "artifacts/script-0-output.txt")
    (folder / ref.path).write_text("new bytes")
    (folder / "checkpoint/episode.md").write_text("No longer mentions old output.")
    manifest = publish_asset_manifest(folder)
    assert next(r for r in manifest.assets if r.asset_id == ref.asset_id).retained
    with pytest.raises(AssetIntegrityError):
        read_research_asset(ot, "PROBLEM-0001", ref.asset_id)
    assert not can_delete_asset(ot, OLD, ref.path)
    assert manifest == build_asset_manifest(folder)


def test_manifest_wrong_run_rejected(asset_run):
    ot, folder = asset_run
    publish_asset_manifest(folder)
    raw = json.loads((folder / "assets.json").read_text())
    raw["run_id"] = NEW
    # Fail even when no row makes the scope mismatch obvious.
    raw["assets"], raw["object_assets"] = [], {}
    (folder / "assets.json").write_text(json.dumps(raw))
    with pytest.raises(AssetIntegrityError):
        load_asset_manifest(ot, OLD)


def test_link_escape_is_rejected(asset_run, tmp_path):
    ot, folder = asset_run
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "pinned.py").write_bytes(b"print(7)\n")
    link = folder / "work/link"
    if os.name == "nt":
        import _winapi

        # Junctions need no symlink privilege and exercise the Windows redirect
        # case that Path.is_symlink alone would miss.
        try:
            _winapi.CreateJunction(str(outside), str(link))
        except PermissionError:
            pytest.skip("This sandbox disallows creation of Windows junctions")
    else:
        link.symlink_to(outside, target_is_directory=True)
    ref = ResearchAssetRef(
        run_id=OLD,
        path="work/link/pinned.py",
        size=9,
        sha256=hashlib.sha256(b"print(7)\n").hexdigest(),
    )
    with pytest.raises(ResearchError, match="redirect"):
        resolve_research_asset(ot, ref)


def test_retained_assets_have_unified_producer_provenance(research):
    from math_research.ledger.dependencies import DependencyRole
    from math_research.ledger.manifest import Ledger

    state, target = research
    folder = seed_run(state, target.problem_id)
    publish_asset_manifest(folder)
    artifacts = [entry for entry in Ledger(state).objects() if entry.ref.kind == "artifact"]
    assert artifacts
    assert any(
        edge.role == DependencyRole.ARTIFACT_PROVENANCE
        for entry in artifacts
        for edge in entry.dependencies
    )
