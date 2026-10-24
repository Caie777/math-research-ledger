"""Synthetic Problem lifecycle, semantic pins and journaled writer regressions."""

import hashlib
import json
import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash
from math_research.core.refs import ObjectRef
from math_research.core.workspace import init_workspace
from math_research.ledger import checkpoint
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.manifest import Ledger, record_content_hash
from math_research.ledger.records import store
from math_research.ledger.records.write_boundary import automated_scope
from math_research.mcp.adapter import SCHEMAS, LedgerAdapter
from math_research.services import problems
from math_research.services.ingest import ingest_episode
from math_research.services.research import add_claim, get_object, history, link_dependency

CREATE = {
    "title": "Synthetic project",
    "statement": "A synthetic question.",
    "primary_target": "Determine the synthetic case.",
}


def inventory(state):
    return {
        p.relative_to(state).as_posix(): p.read_bytes() for p in state.rglob("*") if p.is_file()
    }


def mutate(state, **kwargs):
    return LedgerAdapter(state).call("research_update_problem", kwargs)


def test_create_and_previews_are_explicit_and_zero_write(research, monkeypatch):
    state, _ = research
    before = inventory(state)
    with monkeypatch.context() as mock:
        mock.setattr(
            checkpoint, "file_lock", lambda *a, **k: pytest.fail("Preview took writer lock")
        )
        preview = LedgerAdapter(state).call("research_create_problem", {**CREATE, "dry_run": True})
        assert preview["problem_id"] == "PROBLEM-0002" and not preview["id_reserved"]
        update = mutate(state, problem_id="PROBLEM-0001", lifecycle_status="paused", dry_run=True)
        assert update["lifecycle_change"] == {"from": "active", "to": "paused"}
    assert inventory(state) == before
    created = LedgerAdapter(state).call("research_create_problem", CREATE)
    assert created["problem_id"] == preview["problem_id"] and created["version"]
    assert created["validation_errors"] == []
    record = store.require_dossier(state, created["problem_id"])
    assert record.title == CREATE["title"] and record.primary_target == CREATE["primary_target"]
    assert record.lifecycle_status == "active" and record.statement_authority == "PROVISIONAL"
    assert (
        store.statement_body_for_display(store.read_statement(state, record.id))
        == CREATE["statement"]
    )
    assert inventory(state)[checkpoint.GENERATION] != before[checkpoint.GENERATION]
    assert store.get_active_problem(state) == "PROBLEM-0001"  # No implicit selection change.
    adapter = LedgerAdapter(state)
    assert (
        adapter.call("research_status", {"problem_id": record.id})["continuation"][
            "primary_target_statement"
        ]
        == CREATE["primary_target"]
    )
    assert adapter.call("research_search", {"query": record.id})["hits"]
    packet = adapter.call("research_context_packet", {"ref": created["ref"]})
    assert any(CREATE["primary_target"] in item["content"] for item in packet["items"])
    result = ingest_episode(
        state,
        record.id,
        "synthetic.md",
        b"## Claim: synthetic\n\nSynthetic increment.",
        provenance="fixture",
    )
    assert result["candidates"][0]["problem_id"] == record.id
    again = adapter.call("research_create_problem", CREATE)
    assert again["problem_id"] != record.id  # Repeated creates allocate, never overwrite.


@pytest.mark.parametrize(
    "payload",
    [
        {**CREATE, "title": " "},
        {**CREATE, "statement": ""},
        {**CREATE, "primary_target": None},
        {**CREATE, "authority": "HUMAN_ACCEPTED"},
        {**CREATE, "statement": "x" * 8001},
        {**CREATE, "statement": "界" * 5000},
    ],
)
def test_bad_create_is_rejected_before_mutation(research, payload):
    state, _ = research
    before = inventory(state)
    with pytest.raises(ValidationError):
        LedgerAdapter(state).call("research_create_problem", payload)
    assert inventory(state) == before


def test_missing_workspace_and_unknown_episode_never_initialize(tmp_path, research):
    absent = tmp_path / "absent" / ".math-research-ledger"
    for dry_run in (True, False):
        with pytest.raises(ResearchError, match="research state"):
            problems.create_problem(absent, **CREATE, dry_run=dry_run)
        with pytest.raises(ResearchError, match="research state"):
            problems.update_problem(
                absent, problem_id="PROBLEM-0001", lifecycle_status="paused", dry_run=dry_run
            )
    assert not absent.exists()
    state, _ = research
    before = inventory(state)
    with pytest.raises(ResearchError, match="No problem dossier"):
        ingest_episode(state, "PROBLEM-0999", "bad.md", b"Synthetic.", provenance="fixture")
    assert inventory(state) == before


