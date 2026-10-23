"""Authority/currentness projection over typed records; no runtime or service imports."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from math_research.core.errors import IntegrityError, ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.manifest import Ledger, ManifestEntry
from math_research.ledger.premises import PremiseResolver


class ObjectView(BaseModel):
    object: ManifestEntry
    freshness: str
    freshness_reasons: list[str]
    authority: str
    verification: str
    usable_working_premise: bool
    trusted_formal_premise: bool
    premise_eligibility: Literal["ALLOWED", "CONDITIONAL", "BLOCKED"]
    conditional_premise: bool
    premise_reasons: list[str]


def list_objects(state: Path, problem_id: str | None = None) -> list[ObjectView]:
    from math_research.ledger.persistence import records
    from math_research.verification.authority import accepted_targets
    from math_research.verification.freshness import Freshness, FreshnessResolver
    from math_research.verification.models import VerificationReceipt

    entries = Ledger(state).objects()
    resolver = FreshnessResolver(entries)
    accepted, formal, invalid = accepted_targets(state, entries)
    premises = PremiseResolver(entries, accepted=set(accepted))
    from math_research.verification.freshness import receipt_current

    checks = records(state, "verifications", VerificationReceipt)
    result = []
    for entry in entries:
        if problem_id and entry.ref.problem_id != problem_id:
            continue
        fresh = resolver.resolve(entry.ref)
        relevant = [
            r
            for r in checks
            if r.target.ref == entry.ref
            and r.target.version == entry.version
            and receipt_current(state, r, entries)
        ]
        verification = (
            "PASSED" if any(r.outcome.status == "PASSED" for r in relevant) else entry.verification
        )
        accepted_here = entry.qualified_id in accepted
        if accepted_here:
            fresh = resolver.check_pins(accepted[entry.qualified_id])
        if entry.qualified_id in invalid:
            fresh.freshness = Freshness.STALE
            fresh.reasons.append("Accepted verification artifact changed or unavailable")
        if entry.qualified_id in formal:
            verification = "PASSED"
        decision = premises.resolve(entry.ref, fresh=fresh)
        result.append(
            ObjectView(
                object=entry,
                freshness=fresh.freshness.value,
                freshness_reasons=fresh.reasons,
                authority="HUMAN_ACCEPTED" if accepted_here else entry.authority,
                verification=verification,
                usable_working_premise=decision.usable_working_premise,
                trusted_formal_premise=entry.qualified_id in formal
                and fresh.freshness == Freshness.CURRENT
                and decision.premise_eligibility != "BLOCKED",
                premise_eligibility=decision.premise_eligibility,
                conditional_premise=decision.conditional_premise,
                premise_reasons=decision.premise_reasons,
            )
        )
    return result


def get_object(state: Path, ref: ObjectRef) -> ObjectView:
    ref = Ledger(state).resolve(ref.qualified_id)
    value = next((v for v in list_objects(state, ref.problem_id) if v.object.ref == ref), None)
    if value is None:
        raise ResearchError(f"Unknown qualified object: {ref.qualified_id}")
    if value.object.integrity == "FAILED":
        raise IntegrityError(f"Source unavailable for {ref.qualified_id}")
    return value
