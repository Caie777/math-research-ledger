"""Explicit bounded continuation navigation, using synthetic workspaces only."""

import json

import pytest
from benchmarks.continuity.corpus import build_corpus

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.manifest import Ledger
from math_research.ledger.records import store
from math_research.mcp.adapter import LedgerAdapter
from math_research.retrieval.memory_policy import memory_access
from math_research.services.research import create_problem, status
from math_research.services.retrieval import export_context_packet


@pytest.fixture(scope="module")
def continuity_corpus(tmp_path_factory):
    return build_corpus(tmp_path_factory.mktemp("continuation-contract"))


def primary(research):
    state, ref = research
    problem = store.require_dossier(state, ref.problem_id)
    store.save_dossier(state, problem.model_copy(update={"primary_claim_id": ref.object_id}))
    return state, ref


def test_explicit_problem_restores_primary_despite_adversarial_current(research):
    state, ref = primary(research)
    other = create_problem(state, "Unrelated", "Synthetic other scope")
    store.set_active_problem(state, other.id)
    value = status(state, ref.problem_id)
    assert value["continuation"]["problem_id"] == ref.problem_id
    assert value["continuation"]["primary_target"]["ref"] == ref.qualified_id
    assert store.get_active_problem(state) == other.id


def test_no_explicit_selection_is_not_guessed_from_current(research):
    state, _ = primary(research)
    value = status(state)
    assert value["selection_required"] and value["continuation"] is None


def test_complete_is_only_required_set_complete(research):
    state, ref = research
    packet = export_context_packet(state, ref)
    value = packet.model_dump(mode="json")
    assert value["required_set_complete"] == packet.complete
    assert value["semantic_scope"] == "computed_required_set_only"
    assert "full_research_history" in value["omitted_categories"]


def test_no_baseline_cannot_claim_no_changes(research):
    state, ref = primary(research)
    value = LedgerAdapter(state).call("research_status", {"problem_id": ref.problem_id})
    assert value["continuation"]["changes"]["status"] == "NO_BASELINE"


def test_missing_primary_is_not_invented(research):
    state, ref = research
    value = status(state, ref.problem_id)["continuation"]
    assert value["primary_target"] is None
    assert value["primary_target_diagnostic"] == "NOT_DESIGNATED"
    assert not value["recommended_next_calls"]


def test_missing_designated_target_is_diagnostic(research):
    state, ref = research
    problem = store.require_dossier(state, ref.problem_id)
    store.save_dossier(state, problem.model_copy(update={"primary_claim_id": "CLAIM-9999"}))
    value = status(state, ref.problem_id)["continuation"]
    assert (
        value["primary_target"] is None and value["primary_target_diagnostic"] == "MISSING_OBJECT"
    )


def test_snapshot_detects_semantic_change_without_forging_history(research):
    state, ref = primary(research)
    before = status(state, ref.problem_id)["continuation"]
    version = Ledger(state).get(ref).version
    from math_research.ledger.episodes import list_candidates
    from math_research.services.ingest import ingest_episode, review_proposal

    ingest_episode(
        state,
        ref.problem_id,
        "r.md",
        b"## Claim: test\n\nProvisional semantic test.\n",
        provenance="synthetic",
    )
    candidate = list_candidates(state, ref.problem_id)[0]
    qid = ObjectRef(
        problem_id=ref.problem_id, kind="claim", object_id=candidate.object_id
    ).qualified_id
    # Explicit baselines can include any selected qualified ref, not just the first page.
    from math_research.ledger.continuation import fingerprint
    from math_research.ledger.projection import get_object

    baseline = {qid: fingerprint(get_object(state, ObjectRef.parse(qid)))}
    review_proposal(state, ref.problem_id, candidate.candidate_id, "reject")
    delta = status(state, ref.problem_id, since=baseline)["continuation"]["changes"]
    assert delta["changed"][0]["ref"] == qid
    assert delta["changed"][0]["current"]["authority"] == "REJECTED/HISTORICAL"
    same = status(state, ref.problem_id, since=before["continuation_snapshot"])["continuation"][
        "changes"
    ]
    assert not same["changed"] and same["unchanged_count"] == 1
    assert Ledger(state).get(ref).version == version


