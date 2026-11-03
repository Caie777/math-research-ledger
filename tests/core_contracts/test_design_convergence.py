"""Real-use semantic gaps, exercised solely against synthetic stores."""

import pytest
from pydantic import ValidationError

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.manifest import Ledger
from math_research.ledger.records import claims, store
from math_research.mcp.adapter import LedgerAdapter
from math_research.retrieval.index import IndexDoc, search_documents
from math_research.retrieval.research_map import build_research_map
from math_research.services.problems import update_problem
from math_research.services.research import (
    add_claim,
    create_problem,
    get_object,
    history,
    link_dependency,
)
from math_research.services.review import prepare_review, submit_review
from math_research.verification.review import ReviewReport


def inventory(state):
    return {p.relative_to(state): p.read_bytes() for p in state.rglob("*") if p.is_file()}


def test_mature_statement_binding_keeps_authority_and_semantic_pins(research):
    state, ref = research
    problem_ref = ObjectRef(problem_id=ref.problem_id, kind="problem", object_id=ref.problem_id)
    assert store.require_dossier(state, ref.problem_id).statement_authority is None
    initial_authority = get_object(state, problem_ref).authority
    link_dependency(state, ref, problem_ref, DependencyRole.LOGICAL_PREMISE)
    old = Ledger(state).get(problem_ref).version
    args = dict(
        problem_id=ref.problem_id,
        primary_claim_id=ref.object_id,
        revision_kind="semantic",
        expected_version=old,
    )
    before = inventory(state)
    assert update_problem(state, **args, dry_run=True)["semantic_revision"]
    assert inventory(state) == before
    result = update_problem(state, **args)
    assert result["semantic_revision"] and result["version"] != old
    assert store.require_dossier(state, ref.problem_id).statement_authority is None
    assert get_object(state, problem_ref).authority == initial_authority
    assert get_object(state, ref).freshness == "STALE"
    assert any(row["version"] == old for row in history(state, problem_ref))


@pytest.mark.parametrize("field", ["statement", "primary_target"])
def test_mature_statement_text_revision_becomes_provisional(research, field):
    state, ref = research
    assert store.require_dossier(state, ref.problem_id).statement_authority is None
    args = dict(
        problem_id=ref.problem_id,
        revision_kind="semantic",
        **{field: "Changed synthetic mathematical text"},
    )
    before = inventory(state)
    assert update_problem(state, **args, dry_run=True)["semantic_revision"]
    assert inventory(state) == before
    result = update_problem(state, **args)
    assert result["semantic_revision"]
    assert store.require_dossier(state, ref.problem_id).statement_authority == "PROVISIONAL"


def test_unknown_search_kind_fails_before_reading_workspace(tmp_path):
    from math_research.services.retrieval import search_research

    for kind in ["cliam", "nonexistent_kind", "relation", "unresolved", "acceptance_request"]:
        with pytest.raises(ResearchError, match="Unknown research object kind"):
            search_research(tmp_path / "missing-workspace", "synthetic", kind=kind)


def test_search_kinds_are_valid_even_without_matching_objects(research):
    from math_research.services.retrieval import SEARCH_KINDS

    state, ref = research
    adapter = LedgerAdapter(state)
    assert "formal_bundle" in SEARCH_KINDS
    for kind in ["cliam", "unknown", "unresolved", "relation", "acceptance", "acceptance_request"]:
        with pytest.raises(ValidationError):
            adapter.call("research_search", {"query": ref.qualified_id, "kind": kind})
    assert not adapter.call(
        "research_search",
        {"query": ref.qualified_id, "problem_id": ref.problem_id, "kind": "formal_bundle"},
    )["hits"]


def test_search_schema_enum_matches_audited_emitted_kinds():
    from math_research.ledger.manifest import RESEARCH_OBJECT_KINDS
    from math_research.mcp.adapter import SearchArgs
    from math_research.services.retrieval import SEARCH_KINDS

    # Currently every emitted ObjectView kind is searchable by exact or lexical
    # navigation. An emitter change must prompt an explicit public-surface audit.
    assert SEARCH_KINDS == RESEARCH_OBJECT_KINDS
    schema = SearchArgs.model_json_schema()["properties"]["kind"]
    choices = next(option for option in schema["anyOf"] if option.get("type") == "string")
    assert set(choices["enum"]) == SEARCH_KINDS and "pattern" not in choices
    assert SearchArgs(query="synthetic").kind is None
    for kind in SEARCH_KINDS:
        assert SearchArgs.model_validate({"query": "synthetic", "kind": kind}).kind == kind


