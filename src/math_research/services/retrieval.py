"""Single retrieval entry point for CLI and external adapters."""

import re
from pathlib import Path
from typing import Literal, get_args

from math_research.core.errors import ResearchError
from math_research.ledger.episodes import list_candidates, list_reviews
from math_research.ledger.identity import ScopedIdentityResolver
from math_research.ledger.manifest import Ledger
from math_research.ledger.records import store
from math_research.retrieval.index import IndexDoc, search_documents
from math_research.retrieval.packet import export_context_packet as export_context_packet
from math_research.retrieval.recall import ResearchRecall
from math_research.services.research import list_objects

# Public search surface, audited against Ledger.objects -> projection.list_objects.
# Both lexical and exact identity search can return every emitted ObjectView kind;
# Recall only contributes scores. Dependency placeholders (unresolved), relation
# edges and acceptance history do not become ObjectViews. Keep this explicit rather
# than automatically publishing future internal Ledger kinds as search filters.
SearchKind = Literal[
    "approach",
    "artifact",
    "assumption",
    "branch",
    "claim",
    "counterexample",
    "definition",
    "episode",
    "evidence",
    "experiment",
    "failed_attempt",
    "formal_bundle",
    "gap",
    "known_result",
    "problem",
    "proof",
    "refutation",
    "related_paper",
    "review_report",
    "revision",
    "source",
    "theorem_ref",
    "verification",
    "verification_proof",
]
SEARCH_KINDS = frozenset(get_args(SearchKind))


def search_research(
    state: Path,
    query: str,
    *,
    problem_id: str | None = None,
    kind: str | None = None,
    limit: int = 20,
) -> dict:
    if not query.strip() or len(query) > 4000 or not 1 <= limit <= 100:
        raise ResearchError("Nonempty query <=4000 chars and limit 1..100 required.")
    if kind is not None and kind not in SEARCH_KINDS:
        raise ResearchError(
            f"Unknown research object kind for search: {kind!r}; "
            f"supported kinds: {', '.join(sorted(SEARCH_KINDS))}."
        )
    ledger = Ledger(state)
    before = ledger.source_version(problem_id)
    views = {
        v.object.qualified_id: v
        for v in list_objects(state, problem_id)
        if v.object.ref.kind in SEARCH_KINDS
    }
    exact = None
    identifier = query.strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*-[A-Za-z0-9_.-]+", identifier) or ":" in identifier:
        candidates, reviews = [], []
        for scope in [problem_id] if problem_id else [p.id for p in store.list_dossiers(state)]:
            candidates.extend(list_candidates(state, scope))
            reviews.extend(list_reviews(state, scope))
        resolution = ScopedIdentityResolver(
            (v.object.ref for v in views.values()), candidates, reviews
        ).resolve(identifier, problem_id=problem_id)
        if resolution.ref and resolution.ref.qualified_id in views:
            exact = resolution.ref.qualified_id
    if kind is not None:
        views = {key: v for key, v in views.items() if v.object.ref.kind == kind}
    docs = [
        IndexDoc(
            artifact_id=k,
            artifact_type=v.object.ref.kind,
            title=v.object.record.get("title", v.object.record.get("term", "")),
            text=v.object.full_content,
        )
        for k, v in views.items()
    ]
    lexical = [] if exact else search_documents(docs, query, k=100)
    scores = {doc.artifact_id: 1 / (60 + rank) for rank, (doc, _) in enumerate(lexical, 1)}
    reasons = {key: ["BM25"] for key in scores}
    scopes = [problem_id] if problem_id else [p.id for p in store.list_dossiers(state)]
    kinds = {"failed": "failed_attempt", "provisional": None, "paper": "source"}
    # Reuse scoped intent/currentness/relationship navigation, fused with unified lexical hits.
    for scope in [] if exact else scopes:
        navigation = ResearchRecall(state, scope).find_files(query=query, limit=100)
        for rank, hit in enumerate(navigation.files, 1):
            raw_kind = hit.kind.removeprefix("dossier:")
            hit_kind = kinds.get(raw_kind, raw_kind)
            matches = [
                key
                for key, view in views.items()
                if view.object.ref.problem_id == scope
                and view.object.ref.object_id == hit.artifact_id
                and (hit_kind is None or view.object.ref.kind == hit_kind)
            ]
            if len(matches) == 1:
                key = matches[0]
                scores[key] = scores.get(key, 0) + 1 / (60 + rank)
                reasons.setdefault(key, []).extend(hit.why_relevant)
    if exact and exact in views:
        scores[exact], reasons[exact] = 1.0, ["EXACT_IDENTITY"]
    documents = {d.artifact_id: d for d in docs}
    ranked = sorted(scores, key=lambda key: (-scores[key], key))[:limit]
    hits = [
        {
            "ref": views[key].object.ref.model_dump(),
            "score": scores[key],
            "reasons": list(dict.fromkeys(reasons[key])),
            "content_hash": views[key].object.content_hash,
            "version": views[key].object.version,
            "excerpt": documents[key].text[:1200],
            "authority": views[key].authority,
            "verification": views[key].verification,
            "freshness": views[key].freshness,
            "integrity": views[key].object.integrity,
            "usable_working_premise": views[key].usable_working_premise,
            "trusted_formal_premise": views[key].trusted_formal_premise,
            "premise_eligibility": views[key].premise_eligibility,
            "conditional_premise": views[key].conditional_premise,
            "premise_reasons": views[key].premise_reasons,
            "research_state": views[key].object.research_state,
            "provenance": views[key].object.provenance,
        }
        for key in ranked
    ]
    if ledger.source_version(problem_id) != before:
        raise ResearchError("Research state changed during search; retry.")
    return {
        "source_version": before,
        "retrieval_mode": "EXACT_IDENTITY" if exact else "LEXICAL_RECALL",
        "hits": hits,
    }
