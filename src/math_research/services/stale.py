"""Read-only reports; stale never deletes history."""

from pathlib import Path

from math_research.ledger.manifest import Ledger
from math_research.ledger.persistence import records
from math_research.verification.freshness import Freshness, FreshnessResolver, receipt_current
from math_research.verification.models import AcceptanceReceipt, VerificationReceipt


def stale_report(state: Path, problem_id: str | None = None) -> dict:
    ledger = Ledger(state)
    entries = ledger.objects()
    resolver = FreshnessResolver(entries)
    objects = []
    for entry in entries:
        if problem_id and entry.ref.problem_id != problem_id:
            continue
        result = resolver.resolve(entry.ref)
        if result.freshness != Freshness.CURRENT:
            objects.append({"ref": entry.ref.model_dump(), **result.model_dump(mode="json")})
    checks = [
        r
        for r in records(state, "verifications", VerificationReceipt)
        if not problem_id or r.target.ref.problem_id == problem_id
    ]
    acceptances = [
        r
        for r in records(state, "acceptances", AcceptanceReceipt)
        if not problem_id or r.target.ref.problem_id == problem_id
    ]
    check_by_id = {r.id: r for r in checks}
    acceptance_states = []
    for receipt in acceptances:
        result = resolver.check_pins(
            (
                receipt.target,
                *receipt.dependencies,
                *((receipt.correspondence.informal,) if receipt.correspondence else ()),
            )
        )
        evidence = check_by_id.get(receipt.verification_id)
        if evidence is None or not receipt_current(state, evidence, entries):
            result.freshness = Freshness.STALE
            result.reasons.append("Accepted verification evidence changed or unavailable")
        acceptance_states.append({"id": receipt.id, **result.model_dump(mode="json")})
    return {
        "source_version": ledger.source_version(problem_id),
        "objects": objects,
        "verifications": [
            {"id": r.id, "current": receipt_current(state, r, entries)} for r in checks
        ],
        "acceptances": acceptance_states,
    }
