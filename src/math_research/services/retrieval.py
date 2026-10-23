"""Single retrieval entry point for CLI and external adapters."""

from pathlib import Path

from math_research.core.errors import ResearchError
from math_research.ledger.manifest import Ledger
from math_research.ledger.records import store
from math_research.retrieval.index import IndexDoc, search_documents
from math_research.retrieval.packet import export_context_packet as export_context_packet
from math_research.retrieval.recall import ResearchRecall
from math_research.services.research import list_objects


def search_research(
    state: Path, query: str, *, problem_id: str | None = None, limit: int = 20
) -> dict:
    if not query.strip() or len(query) > 4000 or not 1 <= limit <= 100:
        raise ResearchError("Nonempty query <=4000 chars and limit 1..100 required.")
    ledger = Ledger(state)
    before = ledger.source_version(problem_id)
    views = {v.object.qualified_id: v for v in list_objects(state, problem_id)}
    docs = [
        IndexDoc(
            artifact_id=k,
            artifact_type=v.object.ref.kind,
            title=v.object.record.get("title", v.object.record.get("term", "")),
            text=v.object.full_content,
        )
        for k, v in views.items()
    ]
    lexical = search_documents(docs, query, k=100)
    scores = {doc.artifact_id: 1 / (60 + rank) for rank, (doc, _) in enumerate(lexical, 1)}
    reasons = {key: ["BM25"] for key in scores}
    scopes = [problem_id] if problem_id else [p.id for p in store.list_dossiers(state)]
    kinds = {"failed": "failed_attempt", "provisional": None, "paper": "source"}
    # Reuse scoped intent/currentness/relationship navigation, fused with unified lexical hits.
    for scope in scopes:
        navigation = ResearchRecall(state, scope).find_files(query=query, limit=100)
        for rank, hit in enumerate(navigation.files, 1):
            raw_kind = hit.kind.removeprefix("dossier:")
            kind = kinds.get(raw_kind, raw_kind)
            matches = [
                key
                for key, view in views.items()
                if view.object.ref.problem_id == scope
                and view.object.ref.object_id == hit.artifact_id
                and (kind is None or view.object.ref.kind == kind)
            ]
            if len(matches) == 1:
                key = matches[0]
                scores[key] = scores.get(key, 0) + 1 / (60 + rank)
                reasons.setdefault(key, []).extend(hit.why_relevant)
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
    return {"source_version": before, "hits": hits}
