"""One read-only identity contract over existing records and review mappings.

No persisted alias database and no inference from mathematical prose. Local names
always need an Episode scope. A rejected/deferred proposal keeps its working identity.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef

if TYPE_CHECKING:
    from math_research.ledger.episodes import Proposal, ReviewDecision

LOCAL_ID = re.compile(
    r"^(?:RESULT|PROOF|GAP|EVIDENCE|COUNTEREXAMPLE|REFUTATION|REVISION|FAILED-ATTEMPT|BRANCH)-\d+$"
)
# Qualified alternatives come first so explicit fields never lose their scope.
REFERENCE_TOKEN = re.compile(
    r"[A-Za-z0-9_][A-Za-z0-9_.-]*:[a-z][a-z_]*:[A-Za-z0-9][A-Za-z0-9_.-]*"
    r"|(?:RESULT|PROOF|GAP|EVIDENCE|COUNTEREXAMPLE|REFUTATION|REVISION|FAILED-ATTEMPT|"
    r"BRANCH|CLAIM|APPROACH|APPR|CANDIDATE|DEF|ASSUMPTION|KNOWN)-[A-Za-z0-9]+"
)


def reference_tokens(text: str) -> list[str]:
    """Read IDs only inside an explicitly labelled reference field."""
    return list(dict.fromkeys(REFERENCE_TOKEN.findall(text)))


def working_ref(candidate: Proposal) -> ObjectRef:
    return ObjectRef(
        problem_id=candidate.problem_id,
        kind=candidate.kind,
        object_id=candidate.object_id or candidate.candidate_id,
    )


class IdentityResolution(BaseModel):
    reference: str
    ref: ObjectRef | None = None
    reason: str | None = None
    aliases: list[str] = Field(default_factory=list)

    def require(self) -> ObjectRef:
        if self.ref is None:
            raise ResearchError(
                f"Reference absent or ambiguous: {self.reference} ({self.reason}); "
                "supply a qualified ref and Episode context for local IDs."
            )
        return self.ref


class ScopedIdentityResolver:
    def __init__(
        self,
        refs: Iterable[ObjectRef],
        candidates: Iterable[Proposal] = (),
        reviews: Iterable[ReviewDecision] = (),
    ):
        self.refs = {r.qualified_id: r for r in refs}
        self.bare: dict[tuple[str | None, str], set[ObjectRef]] = defaultdict(set)
        self.aliases: dict[str, set[ObjectRef]] = defaultdict(set)
        self.locals: dict[tuple[str, str, str], set[ObjectRef]] = defaultdict(set)
        self.broken: dict[tuple[str, str], str] = {}
        for r in self.refs.values():
            self.bare[r.problem_id, r.object_id].add(r)
        latest = {(r.problem_id, r.candidate_id): r for r in reviews}
        for candidate in candidates:
            if candidate.kind == "relation":
                continue
            old = working_ref(candidate)
            review = latest.get((candidate.problem_id, candidate.candidate_id))
            if review and review.decision == "accept" and review.mapped_id:
                matches = self.bare[candidate.problem_id, review.mapped_id]
                if len(matches) != 1:
                    for name in (candidate.candidate_id, old.object_id):
                        self.broken[candidate.problem_id, name] = "REVIEW_TARGET_MISSING"
                    continue
                target = next(iter(matches))
            else:
                # Respect the supplied object snapshot, including kind filters.
                # An alias cannot manufacture an object absent from that snapshot.
                if old.qualified_id not in self.refs:
                    continue
                target = self.refs[old.qualified_id]
            for name in {candidate.candidate_id, old.object_id}:
                self.bare[candidate.problem_id, name].add(target)
                alias = old.model_copy(update={"object_id": name}).qualified_id
                self.aliases[alias].add(target)
            if candidate.local_id:
                self.locals[candidate.problem_id, candidate.episode_id, candidate.local_id].add(
                    target
                )

    @classmethod
    def from_state(cls, state: Path) -> ScopedIdentityResolver:
        """Read record identities, never materialize Ledger or recurse into state projections."""
        from math_research.ledger.episodes import list_candidates, list_reviews
        from math_research.ledger.records import store

        refs, candidates, reviews = [], [], []
        readers = (
            ("claim", store.list_claims),
            ("proof", store.list_proof_attempts),
            ("definition", store.list_definitions),
            ("assumption", store.list_assumptions),
            ("known_result", store.list_known_results),
            ("evidence", store.list_evidence),
            ("counterexample", store.list_counterexamples),
            ("failed_attempt", store.list_failed_attempts),
            ("approach", store.list_approaches),
        )
        for problem in store.list_dossiers(state):
            for kind, reader in readers:
                for row in reader(state, problem.id):
                    refs.append(
                        ObjectRef(
                            problem_id=problem.id,
                            kind="gap" if getattr(row, "type", None) == "OPEN_GAP" else kind,
                            object_id=row.id,
                        )
                    )
            rows = list_candidates(state, problem.id)
            decisions = list_reviews(state, problem.id)
            accepted = {r.candidate_id for r in decisions if r.decision == "accept"}
            refs.extend(
                working_ref(c)
                for c in rows
                if c.kind != "relation" and c.candidate_id not in accepted
            )
            candidates.extend(rows)
            reviews.extend(decisions)
        return cls(refs, candidates, reviews)

    def resolve(
        self, reference: str, *, problem_id: str | None = None, episode_id: str | None = None
    ) -> IdentityResolution:
        result = IdentityResolution(reference=reference)
        if ":" in reference:
            try:
                requested = ObjectRef.parse(reference)
            except ValueError:
                result.reason = "MALFORMED_REFERENCE"
                return result
            direct = self.refs.get(requested.qualified_id)
            matches = {direct} if direct else self.aliases.get(requested.qualified_id, set())
        elif (
            problem_id is not None
            and episode_id is not None
            and (problem_id, episode_id, reference) in self.locals
        ):
            matches = self.locals[problem_id, episode_id, reference]
        elif LOCAL_ID.fullmatch(reference) and not (
            self.bare.get((problem_id, reference))
            if problem_id is not None
            else any(name == reference for _, name in self.bare)
        ):
            result.reason = (
                "MISSING_LOCAL_OBJECT"
                if problem_id is not None and episode_id is not None
                else "EPISODE_CONTEXT_REQUIRED"
            )
            return result
        else:
            if problem_id is not None:
                matches = self.bare.get((problem_id, reference), set())
            else:
                matches = {
                    r for (_, name), refs in self.bare.items() if name == reference for r in refs
                }
            if not matches and problem_id is not None:
                result.reason = self.broken.get((problem_id, reference))
        if len(matches) == 1:
            result.ref = next(iter(matches))
            if reference != result.ref.qualified_id:
                result.aliases = [reference, result.ref.qualified_id]
        elif len(matches) > 1:
            result.reason = "SCOPE_AMBIGUITY"
        elif result.reason is None:
            result.reason = "MISSING_OBJECT"
        return result