@pytest.mark.parametrize("kind", ["resolved", "abandoned", "superseded", "other"])
def test_lifecycle_reopens_without_touching_math_authority(research, kind):
    state, ref = research
    before = get_object(state, ref).model_dump()
    from math_research.services.research import create_problem

    other = create_problem(state, "Other synthetic scope")
    add_claim(state, other.id, "Duplicate bare Claim ID in another Problem")
    problem = store.require_dossier(state, ref.problem_id)
    pin = (
        Ledger(state)
        .get(ObjectRef(problem_id=problem.id, kind="problem", object_id=problem.id))
        .version
    )
    for status in ("paused", "active"):
        mutate(state, problem_id=problem.id, lifecycle_status=status)
        assert store.require_dossier(state, problem.id).lifecycle_status == status
    result = mutate(
        state,
        problem_id=problem.id,
        lifecycle_status="closed",
        closure_kind=kind,
        closure_reason="Synthetic stopping decision",
        resolution_refs=[ref.object_id],
    )
    assert result["version"] == pin and not result["semantic_revision"]
    closed = store.require_dossier(state, problem.id)
    assert closed.closure_kind == kind and closed.resolution_refs == [ref.qualified_id]
    page = LedgerAdapter(state).call(
        "research_get_object", {"ref": f"{problem.id}:problem:{problem.id}", "length": 8000}
    )
    assert "Synthetic stopping decision" in page["content"] and '"closed"' in page["content"]
    mutate(state, problem_id=problem.id, lifecycle_status="active")
    reopened = store.require_dossier(state, problem.id)
    assert (
        reopened.lifecycle_status == "active" and reopened.closure_reason == closed.closure_reason
    )
    assert get_object(state, ref).model_dump() == before
    assert not list((state / "ledger").glob("*accept*.jsonl"))
    assert not list((state / "ledger").glob("*verifications*.jsonl"))
    with automated_scope(), pytest.raises(ResearchError, match="Automated"):
        add_claim(state, problem.id, "Cannot bypass canonical writes")


def test_legacy_versions_survive_metadata_updates_and_stale_only_on_semantics(research):
    state, ref = research
    # Synthetic legacy Windows bytes must survive an identical semantic request.
    statement_path = store.dossier_dir(state, ref.problem_id) / "statement.md"
    statement_path.write_bytes(
        statement_path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    )
    ledger = Ledger(state)
    problem_ref = ObjectRef(problem_id=ref.problem_id, kind="problem", object_id=ref.problem_id)
    initial = ledger.get(problem_ref)
    old_keys = {
        "id",
        "title",
        "status",
        "domain",
        "created_at",
        "updated_at",
        "formalization_status",
        "known_equivalent_forms",
        "known_obstructions",
        "minimal_examples",
        "tags",
        "primary_claim_id",
    }
    legacy_hash = record_content_hash(
        {k: v for k, v in initial.record.items() if k in old_keys},
        initial.full_content,
        [ledger._artifact_identity(a) for a in initial.artifact_refs],
    )
    assert initial.version == content_hash({"content": legacy_hash, "dependencies": []})
    link_dependency(state, ref, problem_ref, DependencyRole.LOGICAL_PREMISE)
    downstream = add_claim(state, ref.problem_id, "A dependent synthetic fixture")
    downstream_ref = ObjectRef(problem_id=ref.problem_id, kind="claim", object_id=downstream.id)
    link_dependency(state, downstream_ref, ref, DependencyRole.LOGICAL_PREMISE)
    unrelated = add_claim(state, ref.problem_id, "Unrelated fixture")
    for changes in (
        {"title": "Corrected title"},
        {"summary": "Extra explanation"},
        {"source_refs": ["https://example.org/synthetic"]},
        {"metadata": {"label": "Synthetic local metadata"}},
        {"lifecycle_status": "paused"},
        {"lifecycle_status": "active"},
        {"revision_kind": "semantic", "title": "Metadata remains metadata"},
        {"revision_kind": "semantic", "statement": "A synthetic test problem"},
    ):
        response = mutate(state, problem_id=ref.problem_id, **changes)
        assert response["version"] == initial.version and not response["semantic_revision"]
        assert get_object(state, ref).freshness == "CURRENT"
        assert get_object(state, downstream_ref).freshness == "CURRENT"
    response = mutate(
        state,
        problem_id=ref.problem_id,
        revision_kind="semantic",
        statement="Revised synthetic assumptions.",
    )
    assert response["semantic_revision"] and response["version"] != initial.version
    assert get_object(state, ref).freshness == "STALE"
    assert get_object(state, downstream_ref).freshness == "STALE"
    assert (
        get_object(
            state, ObjectRef(problem_id=ref.problem_id, kind="claim", object_id=unrelated.id)
        ).freshness
        == "CURRENT"
    )
    saved = history(state, problem_ref)
    assert any(
        item["version"] == initial.version and item["full_content"].startswith(initial.full_content)
        for item in saved
    )
    # Persisted data, not an opaque cached version: external statement drift is visible.
    store.write_statement(state, ref.problem_id, "Another actual statement change")
    assert ledger.get(problem_ref).version != response["version"]


