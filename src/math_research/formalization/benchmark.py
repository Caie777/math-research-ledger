"""Single-run benchmark setup from allowlisted inputs, never a baseline solution checkout."""

from __future__ import annotations

import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import yaml

from math_research.core.atomicio import atomic_write_text
from math_research.core.process import run_process

from .agent import FormalBudget, FormalRunState, select_api_provider
from .checker import LeanChecker, code_only, validate_name
from .freeze import freeze, frozen_source, hash_bytes, source_path
from .loop import FormalizationLoop
from .tools import FormalTools
from .workspace import FormalWorkspace, append_event


def statement_contract(source: str) -> str:
    """Derive a type-checking contract from a simple frozen Prop predicate header."""
    clean = code_only(source)
    match = re.search(r"\bdef\s+([A-Za-z_][\w']*)\s*((?:\([^()\n]+\)\s*)+)\s*:\s*Prop\s*:=", clean)
    if not match:
        raise ValueError("Unsupported frozen statement header; no inferred weakening allowed")
    namespace = re.findall(r"\bnamespace\s+([A-Za-z_][\w.]*)", clean[: match.start()])
    qualified = ".".join([*namespace, match[1]])
    binders = re.findall(r"\(([A-Za-z_][\w']*)\s*:\s*([^()\n]+)\)", match[2])
    if not binders:
        raise ValueError("Missing statement parameters")
    parameters = " ".join(f"({name} : {kind.strip()})" for name, kind in binders)
    return f"∀ {parameters}, {qualified} " + " ".join(name for name, _ in binders)