def test_search_can_return_each_public_kind_by_exact_identity(research, monkeypatch):
    from math_research.services import retrieval

    state, ref = research
    template = get_object(state, ref)
    views = []
    for kind in [*sorted(retrieval.SEARCH_KINDS), "internal_only"]:
        entry = template.object.model_copy(
            update={
                "ref": ObjectRef(problem_id=ref.problem_id, kind=kind, object_id=f"TEST-{kind}"),
            }
        )
        views.append(template.model_copy(update={"object": entry}))
    monkeypatch.setattr(retrieval, "list_objects", lambda *args: views)
    monkeypatch.setattr(retrieval.Ledger, "source_version", lambda *args: "synthetic-version")
    # Exercise real search identity resolution, filtering and result assembly;
    # ObjectViews substitute for storage, including types absent from Recall.
    for view in views:
        kind = view.object.ref.kind
        result = retrieval.search_research(
            state, view.object.qualified_id, problem_id=ref.problem_id
        )
        if kind == "internal_only":
            assert all(hit["ref"]["kind"] != kind for hit in result["hits"])
            continue
        assert result["retrieval_mode"] == "EXACT_IDENTITY"
        assert result["hits"][0]["ref"] == view.object.ref.model_dump()
        filtered = retrieval.search_research(
            state, view.object.qualified_id, problem_id=ref.problem_id, kind=kind
        )
        assert filtered["hits"] == result["hits"]


def test_binding_versions_preview_freshness_and_gap_context(research):
    state, ref = research
    adapter = LedgerAdapter(state)
    pid = ref.problem_id
    update_problem(state, problem_id=pid, revision_kind="semantic", primary_target="Full target")
    status = adapter.call("research_status", {"problem_id": pid})["continuation"]
    assert status["primary_target_binding"] == "TEXT_ONLY"
    assert status["primary_target_statement"] == "Full target"
    assert status["primary_target_diagnostic"] is None and "problem_status" not in status
    problem_ref = ObjectRef(problem_id=pid, kind="problem", object_id=pid)
    dependent = add_claim(state, pid, "Dependent synthetic claim")
    dep_ref = ObjectRef(problem_id=pid, kind="claim", object_id=dependent.id)
    link_dependency(state, dep_ref, problem_ref, DependencyRole.LOGICAL_PREMISE)
    old = Ledger(state).get(problem_ref).version
    args = dict(
        problem_id=pid,
        primary_claim_id=ref.qualified_id,
        revision_kind="semantic",
        expected_version=old,
    )
    before = inventory(state)
    preview = adapter.call("research_update_problem", {**args, "dry_run": True})
    assert preview["semantic_revision"] and inventory(state) == before
    result = adapter.call("research_update_problem", args)
    assert result["version"] != old
    assert any(row["version"] == old for row in history(state, problem_ref))
    assert get_object(state, dep_ref).freshness == "STALE"
    status = adapter.call("research_status", {"problem_id": pid})["continuation"]
    assert status["primary_target_binding"] == "CLAIM"
    assert status["primary_claim_id"] == ref.object_id
    assert status["primary_target"]["ref"] == ref.qualified_id
    assert not adapter.call(
        "research_update_problem", {**args, "expected_version": result["version"]}
    )["semantic_revision"]
    gap = claims.add_claim(state, pid, claim_type="OPEN_GAP", statement="Synthetic target gap")
    gap_ref = ObjectRef(problem_id=pid, kind="gap", object_id=gap.id)
    packet = adapter.call("research_context_packet", {"ref": gap_ref.qualified_id})
    assert any(item["ref"] == ref.model_dump() for item in packet["items"])


def test_binding_rejects_wrong_scope_kind_missing_and_metadata(research):
    state, ref = research
    other = create_problem(state, "Other", "Other synthetic scope")
    foreign = add_claim(state, other.id, "Other scope claim")
    for value in [
        f"{other.id}:claim:{foreign.id}",
        "CLAIM-9999",
        f"{ref.problem_id}:problem:{ref.problem_id}",
        "A complete synthetic claim",
    ]:
        before = inventory(state)
        with pytest.raises((ResearchError, ValueError)):
            update_problem(
                state,
                problem_id=ref.problem_id,
                revision_kind="semantic",
                primary_claim_id=value,
                dry_run=True,
            )
        assert inventory(state) == before
    with pytest.raises(ValidationError, match="semantic"):
        update_problem(state, problem_id=ref.problem_id, primary_claim_id=ref.object_id)


