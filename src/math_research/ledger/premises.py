"""Shared working-premise decisions, separate from byte freshness and human authority."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from math_research.ledger.dependencies import PREMISE_ROLES

if TYPE_CHECKING:
    from math_research.core.refs import ObjectRef
    from math_research.ledger.manifest import ManifestEntry
    from math_research.verification.freshness import FreshnessResult


class PremiseDecision(BaseModel):
    premise_eligibility: Literal["ALLOWED", "CONDITIONAL", "BLOCKED"]
    premise_reasons: list[str] = Field(default_factory=list)

    @property
    def usable_working_premise(self) -> bool:
        # CONDITIONAL material may guide explicitly conditional research, but is
        # never advertised as an unqualified positive premise by this boolean.
        return self.premise_eligibility == "ALLOWED"

    @property
    def conditional_premise(self) -> bool:
        return self.premise_eligibility == "CONDITIONAL"


def semantic_premise(
    kind: str,
    research_state: str,
    authority: str,
    verification: str,
    warnings: list[str] | tuple[str, ...] = (),
) -> PremiseDecision:
    reasons = []
    if authority in {"REJECTED/HISTORICAL", "ADVISORY", "NONE"}:
        reasons.append(f"Authority does not permit a positive premise: {authority}")
    if research_state in {"INVALIDATED", "REFUTED", "SUPERSEDED", "REVISED", "HISTORICAL"}:
        reasons.append(f"Semantic state does not permit a positive premise: {research_state}")
    if kind.lower() in {
        "gap",
        "open_gap",
        "failed_attempt",
        "episode",
        "source",
        "problem",
        "review_report",
        "verification",
        "obligation",
    }:
        reasons.append(f"Not a positive-premise object: {kind}")
    if verification in {"VERIFIER_FAILED", "FAILED"}:
        reasons.append("Verification failed")
    reasons.extend(
        w
        for w in warnings
        if w.startswith(("upstream ", "Unresolved dependency"))
        or w in {"Ledger status: contradicted", "Ledger status: needs_review"}
    )
    if reasons:
        return PremiseDecision(premise_eligibility="BLOCKED", premise_reasons=sorted(set(reasons)))
    if (
        authority == "PROVISIONAL"
        or (
            kind.upper() in {"CONJECTURE", "HEURISTIC", "ASSUMPTION"}
            and authority != "HUMAN_ACCEPTED"
        )
        or any(w.startswith("Conditional upstream assumption:") for w in warnings)
    ):
        return PremiseDecision(
            premise_eligibility="CONDITIONAL",
            premise_reasons=[
                "Explicit conditional research assumption; not an established premise"
            ],
        )
    return PremiseDecision(
        premise_eligibility="ALLOWED",
        premise_reasons=["Working premise only; canonical/current is not proof"],
    )


class PremiseResolver:
    def __init__(self, entries: list[ManifestEntry], *, accepted: set[str] | None = None):
        from math_research.verification.freshness import FreshnessResolver

        self.entries = {e.qualified_id: e for e in entries}
        self.freshness = FreshnessResolver(entries)
        self.accepted = accepted or set()

    def resolve(self, ref: ObjectRef, *, fresh: FreshnessResult | None = None) -> PremiseDecision:
        decisions = []
        seen: set[str] = set()
        queue = [ref]
        while queue and len(seen) < 256:
            current = queue.pop()
            key = current.qualified_id
            if key in seen:
                continue
            seen.add(key)
            entry = self.entries.get(key)
            if entry is None:
                decisions.append(
                    PremiseDecision(
                        premise_eligibility="BLOCKED", premise_reasons=[f"Missing premise: {key}"]
                    )
                )
                continue
            # Old traversal warnings are replaced by this scoped typed traversal.
            # Intrinsic body-integrity failures and ledger status warnings remain.
            warnings = [
                w
                for w in entry.warnings
                if not w.startswith(("upstream ", "Unresolved dependency"))
                or "body integrity" in w
                or "cyclic INVALIDATES" in w
            ]
            decision = semantic_premise(
                entry.record.get("type", entry.ref.kind),
                entry.research_state,
                "HUMAN_ACCEPTED" if key in self.accepted else entry.authority,
                entry.verification,
                warnings,
            )
            if key != ref.qualified_id and decision.premise_eligibility != "ALLOWED":
                decision.premise_reasons = [
                    f"Upstream {key}: {r}" for r in decision.premise_reasons
                ]
            decisions.append(decision)
            queue.extend(e.target for e in entry.dependencies if e.role in PREMISE_ROLES)
        status = fresh if fresh is not None else self.freshness.resolve(ref)
        reasons = []
        if status.freshness != "CURRENT":
            reasons = [f"Freshness {status.freshness}: {r}" for r in status.reasons]
        if queue:
            reasons.append("Premise traversal limit reached")
        blocked = reasons or any(d.premise_eligibility == "BLOCKED" for d in decisions)
        conditional = any(d.premise_eligibility == "CONDITIONAL" for d in decisions)
        if blocked or conditional:
            reasons.extend(
                r
                for d in decisions
                if d.premise_eligibility != "ALLOWED"
                for r in d.premise_reasons
            )
        else:
            reasons = ["Working premise only; canonical/current is not proof"]
        return PremiseDecision(
            premise_eligibility="BLOCKED"
            if blocked
            else "CONDITIONAL"
            if conditional
            else "ALLOWED",
            premise_reasons=sorted(set(reasons)),
        )
