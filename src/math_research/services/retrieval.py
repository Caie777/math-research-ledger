"""Single retrieval entry point for CLI and external adapters."""

from pathlib import Path

from math_research.core.errors import ResearchError
from math_research.ledger.manifest import Ledger
from math_research.retrieval.index import IndexDoc, search_documents
from math_research.retrieval.packet import export_context_packet as export_context_packet
from math_research.services.research import list_objects


def search_research(state: Path, query: str, *, problem_id: str | None = None, limit: int = 20) -> dict:
    if not query.strip() or len(query) > 4000 or not 1 <= limit <= 100:
        raise ResearchError("Nonempty query <=4000 chars and limit 1..100 required.")
    ledger = Ledger(state)
    before = ledger.source_version(problem_id)
    views = {v.object.qualified_id: v for v in list_objects(state, problem_id)}
    docs = [IndexDoc(artifact_id=k, artifact_type=v.object.ref.kind, title=v.object.record.get("title", v.object.record.get("term", "")), text=v.object.full_content) for k, v in views.items()]
    hits = [{"ref": views[d.artifact_id].object.ref.model_dump(), "score": score, "content_hash": views[d.artifact_id].object.content_hash, "excerpt": d.text[:1200], "authority": views[d.artifact_id].authority, "verification": views[d.artifact_id].verification, "freshness": views[d.artifact_id].freshness, "research_state": views[d.artifact_id].object.research_state, "provenance": views[d.artifact_id].object.provenance} for d, score in search_documents(docs, query, k=limit)]
    if ledger.source_version(problem_id) != before:
        raise ResearchError("Research state changed during search; retry.")
    return {"source_version": before, "hits": hits}