def test_baseline_scope_and_schema_are_enforced(research):
    state, ref = primary(research)
    with pytest.raises(ResearchError, match="explicit"):
        status(state, since={})
    with pytest.raises(ResearchError, match="conflicts"):
        status(state, ref.problem_id, since={"PROBLEM-9999:claim:CLAIM-0001": "a" * 64})
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        LedgerAdapter(state).call(
            "research_status", {"problem_id": ref.problem_id, "since": {ref.qualified_id: "bad"}}
        )


def test_bounded_navigation_and_latest_checkpoint(continuity_corpus):
    corpus = continuity_corpus
    value = status(corpus["state"], corpus["problem_id"])["continuation"]
    assert value["counts"]["open_gaps"] == 2
    assert value["counts"]["failed_routes"] == 1
    assert value["counts"]["counterexamples_refutations"] == 2
    assert value["counts"]["integrity_failed"] == 2
    latest = value["latest_meaningful_checkpoint"]
    assert latest["ref"] == corpus["roles"]["checkpoint_source"].qualified_id
    assert latest["authority"] == "ADVISORY" and not latest["usable_working_premise"]
    assert (
        value["latest_advisory_handoff"]["ref"] == corpus["roles"]["advisory_source"].qualified_id
    )
    assert value["latest_advisory_handoff"]["recheck_referenced_objects"]
    assert len(value["continuation_snapshot"]) <= 16
    assert "A synthetic checkpoint increment." not in json.dumps(value)


@pytest.mark.parametrize(
    "role,freshness,eligible",
    [
        ("current", "CURRENT", "ALLOWED"),
        ("unknown", "UNKNOWN", "BLOCKED"),
        ("stale", "STALE", "BLOCKED"),
        ("refuted", "CURRENT", "BLOCKED"),
        ("rejected", "CURRENT", "BLOCKED"),
        ("conditional", "CURRENT", "CONDITIONAL"),
    ],
)
def test_premise_state_survives_continuation_reads(continuity_corpus, role, freshness, eligible):
    from math_research.services.research import get_object

    c = continuity_corpus
    view = get_object(c["state"], c["roles"][role])
    assert view.freshness == freshness and view.premise_eligibility == eligible
    assert not view.trusted_formal_premise
    if eligible != "ALLOWED":
        assert not view.usable_working_premise


@pytest.mark.parametrize("budget", [2000, 8000, 16000])
def test_budget_and_complete_scope_are_truthful(research, budget):
    from math_research.ledger.dependencies import DependencyRole
    from math_research.services.research import add_definition, link_dependency

    state, ref = research
    definition = add_definition(
        state, ref.problem_id, "Long synthetic definition", "bounded proof input " * 5000
    )
    dref = ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=definition.id)
    link_dependency(state, ref, dref, DependencyRole.DEFINITION)
    packet = export_context_packet(state, ref, token_budget=budget)
    assert packet.token_estimate <= budget
    assert packet.required_set_complete == packet.complete
    assert packet.required_context_truncated
    assert not packet.required_set_complete
    assert dref.qualified_id in packet.required_record_ids
    assert "not complete mathematical state" in packet.continuation_coverage


@pytest.mark.parametrize(
    "event",
    [
        "route_transition",
        "duplicate_risk",
        "premise_reuse",
        "possible_conflict",
        "before_expensive_work",
        "historical_failures",
        "checkpoint",
    ],
)
def test_event_policy_is_guidance_only(event):
    value = memory_access(event)
    assert value["guidance_only"] and value["suggested_tools"]
    assert value["requires_meaningful_change"] == (event == "checkpoint")


def test_continuous_local_reasoning_does_not_request_ledger_calls():
    assert memory_access("session_start")["action"] == "RESTORE"
    for _ in range(20):
        assert memory_access("local_reasoning")["suggested_tools"] == []
    with pytest.raises(ValueError):
        memory_access("unknown")


def test_candidate_preparation_is_scoped_read_only_and_not_gold(continuity_corpus, tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    c = continuity_corpus
    output = tmp_path / "candidate-queries.json"
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            str(root / "scripts/prepare_continuity_candidates.py"),
            "--state",
            str(c["state"]),
            "--problem-id",
            c["problem_id"],
            "--output",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text("utf-8"))
    assert data["not_gold"] and data["integrity_observation"]["bytes_unchanged"]
    assert data["candidates"] and all(
        row["annotation_status"] == "PENDING_HUMAN" for row in data["candidates"]
    )
    assert all(
        row["ref"].startswith(c["problem_id"] + ":") and row["gold"] is None
        for row in data["candidates"]
    )
    assert "Primary synthetic chamber objective" not in output.read_text("utf-8")