@pytest.mark.parametrize("field", ["statement", "primary_target"])
def test_semantic_revision_requires_explicit_kind_and_preserves_preview(research, field):
    state, ref = research
    before = inventory(state)
    with pytest.raises(ValidationError, match="semantic"):
        mutate(state, problem_id=ref.problem_id, **{field: "Changed mathematical target"})
    assert inventory(state) == before
    preview = mutate(
        state,
        problem_id=ref.problem_id,
        revision_kind="semantic",
        dry_run=True,
        **{field: "Changed mathematical target"},
    )
    assert preview["semantic_revision"] and inventory(state) == before
    result = mutate(
        state,
        problem_id=ref.problem_id,
        revision_kind="semantic",
        **{field: "Changed mathematical target"},
    )
    assert result["semantic_revision"]
    problem_entry = Ledger(state).get(ObjectRef.parse(result["ref"]))
    assert problem_entry.authority == "PROVISIONAL" and problem_entry.verification == "NOT_CHECKED"


@pytest.mark.parametrize(
    "changes",
    [
        {"lifecycle_status": "closed"},
        {"lifecycle_status": "closed", "closure_kind": "resolved"},
        {"closure_reason": "Not closed"},
        {"lifecycle_status": "deleted"},
        {"statement": "x", "revision_kind": "metadata"},
        {"title": None},
        {},
        {
            "lifecycle_status": "closed",
            "closure_kind": "other",
            "closure_reason": "Reason",
            "resolution_refs": ["PROBLEM-0001:claim:CLAIM-9999"],
        },
        {"title": "Conflict", "expected_version": "0" * 64},
    ],
)
def test_invalid_updates_fail_closed_and_preview_never_writes(research, changes):
    state, ref = research
    before = inventory(state)
    with pytest.raises((ResearchError, ValidationError)):
        mutate(state, problem_id=ref.problem_id, dry_run=True, **changes)
    assert inventory(state) == before


def test_allocator_skips_gaps_and_reserved_directories(research):
    state, _ = research
    (state / "problems/PROBLEM-0007").mkdir()
    created = problems.create_problem(state, **CREATE)
    assert created["problem_id"] == "PROBLEM-0008"
    assert len(store.list_dossiers(state)) == 2


def test_failed_create_and_update_roll_back_and_advance_generation(research, monkeypatch):
    state, ref = research
    before = inventory(state)
    real = store.atomic_write_text

    def fail_create(path, body):
        real(path, body)
        if path.name == "statement.md":
            raise OSError("Synthetic create failure")

    with monkeypatch.context() as mock:
        mock.setattr(store, "atomic_write_text", fail_create)
        with pytest.raises(OSError, match="create failure"):
            problems.create_problem(state, **CREATE)
    after = inventory(state)
    assert after.pop(checkpoint.GENERATION) != before.pop(checkpoint.GENERATION)
    assert after == before and not (state / "problems/PROBLEM-0002").exists()
    before = inventory(state)

    def fail_update(path, body):
        real(path, body)
        if path.name == "problem.yaml":
            raise OSError("Synthetic update failure")

    monkeypatch.setattr(problems, "atomic_write_text", fail_update)
    with pytest.raises(OSError, match="update failure"):
        mutate(state, problem_id=ref.problem_id, title="Will roll back")
    after = inventory(state)
    assert after.pop(checkpoint.GENERATION) != before.pop(checkpoint.GENERATION)
    assert after == before


