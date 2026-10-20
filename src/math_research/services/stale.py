"""Read-only reports; stale never deletes history."""

from pathlib import Path

from math_research.ledger.manifest import Ledger
from math_research.ledger.persistence import records
from math_research.services.verification import receipt_current
from math_research.verification.freshness import Freshness, FreshnessResolver
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
    checks = [r for r in records(state, "verifications", VerificationReceipt) if not problem_id or r.target.ref.problem_id == problem_id]
    acceptances = [r for r in records(state, "acceptances", AcceptanceReceipt) if not problem_id or r.target.ref.problem_id == problem_id]
    return {
        "source_version": ledger.source_version(problem_id), "objects": objects,
        "verifications": [{"id": r.id, "current": receipt_current(state, r, entries)} for r in checks],
        "acceptances": [{"id": r.id, **resolver.check_pins((r.target, *r.dependencies, *((r.correspondence.informal,) if r.correspondence else ()))).model_dump(mode="json")} for r in acceptances],
    }