@pytest.mark.parametrize("state_name", ["REVISED", "SUPERSEDED", "HISTORICAL", "REFUTED"])
def test_binding_rejects_historical_projection(research, monkeypatch, state_name):
    state, ref = research
    view = get_object(state, ref)
    view.object.research_state = state_name
    monkeypatch.setattr("math_research.ledger.projection.get_object", lambda *a: view)
    with pytest.raises(ResearchError, match="Historical"):
        update_problem(
            state,
            problem_id=ref.problem_id,
            primary_claim_id=ref.object_id,
            revision_kind="semantic",
        )


def test_binding_rejects_rejected_provisional_claim(research):
    from math_research.ledger.episodes import list_candidates
    from math_research.services.ingest import ingest_episode, review_proposal

    state, ref = research
    ingest_episode(
        state,
        ref.problem_id,
        "rejected.md",
        b"## Claim: rejected\n\nSynthetic rejected target.\n",
        provenance="synthetic",
    )
    candidate = list_candidates(state, ref.problem_id)[0]
    review_proposal(state, ref.problem_id, candidate.candidate_id, "reject")
    before = inventory(state)
    with pytest.raises(ResearchError, match="Historical"):
        update_problem(
            state,
            problem_id=ref.problem_id,
            primary_claim_id=candidate.object_id,
            revision_kind="semantic",
            dry_run=True,
        )
    assert inventory(state) == before


def test_review_math_context_metadata_stability_and_report_pins(research):
    state, ref = research
    problem_ref = ObjectRef(problem_id=ref.problem_id, kind="problem", object_id=ref.problem_id)
    # Also exercise the metadata leakage route through a referenced Problem dependency.
    link_dependency(state, ref, problem_ref, DependencyRole.LOGICAL_PREMISE)
    packet = prepare_review(state, ref)
    assert packet.problem_context["statement"] == "A synthetic test problem"
    for changes in [
        dict(title="Editable title"),
        dict(lifecycle_status="paused"),
        dict(lifecycle_status="closed", closure_kind="other", closure_reason="Test"),
        dict(lifecycle_status="active"),
        dict(summary="Project summary"),
    ]:
        update_problem(state, problem_id=ref.problem_id, **changes)
        assert prepare_review(state, ref).source_version == packet.source_version
    report = ReviewReport(
        id="review-context",
        target=packet.target,
        reviewer="synthetic reviewer",
        verdict="INCONCLUSIVE",
        packet_version=packet.source_version,
    )
    assert submit_review(state, report).authority == "ADVISORY"
    for field in ["statement", "primary_target"]:
        previous = prepare_review(state, ref)
        update_problem(
            state,
            problem_id=ref.problem_id,
            revision_kind="semantic",
            **{field: "Revised mathematical framework"},
        )
        assert prepare_review(state, ref).source_version != previous.source_version
        with pytest.raises(ResearchError, match="version changed"):
            submit_review(state, report.model_copy(update={"id": f"old-{field}"}))


def test_search_filter_exact_identity_and_scoped_stale(research):
    state, ref = research
    gap = claims.add_claim(state, ref.problem_id, claim_type="OPEN_GAP", statement="Synthetic gap")
    adapter = LedgerAdapter(state)
    for scope in [{}, {"problem_id": ref.problem_id}]:
        hits = adapter.call("research_search", {"query": "Synthetic", "kind": "gap", **scope})[
            "hits"
        ]
        assert hits and all(h["ref"]["kind"] == "gap" for h in hits)
        exact = adapter.call("research_search", {"query": gap.id, "kind": "gap", **scope})
        assert exact["retrieval_mode"] == "EXACT_IDENTITY"
        assert not adapter.call(
            "research_search", {"query": ref.qualified_id, "kind": "gap", **scope}
        )["hits"]
    for args, expected in [
        ({}, {"kind": "workspace"}),
        ({"problem_id": ref.problem_id}, {"kind": "problem", "problem_id": ref.problem_id}),
    ]:
        report = adapter.call("research_stale_report", args)
        assert report["scope"] == expected and report["counts_are_scoped"]
    update_problem(state, problem_id=ref.problem_id, lifecycle_status="paused")
    node = next(n for n in build_research_map(state, ref.problem_id).nodes if n.type == "problem")
    assert node.status == "paused" and store.require_dossier(state, ref.problem_id).status == "open"


def test_title_match_beats_incidental_long_body():
    docs = [
        IndexDoc(
            artifact_id="gap",
            artifact_type="gap",
            title="chamber obstruction",
            text="synthetic target",
        ),
        IndexDoc(
            artifact_id="claim",
            artifact_type="claim",
            title="Other result",
            text="unrelated " * 1000 + "chamber obstruction",
        ),
    ]
    assert search_documents(docs, "chamber obstruction")[0][0].artifact_id == "gap"
