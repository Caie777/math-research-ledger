import pytest
from test_formal import CLEAN, fake_commands
from test_formal import project as project

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.records.write_boundary import automated_scope
from math_research.services.acceptance import accept, request_acceptance
from math_research.services.research import get_object
from math_research.services.retrieval import export_context_packet
from math_research.services.verification import check_formalization, freeze_statement
from math_research.verification.formal.checker import CommandResult


def bundle(research, project, monkeypatch):
    state, ref = research
    repo, _, checker = project
    monkeypatch.setattr("math_research.services.verification._git_head", lambda _: "synthetic-head")
    freeze_statement(
        state,
        ref,
        ident="FORMAL-synthetic",
        repo=repo,
        statement="Statement.lean",
        local_definitions=("Definition.lean",),
        module="Example",
        declaration="Example.target",
        expected_type="True",
    )
    formal_ref = ObjectRef(
        problem_id=ref.problem_id, kind="formal_bundle", object_id="FORMAL-synthetic"
    )
    calls = fake_commands(
        monkeypatch, checker, [CommandResult(0, "built"), CommandResult(0, CLEAN)]
    )
    result = check_formalization(state, formal_ref, checker)
    return formal_ref, result, calls


def test_synthetic_formal_checked_acceptance_and_proof_drift(research, project, monkeypatch):
    state, claim = research
    repo, _, checker = project
    formal, receipt, calls = bundle(research, project, monkeypatch)
    assert receipt.outcome.status == "PASSED"
    assert get_object(state, formal).authority == "PROVISIONAL"
    assert not get_object(state, claim).trusted_formal_premise
    assert check_formalization(state, formal, checker) == receipt and len(calls) == 2
    request = request_acceptance(state, formal, receipt.id)
    with pytest.raises(ResearchError, match="correspondence"):
        accept(state, request.id, actor="synthetic human", rationale="test")
    with automated_scope(), pytest.raises(ResearchError):
        accept(state, request.id, actor="model", rationale="not permitted", correspondence="test")
    accept(
        state,
        request.id,
        actor="synthetic human",
        rationale="inspected",
        correspondence="Synthetic informal/formal scope checked",
    )
    assert get_object(state, claim).trusted_formal_premise
    assert get_object(state, formal).trusted_formal_premise
    packet = export_context_packet(state, claim, token_budget=12000)
    assert next(i for i in packet.items if i.ref == claim).label == "TRUSTED"
    history = (state / "ledger/acceptances.jsonl").read_bytes()
    from math_research.ledger.history import object_history

    saved = object_history(state, formal)
    assert saved and saved[0]["record"]["proof_sources"]
    (repo / "Proof.lean").write_text("theorem target : True := by simp\n", encoding="utf-8")
    assert get_object(state, formal).freshness == "STALE"
    assert get_object(state, claim).freshness == "STALE"
    assert not get_object(state, claim).trusted_formal_premise
    assert (
        next(
            i
            for i in export_context_packet(state, claim, token_budget=12000).items
            if i.ref == claim
        ).label
        == "STALE"
    )
    assert (state / "ledger/acceptances.jsonl").read_bytes() == history


def test_checker_log_tamper_revokes_current_premise_without_erasing_acceptance(
    research, project, monkeypatch
):
    state, claim = research
    formal, receipt, _ = bundle(research, project, monkeypatch)
    request = request_acceptance(state, formal, receipt.id)
    accept(state, request.id, actor="human", rationale="test", correspondence="test correspondence")
    from pathlib import Path

    Path(receipt.artifacts[0].path).write_text("tampered checker log", encoding="utf-8")
    assert get_object(state, claim).freshness == "STALE"
    assert not get_object(state, claim).trusted_formal_premise
    with pytest.raises(ResearchError):
        request_acceptance(state, formal, receipt.id)


def test_review_packet_preserves_full_proof_and_definitions(research):
    from test_ledger import episode

    from math_research.services.ingest import ingest_episode
    from math_research.services.research import add_definition
    from math_research.services.review import prepare_review

    state, ref = research
    add_definition(state, ref.problem_id, "D", "exact definition")
    ingest_episode(
        state, ref.problem_id, "test.md", episode(ref), provenance="synthetic external harness"
    )
    packet = prepare_review(state, ref)
    assert packet.definitions and packet.proofs
    assert packet.proofs[0]["full_content"].count("full synthetic proof text") == 150


def test_service_retains_failed_drift_result(research, project, monkeypatch):
    state, _ = research
    repo, _, checker = project
    formal, _, _ = bundle(research, project, monkeypatch)
    (repo / "Statement.lean").write_text("def statement : Prop := False\n", encoding="utf-8")
    result = check_formalization(state, formal, checker)
    assert result.outcome.status == "FAILED"
    assert "FROZEN_SOURCE_DRIFT" in result.outcome.details["reasons"]
    assert get_object(state, formal).freshness == "STALE"