def prepare_workspace(
    snapshot_bundle: Path, repo: Path, dependency_cache: Path, output: Path
) -> dict:
    """Copy approved snapshot files and dependency caches, never root build artifacts."""
    original = json.loads((snapshot_bundle / "freeze-manifest.json").read_text("utf-8"))
    # Deliberately select metadata fields only, never expose the parsed bundle to the model.
    raw = yaml.safe_load((snapshot_bundle / "bundle.yaml").read_text("utf-8"))
    metadata = {
        "declaration": raw["declaration"],
        "statement_version": raw["statement_version"],
        "informal_source": {
            key: raw["informal_source"][key]
            for key in ["title", "pdf_path", "pdf_sha256", "target", "page"]
        },
    }
    validate_name(metadata["declaration"])
    repo.mkdir(parents=True, exist_ok=False)
    output.mkdir(parents=True, exist_ok=True)
    audit = output / "setup-access-audit.jsonl"
    approved = {original["statement_path"], "lean-toolchain", "lakefile.toml", "lake-manifest.json"}
    if original["local_definitions"]:
        raise ValueError("This benchmark setup expects the approved definition-free snapshot")
    if set(original["files"]) != approved:
        raise ValueError("Unexpected source in the approved snapshot")
    snapshot = (snapshot_bundle / "statement-v1").resolve(strict=True)
    for relative in sorted(approved):
        source = source_path(snapshot, relative)
        data = source.read_bytes()
        if hash_bytes(data) != original["files"][relative]:
            raise ValueError("Approved snapshot hash mismatch")
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        append_event(
            audit,
            {"tool": "setup", "path": str(source), "operation": "copy_frozen", "allowed": True},
        )
    cache = dependency_cache.resolve(strict=True)
    if cache.name != "packages" or cache.parent.name != ".lake":
        raise ValueError("Expected dependency package cache, not a project checkout")
    lock = json.loads((repo / "lake-manifest.json").read_text("utf-8"))
    for package in lock["packages"]:
        name = package["name"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
            raise ValueError("Invalid locked dependency name")
        source = (cache / name).resolve(strict=True)
        if not source.is_relative_to(cache):
            raise ValueError("Dependency cache escape")
        shutil.copytree(source, repo / ".lake/packages" / name)
        append_event(
            audit,
            {
                "tool": "setup",
                "path": str(source),
                "operation": "copy_dependency_tree",
                "allowed": True,
                "package": name,
                "locked_commit": package["rev"],
            },
        )
    atomic_write_text(repo / ".gitignore", ".lake/\n")
    atomic_write_text(repo / "WeakSchottky.lean", "import WeakSchottky.Proofs.Target\n")
    atomic_write_text(
        repo / "WeakSchottky/Proofs/Target.lean", "import WeakSchottky.Lemma41Statement\n"
    )
    env = {**os.environ, "ELAN_HOME": "D:/Tools/elan"}
    run_process(["git", "init", str(repo)], env=env, capture_output=True, check=True)
    frozen = freeze(repo, original["statement_path"], (), output / "frozen")
    # Root import module is harness-owned and immutable too.
    frozen = frozen.model_copy(
        update={"dependencies": (*frozen.dependencies, frozen_source(repo, "WeakSchottky.lean"))}
    )
    atomic_write_text(output / "frozen-inputs.json", frozen.model_dump_json(indent=2))
    atomic_write_text(
        output / "frozen/root-module.lean", (repo / "WeakSchottky.lean").read_text("utf-8")
    )
    assert frozen.statement.sha256 == original["statement_sha256"]
    metadata["target_type"] = statement_contract(
        (repo / original["statement_path"]).read_text("utf-8")
    )
    metadata.update(
        statement_identical=True,
        statement_sha256=frozen.statement.sha256,
        lean_toolchain=frozen.lean_toolchain,
        mathlib_commit=frozen.mathlib_commit,
        mathlib_ref=frozen.mathlib_ref,
        formal_repo=str(repo.resolve()),
    )
    atomic_write_text(output / "setup.json", json.dumps(metadata, indent=2))
    return metadata


def informal_source(metadata: dict) -> str:
    from pypdf import PdfReader

    source = metadata["informal_source"]
    path = Path(source["pdf_path"])
    if hash_bytes(path.read_bytes()) != source["pdf_sha256"]:
        raise ValueError("PDF identity mismatch")
    reader = PdfReader(path)
    if source["title"] not in " ".join((reader.pages[0].extract_text() or "").split()):
        raise ValueError("Paper title mismatch")
    text = reader.pages[source["page"] - 1].extract_text() or ""
    start = re.search(r"Lemma\s+4\.1\.", text)
    end = re.search(r"Proposition\s+4\.2\.", text)
    if not start or not end or end.start() <= start.start():
        raise ValueError("Cannot isolate paper Lemma 4.1")
    return (
        f"# {source['title']}\n\nSource: PDF page {source['page']}, Lemma 4.1.\n\n"
        + text[start.start() : end.start()]
    )


def seal_run(run_dir: Path) -> str:
    """Content-address the terminal snapshot before any post-hoc baseline comparison."""
    if (run_dir / "run-freeze.json").exists():
        raise FileExistsError("Terminal run already sealed")
    inventory = {
        p.relative_to(run_dir).as_posix(): hash_bytes(p.read_bytes())
        for p in sorted(run_dir.rglob("*"))
        if p.is_file()
    }
    data = json.dumps(
        {"sealed_at": datetime.now(UTC).isoformat(), "files": inventory}, sort_keys=True, indent=2
    ).encode()
    (run_dir / "run-freeze.json").write_bytes(data)
    for path in run_dir.rglob("*"):
        if path.is_file():
            path.chmod(0o444)
    return hash_bytes(data)


def execute_benchmark(project: Path, repo: Path, output: Path, metadata: dict, lake: Path) -> dict:
    """One exclusive official-run reservation. No retries or alternate executor fallback."""
    from .freeze import load_freeze

    reservation = output / "official-run-reservation.json"
    with reservation.open("x", encoding="utf-8") as handle:
        json.dump({"created_at": datetime.now(UTC).isoformat(), "single_run": True}, handle)
    run_dir = output / "run"
    run_dir.mkdir(exist_ok=False)
    frozen = load_freeze(output / "frozen-inputs.json")
    selection = select_api_provider(project / ".math-research")
    if selection.provider is not None and not metadata.get("target_type"):
        raise ValueError("An API benchmark requires a frozen target type contract")
    atomic_write_text(output / "provider.json", json.dumps(selection.metadata, indent=2))
    checker = LeanChecker(lake)
    workspace = FormalWorkspace(repo, frozen, run_dir / "access-audit.jsonl")
    tools = FormalTools(
        workspace,
        checker,
        run_dir,
        "WeakSchottky.Proofs.Target",
        metadata["declaration"],
        target_type=metadata.get("target_type"),
    )
    informal = (output / "informal-target.md").read_text("utf-8")
    atomic_write_text(run_dir / "informal-target.md", informal)
    atomic_write_text(run_dir / "frozen-inputs.json", frozen.model_dump_json(indent=2))
    atomic_write_text(run_dir / "setup.json", json.dumps(metadata, indent=2))
    atomic_write_text(run_dir / "provider.json", json.dumps(selection.metadata, indent=2))
    if selection.provider is None:
        state = FormalRunState(
            run_id="BLOCKED-API-CONFIGURATION",
            stop_reason="BLOCKED_API_CONFIGURATION",
            proof_hashes=workspace.proof_hashes(),
        )
        tools.persist(state)
        atomic_write_text(run_dir / "run-summary.json", state.model_dump_json(indent=2))
        atomic_write_text(
            run_dir / "usage.json",
            json.dumps(
                {
                    "model_calls": 0,
                    "real_api_calls": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": None,
                }
            ),
        )
        result = "BLOCKED"
    else:
        try:
            state = FormalizationLoop(
                selection.provider, tools, informal, budget=FormalBudget()
            ).run()
            result = "CHECKED" if state.stop_reason == "CHECKED" else "FAILED"
        except Exception:
            # Never repair and resume a crashed official experiment as if it were clean.
            result = "BENCHMARK_INVALIDATED_BY_INFRA_BUG"
            state_path = run_dir / "run-state.json"
            state = (
                FormalRunState.model_validate_json(state_path.read_bytes())
                if state_path.exists()
                else FormalRunState(run_id="INFRASTRUCTURE-FAILURE")
            )
            state.stop_reason = result
            tools.persist(state)
            atomic_write_text(run_dir / "run-summary.json", state.model_dump_json(indent=2))
            append_event(run_dir / "agent-events.jsonl", {"event": result})
    if not (run_dir / "usage.json").exists():
        atomic_write_text(
            run_dir / "usage.json",
            json.dumps(
                {
                    "model_calls": state.model_calls,
                    "input_tokens": state.input_tokens,
                    "output_tokens": state.output_tokens,
                    "usage_missing_calls": state.usage_missing_calls,
                    "cached_tokens": None,
                }
            ),
        )
    for name in ["access-audit.jsonl", "build-events.jsonl", "agent-events.jsonl", "usage.jsonl"]:
        (run_dir / name).touch(exist_ok=True)
    # Preserve final sources inside the immutable terminal snapshot, including a failed attempt.
    for name in workspace.proof_hashes():
        destination = run_dir / "final" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((workspace.root / name).read_bytes())
    workspace.integrity()
    seal = seal_run(run_dir)
    benchmark = {
        "result": result,
        "stop_reason": state.stop_reason,
        "benchmark_valid": result not in {"BLOCKED", "BENCHMARK_INVALIDATED_BY_INFRA_BUG"},
        "official_run_started": selection.provider is not None,
        "provider": selection.metadata,
        "statement_identical": True,
        "statement_sha256": frozen.statement.sha256,
        "lean_toolchain": frozen.lean_toolchain,
        "mathlib_commit": frozen.mathlib_commit,
        "harness_commit": metadata.get("harness_commit"),
        "statement_drift": False,
        "model_calls": state.model_calls,
        "build_iterations": state.build_count,
        "target_checks": state.target_checks,
        "input_tokens": state.input_tokens,
        "output_tokens": state.output_tokens,
        "human_interventions_during_run": 0,
        "codex_executor_calls": 0,
        "run_seal_sha256": seal,
        "human_correspondence": "PENDING",
        "usable_as_premise": False,
    }
    atomic_write_text(output / "benchmark.json", json.dumps(benchmark, indent=2))
    atomic_write_text(
        output / "benchmark.sha256", hash_bytes((output / "benchmark.json").read_bytes()) + "\n"
    )
    return benchmark
