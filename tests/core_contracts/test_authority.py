import pytest
from pydantic import ValidationError

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.persistence import records
from math_research.ledger.records.write_boundary import automated_scope
from math_research.services.acceptance import accept, request_acceptance
from math_research.services.research import (
    add_definition,
    get_object,
    link_dependency,
    update_definition,
)
from math_research.services.review import prepare_review, submit_review
from math_research.services.stale import stale_report
from math_research.services.verification import ExactVerificationService
from math_research.verification.models import AcceptanceReceipt, CheckOutcome, ExactCertificate
from math_research.verification.review import ReviewReport, ReviewVerdict


class SyntheticChecker:
    def check(self, certificate):
        return CheckOutcome(
            status="PASSED"
            if certificate.inputs["left"] == certificate.inputs["right"]
            else "FAILED",
            summary="Synthetic exact equality test",
        )


def checked(state, ref):
    return ExactVerificationService({"test-equality": SyntheticChecker()}).verify(
        state,
        ref,
        ExactCertificate(
            checker="test-equality", inputs={"left": 2, "right": 2}, scope="synthetic equality only"
        ),
    )


def test_canonical_checked_accepted_are_distinct_and_idempotent(research):
    state, ref = research
    view = get_object(state, ref)
    assert view.authority == "CANONICAL" and view.verification == "NOT_CHECKED"
    receipt = checked(state, ref)
    assert checked(state, ref) == receipt
    assert get_object(state, ref).authority == "CANONICAL"
    assert get_object(state, ref).verification == "PASSED"
    request = request_acceptance(state, ref, receipt.id)
    assert request_acceptance(state, ref, receipt.id) == request
    with automated_scope(), pytest.raises(ResearchError):
        accept(state, request.id, actor="test human", rationale="test")
    accepted = accept(state, request.id, actor="test human", rationale="Reviewed exact scope")
    assert accept(state, request.id, actor="test human", rationale="repeat") == accepted
    assert len(records(state, "acceptances", AcceptanceReceipt)) == 1
    assert get_object(state, ref).authority == "HUMAN_ACCEPTED"
    assert not get_object(state, ref).trusted_formal_premise


def test_definition_change_stales_acceptance_without_rewriting_receipts(research):
    state, ref = research
    d = add_definition(state, ref.problem_id, "D", "v1 definition")
    dr = ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=d.id)
    link_dependency(state, ref, dr, DependencyRole.DEFINITION)
    verification = checked(state, ref)
    request = request_acceptance(state, ref, verification.id)
    accept(state, request.id, actor="human", rationale="test")
    before = (state / "ledger/acceptances.jsonl").read_bytes()
    update_definition(state, ref.problem_id, d.model_copy(update={"definition": "v2 definition"}))
    assert get_object(state, ref).freshness == "STALE"
    assert not get_object(state, ref).usable_working_premise
    assert (state / "ledger/acceptances.jsonl").read_bytes() == before
    assert stale_report(state)["acceptances"][0]["freshness"] == "STALE"
    with pytest.raises(ResearchError):
        accept(state, request.id, actor="human", rationale="cannot reaccept stale")


def test_soft_review_advisory_never_verifies(research):
    state, ref = research
    packet = prepare_review(state, ref)
    report = ReviewReport(
        id="REVIEW-test",
        target=packet.target,
        reviewer="external synthetic reviewer",
        verdict=ReviewVerdict.NO_GAP_FOUND,
        packet_version=packet.source_version,
    )
    assert submit_review(state, report) == submit_review(state, report)
    assert report.authority == "ADVISORY"
    assert get_object(state, ref).verification == "NOT_CHECKED"
    assert get_object(state, ref).authority == "CANONICAL"
    with pytest.raises(ValidationError):
        ReviewReport(**{**report.model_dump(), "authority": "HUMAN_ACCEPTED"})


def test_failed_or_wrong_target_verification_cannot_request_authority(research):
    state, ref = research
    service = ExactVerificationService({"eq": SyntheticChecker()})
    failed = service.verify(
        state,
        ref,
        ExactCertificate(checker="eq", inputs={"left": 1, "right": 2}, scope="synthetic"),
    )
    with pytest.raises(ResearchError):
        request_acceptance(state, ref, failed.id)
    with pytest.raises(ResearchError):
        service.verify(
            state, ref, ExactCertificate(checker="unregistered", inputs={}, scope="test")
        )


def test_changed_dependency_set_invalidates_receipt(research):
    state, ref = research
    receipt = checked(state, ref)
    d = add_definition(state, ref.problem_id, "D", "full D")
    link_dependency(
        state,
        ref,
        ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=d.id),
        DependencyRole.DEFINITION,
    )
    with pytest.raises(ResearchError):
        request_acceptance(state, ref, receipt.id)


def test_recheck_and_new_acceptance_do_not_resurrect_old_receipt(research):
    state, ref = research
    d = add_definition(state, ref.problem_id, "D", "v1")
    dr = ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=d.id)
    link_dependency(state, ref, dr, DependencyRole.DEFINITION)
    first = checked(state, ref)
    old_request = request_acceptance(state, ref, first.id)
    accept(state, old_request.id, actor="human", rationale="first scope")
    update_definition(state, ref.problem_id, d.model_copy(update={"definition": "v2"}))
    link_dependency(state, ref, dr, DependencyRole.DEFINITION)
    assert get_object(state, ref).freshness == "STALE"
    second = checked(state, ref)
    assert second.id != first.id
    new_request = request_acceptance(state, ref, second.id)
    accept(state, new_request.id, actor="human", rationale="reviewed new scope")
    assert get_object(state, ref).freshness == "CURRENT"
    assert len(records(state, "acceptances", AcceptanceReceipt)) == 2


@pytest.mark.parametrize("key", ["SMR_AUTOMATED_RESEARCH", "MCH_AUTOMATED_RESEARCH"])
def test_automated_environment_cannot_use_human_cli_service(research, monkeypatch, key):
    state, ref = research
    receipt = checked(state, ref)
    request = request_acceptance(state, ref, receipt.id)
    monkeypatch.setenv(key, "1")
    with pytest.raises(ResearchError):
        accept(state, request.id, actor="automated caller", rationale="cannot elevate")


def test_mcp_can_request_but_cannot_elevate(research):
    from math_research.mcp.adapter import LedgerAdapter

    state, ref = research
    receipt = checked(state, ref)
    result = LedgerAdapter(state).call(
        "research_request_acceptance", {"ref": ref.qualified_id, "verification_id": receipt.id}
    )
    assert result["id"].startswith("REQUEST-")
    assert get_object(state, ref).authority == "CANONICAL"