def test_concurrent_creators_share_one_allocator(tmp_path):
    init_workspace(tmp_path)
    state = tmp_path / ".math-research-ledger"
    program = """import sys,json
from pathlib import Path
from math_research.services.problems import create_problem
print(json.dumps([create_problem(
 Path(sys.argv[1]),title='Same title',statement='Synthetic',
 primary_target='Synthetic target')['problem_id'] for _ in range(2)]))
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", program, str(state)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(4)
    ]
    ids = []
    try:
        for process in processes:
            out, err = process.communicate(timeout=40)
            assert process.returncode == 0, err
            ids.extend(json.loads(out))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    assert len(ids) == len(set(ids)) == 8
    assert len(store.list_dossiers(state)) == 8 and not (state / checkpoint.JOURNAL).exists()


@pytest.mark.parametrize("action", ["create", "update", "semantic"])
def test_real_process_crash_is_recoverable(research, action):
    state, ref = research
    before = inventory(state)
    program = """import os,sys
from pathlib import Path
from math_research.services import problems
from math_research.ledger.records import store
module=store if sys.argv[2]=='create' else problems
real=module.atomic_write_text
def crash(path,body):
 real(path,body)
 if path.name==('statement.md' if sys.argv[2]=='create' else 'problem.yaml'): os._exit(77)
module.atomic_write_text=crash
if sys.argv[2]=='create': problems.create_problem(
 Path(sys.argv[1]),title='Crash fixture',statement='Synthetic',primary_target='Synthetic target')
elif sys.argv[2]=='update': problems.update_problem(
 Path(sys.argv[1]),problem_id='PROBLEM-0001',title='Uncommitted title')
else: problems.update_problem(Path(sys.argv[1]),problem_id='PROBLEM-0001',
 revision_kind='semantic',statement='Uncommitted semantic statement')
"""
    completed = subprocess.run(
        [sys.executable, "-c", program, str(state), action], capture_output=True, timeout=20
    )
    assert completed.returncode == 77, completed.stderr
    assert (state / checkpoint.JOURNAL).exists()
    with pytest.raises(ResearchError, match="pending or interrupted"):
        LedgerAdapter(state).call("research_status", {})
    os.utime(
        state / ".checkpoint.lock", (0, 0)
    )  # Fixture process is dead; exercise stale-lock recovery.
    assert checkpoint.recover_checkpoint(state)["recovered"]
    after = inventory(state)
    assert after.pop(checkpoint.GENERATION) != before.pop(checkpoint.GENERATION)
    assert all(after[p] == body for p, body in before.items())
    extra = set(after) - set(before)
    assert (
        not extra or action == "semantic" and all(p.startswith("ledger/versions/") for p in extra)
    )
    assert store.require_dossier(state, ref.problem_id)


def test_original_nine_schemas_are_unchanged():
    # SHA256 of canonical JSON schema at public v1.2.1 (2ae449d).
    expected = dict(
        research_status="462076f8080161661bbe3187636813136468a2f3013f351da2368683ff248229",
        research_search="f84f8dfb3207a73989625f1717ddda298449bf459fd8f2ba2a1f786b118c9c5f",
        research_get_object="cb93a63caf2c4237ff2cca725bfe8c2c576724758ec96d36a55bf2cb306d308e",
        research_context_packet="fd5d408ceed81fa8deac675ff698a2c029cf8fb02d6e71f4fe4adfdd28e6c720",
        research_review_packet="69bc3c0c99315c2cd5f530a27a1834428bf607acac12153569b4daf7af561a7d",
        research_stale_report="719c35dd18fdeaf451cc4391ee9b30782aaf7e8f498c746fa7ef35b692c38793",
        research_ingest_episode="6a1d359006b23a5e5cb091014096170420de928ec79c928a47c14e9a11cb3c35",
        research_save_note="eb103db3cf8585ecbe9a5d87ea4402db9701be63d0b104d00ce7603d5658c04c",
        research_request_acceptance="a8841e8f286f4d45083a40bca3f497246ed36f4751c892c0f827e15920d9d44f",
    )
    assert len(SCHEMAS) == 11
    for name, digest in expected.items():
        assert (
            hashlib.sha256(
                json.dumps(SCHEMAS[name].model_json_schema(), sort_keys=True).encode()
            ).hexdigest()
            == digest
        )
