"""Human-only elevation, immutable receipts and current version checks."""

from pathlib import Path

from math_research.core.atomicio import file_lock
from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash
from math_research.core.refs import ObjectRef
from math_research.ledger.manifest import Ledger
from math_research.ledger.persistence import append_once, ledger_path, records
from math_research.ledger.records.write_boundary import human_write
from math_research.verification.freshness import Freshness, FreshnessResolver
from math_research.verification.models import AcceptanceReceipt, AcceptanceRequest, HumanCorrespondence, VerificationKind, VerificationReceipt, VersionPin


def _verification(state, ident):
    receipt = next((r for r in records(state, "verifications", VerificationReceipt) if r.id == ident), None)
    if receipt is None or receipt.outcome.status != "PASSED":
        raise ResearchError("Acceptance requires an existing passed hard-verification receipt.")
    return receipt


def request_acceptance(state: Path, target: ObjectRef, verification_id: str) -> AcceptanceRequest:
    ledger = Ledger(state)
    resolver = FreshnessResolver(ledger.objects())
    receipt = _verification(state, verification_id)
    if receipt.target.ref != target:
        raise ResearchError("Verification targets a different qualified object.")
    if resolver.check_pins((receipt.target, *receipt.dependencies)).freshness != Freshness.CURRENT:
        raise ResearchError("Verification evidence is stale or incomplete.")
    pins = resolver.pins(target)
    identity = content_hash({"target": receipt.target.model_dump(mode="json"), "verification": verification_id, "pins": [p.model_dump(mode="json") for p in pins]})
    old = next((r for r in records(state, "acceptance_requests", AcceptanceRequest) if r.id == "REQUEST-" + identity[:24]), None)
    if old:
        return old
    value = AcceptanceRequest(id="REQUEST-" + identity[:24], target=receipt.target, verification_id=verification_id, dependencies=tuple(p for p in pins if p.ref != target))
    return append_once(state, "acceptance_requests", value, key="id")


def pending_acceptances(state: Path) -> list[AcceptanceRequest]:
    done = {r.request_id for r in records(state, "acceptances", AcceptanceReceipt)}
    return [r for r in records(state, "acceptance_requests", AcceptanceRequest) if r.id not in done]


@human_write
def accept(state: Path, request_id: str, *, actor: str, rationale: str, correspondence: str | None = None) -> AcceptanceReceipt:
    with file_lock(ledger_path(state, "acceptances").with_suffix(".transaction")):
        existing = next((r for r in records(state, "acceptances", AcceptanceReceipt) if r.request_id == request_id), None)
        request = next((r for r in records(state, "acceptance_requests", AcceptanceRequest) if r.id == request_id), None)
        if request is None:
            raise ResearchError("Acceptance request not found.")
        ledger = Ledger(state)
        resolver = FreshnessResolver(ledger.objects())
        pins = (request.target, *request.dependencies)
        check = _verification(state, request.verification_id)
        if check.target != request.target or resolver.check_pins((*pins, *check.dependencies)).freshness != Freshness.CURRENT:
            raise ResearchError("Acceptance input changed; request review of the current version.")
        if existing:
            return existing
        link = None
        if check.kind == VerificationKind.FORMAL:
            bundle = ledger.get(request.target.ref)
            if bundle.ref.kind != "formal_bundle" or not correspondence or not bundle.record.get("target"):
                raise ResearchError("Formal acceptance requires explicit human informal/formal correspondence.")
            informal = ObjectRef.model_validate(bundle.record["target"])
            link = HumanCorrespondence(rationale=correspondence, informal=VersionPin(ref=informal, version=ledger.get(informal).version), formal=request.target)
        value = AcceptanceReceipt(id="ACCEPT-" + content_hash({"request": request_id})[:24], request_id=request_id, target=request.target, verification_id=request.verification_id, dependencies=request.dependencies, actor=actor, rationale=rationale, correspondence=link)
        return append_once(state, "acceptances", value, key="id")


def accepted_targets(state: Path, entries: list) -> tuple[dict, set]:
    """Historical authority is retained even when its current evidence becomes stale."""
    accepted, formal = {}, set()
    resolver = FreshnessResolver(entries)
    for receipt in records(state, "acceptances", AcceptanceReceipt):
        pins = (receipt.target, *receipt.dependencies)
        accepted[receipt.target.ref.qualified_id] = pins
        if receipt.correspondence:
            pins = (*pins, receipt.correspondence.informal, receipt.correspondence.formal)
            accepted[receipt.correspondence.informal.ref.qualified_id] = pins
            if resolver.check_pins(pins).freshness == Freshness.CURRENT:
                formal.update((receipt.target.ref.qualified_id, receipt.correspondence.informal.ref.qualified_id))
    return accepted, formal
