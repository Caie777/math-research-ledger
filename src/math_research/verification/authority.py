"""Read-only human authority projections; checked and canonical never self-promote."""

from pathlib import Path

from math_research.ledger.persistence import records
from math_research.verification.freshness import Freshness, FreshnessResolver, receipt_current
from math_research.verification.models import AcceptanceReceipt, VerificationReceipt


def accepted_targets(state: Path, entries: list) -> tuple[dict, set, set]:
    """Historical authority is retained even when its current evidence becomes stale."""
    accepted: dict = {}
    formal: set[str] = set()
    invalid: set[str] = set()
    checks = {r.id: r for r in records(state, "verifications", VerificationReceipt)}
    resolver = FreshnessResolver(entries)
    for receipt in records(state, "acceptances", AcceptanceReceipt):
        pins = (receipt.target, *receipt.dependencies)
        accepted[receipt.target.ref.qualified_id] = pins
        evidence = checks.get(receipt.verification_id)
        current = evidence is not None and receipt_current(state, evidence, entries)
        if not current:
            invalid.add(receipt.target.ref.qualified_id)
        else:
            invalid.discard(receipt.target.ref.qualified_id)
        if receipt.correspondence:
            if not current:
                invalid.add(receipt.correspondence.informal.ref.qualified_id)
            else:
                invalid.discard(receipt.correspondence.informal.ref.qualified_id)
            pins = (*pins, receipt.correspondence.informal, receipt.correspondence.formal)
            accepted[receipt.correspondence.informal.ref.qualified_id] = pins
            if current and resolver.check_pins(pins).freshness == Freshness.CURRENT:
                formal.update(
                    (
                        receipt.target.ref.qualified_id,
                        receipt.correspondence.informal.ref.qualified_id,
                    )
                )
    return accepted, formal, invalid
