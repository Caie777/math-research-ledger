"""Local, offline-first artifact index.

Builds a keyword/BM25 index over project artifacts (memory, claims, papers,
reports, experiments) so the agent can recall the *right* context instead of
dumping everything into the prompt. The index is plain JSONL under
``.math-research/index/`` — inspectable and git-friendly. No network or embeddings
are required; an embeddings backend can be added later behind the same API.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from math_research.core.errors import ResearchError
from math_research.memory.archive import source_path
from math_research.memory.records.evidence_content import render_evidence
from math_research.memory.relations.ledger import active_relations

if TYPE_CHECKING:
    from math_research.retrieval.embeddings import Embedder

ArtifactType = str
_TOKEN_RE = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")
_K1 = 1.5
_B = 0.75
_RRF_K = 60


class IndexDoc(BaseModel):
    artifact_id: str
    artifact_type: ArtifactType
    title: str
    text: str
    problem_id: str | None = None
    record_status: str | None = None
    caveats: list[str] = Field(default_factory=list)


class IndexStatus(BaseModel):
    built: bool
    count: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    built_at: datetime | None = None
    embeddings: bool = False
    embeddings_model: str | None = None


def index_dir(ot_dir: Path) -> Path:
    return ot_dir / "index"


def _docs_path(ot_dir: Path) -> Path:
    return index_dir(ot_dir) / "docs.jsonl"


def _status_path(ot_dir: Path) -> Path:
    return index_dir(ot_dir) / "status.json"


def _vectors_path(ot_dir: Path) -> Path:
    return index_dir(ot_dir) / "vectors.jsonl"


def _tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(normalized):
        word = match.group()
        if "\u3400" <= word[0] <= "\u9fff":
            tokens.extend(word[i : i + 2] for i in range(len(word) - 1))
            if len(word) == 1:
                tokens.append(word)
        else:
            tokens.append(word)
    return tokens


def _read_text(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except (OSError, UnicodeDecodeError):
        return ""


def gather_documents(ot_dir: Path, *, problem_id: str | None = None) -> list[IndexDoc]:
    """Collect indexable documents from all artifact stores (live, not cached)."""
    from math_research.memory.episodes import list_candidates, list_episodes, list_reviews
    from math_research.memory.records import store as dossier_store
    from math_research.memory.source_records import list_papers

    docs: list[IndexDoc] = []

    for paper in list_papers(ot_dir) if problem_id is None else []:
        title = paper.title or paper.source
        body = f"{title} {paper.source}"
        if paper.abstract:
            body += f"\n{paper.abstract}"
        if paper.note_path:
            body += f"\n{_read_text(ot_dir / paper.note_path)}"
        docs.append(
            IndexDoc(
                artifact_id=paper.id,
                artifact_type="paper",
                title=title[:80],
                text=body,
            )
        )

    for dossier in dossier_store.list_dossiers(ot_dir):
        pid = dossier.id
        if problem_id is not None and pid != problem_id:
            continue
        dossier_start = len(docs)
        from math_research.memory.sources import read_source, source_papers

        for source in source_papers(ot_dir, pid):
            caveats = ["Raw source; no mathematical authority."]
            try:
                _, path, raw = read_source(ot_dir, pid, source.id)
                text = raw.decode("utf-8-sig")[:100_000] if path.suffix != ".pdf" else ""
            except (ResearchError, OSError, UnicodeError):
                # Keep navigation metadata, never index unverified source bytes.
                # An unrelated stale Source must not block canonical retrieval.
                text = ""
                caveats.append(
                    "Unavailable pinned Source: integrity/access check failed; content excluded."
                )
            docs.append(
                IndexDoc(
                    artifact_id=source.id,
                    artifact_type="dossier:source",
                    title=source.title or source.source,
                    text=text,
                    problem_id=pid,
                    caveats=caveats,
                )
            )
        for dossier_claim in dossier_store.list_claims(ot_dir, pid):
            docs.append(
                IndexDoc(
                    artifact_id=dossier_claim.id,
                    artifact_type="dossier:claim",
                    title=dossier_claim.statement[:80],
                    text=f"{dossier_claim.statement}\n{dossier_claim.notes}",
                    problem_id=pid,
                    record_status=dossier_claim.status,
                )
            )
        for proof in dossier_store.list_proof_attempts(ot_dir, pid):
            body = (
                _read_text(
                    dossier_store.dossier_dir(ot_dir, pid) / (proof.body_path or ""), 100_000
                )
                if proof.body_path
                else ""
            )
            docs.append(
                IndexDoc(
                    artifact_id=proof.id,
                    artifact_type="dossier:proof",
                    title=proof.title,
                    text=f"{proof.title}\n{body}\n" + "\n".join(proof.gaps),
                    problem_id=pid,
                    record_status=proof.status,
                )
            )
        from math_research.memory.records.counterexamples import read_counterexample

        for counterexample in dossier_store.list_counterexamples(ot_dir, pid):
            body, _ = read_counterexample(ot_dir, counterexample)
            docs.append(
                IndexDoc(
                    artifact_id=counterexample.id,
                    artifact_type="dossier:counterexample",
                    title=counterexample.title or counterexample.id,
                    text=body,
                    problem_id=pid,
                    record_status=counterexample.status,
                )
            )
        for failed in dossier_store.list_failed_attempts(ot_dir, pid):
            docs.append(
                IndexDoc(
                    artifact_id=failed.id,
                    artifact_type="dossier:failed",
                    title=failed.attempted_method,
                    text=f"{failed.attempted_method}\n{failed.summary}\n{failed.reason_failed}",
                    problem_id=pid,
                    record_status="failed_route",
                )
            )
        for evidence in dossier_store.list_evidence(ot_dir, pid):
            docs.append(
                IndexDoc(
                    artifact_id=evidence.id,
                    artifact_type="dossier:evidence",
                    title=evidence.summary[:80],
                    text=render_evidence(evidence),
                    problem_id=pid,
                )
            )
        for approach in dossier_store.list_approaches(ot_dir, pid):
            docs.append(
                IndexDoc(
                    artifact_id=approach.id,
                    artifact_type="dossier:approach",
                    title=approach.objective[:80],
                    text=f"{approach.objective}\n{approach.method}\n{approach.notes}",
                    problem_id=pid,
                )
            )
        reviews_by_candidate = {r.candidate_id: r for r in list_reviews(ot_dir, pid)}
        for proposal in list_candidates(ot_dir, pid):
            if not proposal.object_id:
                continue
            review = reviews_by_candidate.get(proposal.candidate_id)
            if review and review.decision == "accept":
                continue  # The human record is already indexed; do not duplicate cold bodies.
            proposal_snapshot = (review.reviewed_candidate or proposal) if review else proposal
            docs.append(
                IndexDoc(
                    artifact_id=proposal.object_id,
                    artifact_type="dossier:provisional",
                    title=proposal.title,
                    text=proposal_snapshot.body,
                    problem_id=pid,
                    record_status="unverified",
                    caveats=["Working identity; authority comes from KnowledgeStateResolver."],
                )
            )
        for episode in list_episodes(ot_dir, pid):
            if (episode.provenance or "").startswith("SOURCE_DIGEST:"):
                continue  # Advisory review snapshots are not research/source recall material.
            docs.append(
                IndexDoc(
                    artifact_id=episode.episode_id,
                    artifact_type="dossier:episode",
                    title=episode.source_filename,
                    text=_read_text(source_path(ot_dir, episode.archive_path), 100_000),
                    problem_id=pid,
                )
            )

        # Derived cautions accompany retrieval; they never rewrite epistemic
        # status or remove historical objects/source files from the Problem Record.
        by_id = {doc.artifact_id: doc for doc in docs[dossier_start:]}
        for failed in dossier_store.list_failed_attempts(ot_dir, pid):
            for artifact in failed.artifacts:
                doc = by_id.get(artifact)
                if doc and doc.artifact_type == "dossier:proof":
                    doc.caveats.append(
                        f"Known failed attempt {failed.id}: {failed.reason_failed[:500]}"
                    )
        for edge in active_relations(ot_dir, pid):
            if edge.relation in {"REVISES", "SUPERSEDES", "REFUTES", "INVALIDATES"}:
                doc = by_id.get(edge.target_id or "")
                if doc:
                    doc.caveats.append(
                        f"Historical caution: {edge.label} {edge.relation} from "
                        f"{edge.source_id}. Check the replacement/refutation; "
                        "relation confirmation is separate from verification."
                    )
                    if edge.relation == "INVALIDATES":
                        doc.caveats.append("Underlying claim is not thereby refuted.")
        for review in list_reviews(ot_dir, pid):
            if review.decision != "accept":
                continue
            candidate = review.reviewed_candidate
            if candidate and candidate.kind == "proof" and candidate.revises_proof_id:
                doc = by_id.get(candidate.revises_proof_id)
                if doc:
                    doc.caveats.append(
                        f"Historical caution: revised by accepted proof {review.mapped_id}."
                    )
        for doc in docs[dossier_start:]:
            if doc.record_status in {"refuted", "contradicted", "blocked", "abandoned"}:
                doc.caveats.append(f"Problem Record status: {doc.record_status}; consult history.")
            doc.caveats = list(dict.fromkeys(doc.caveats))
            if doc.caveats:
                doc.text = "\n".join(doc.caveats) + "\n\n" + doc.text

    # Global raw sources without a logical Problem membership are available only
    # to an explicit all-scopes query. Never infer ownership from the directory.
    if problem_id is None:
        indexed_sources = {d.artifact_id for d in docs if d.artifact_type == "dossier:episode"}
        for episode in list_episodes(ot_dir):
            if (episode.provenance or "").startswith("SOURCE_DIGEST:"):
                continue
            if episode.episode_id not in indexed_sources:
                docs.append(
                    IndexDoc(
                        artifact_id=episode.episode_id,
                        artifact_type="dossier:episode",
                        title=episode.source_filename,
                        text=_read_text(source_path(ot_dir, episode.archive_path), 100_000),
                    )
                )

    return docs


def scoped_memory_documents(
    ot_dir: Path, problem_id: str, *, documents: list[IndexDoc] | None = None
) -> dict[str, IndexDoc]:
    """Canonical keyed memory view; consumers may reuse a live retrieval snapshot."""
    from math_research.memory.records import store

    store.require_dossier(ot_dir, problem_id)
    docs = documents if documents is not None else gather_documents(ot_dir, problem_id=problem_id)
    return {
        f"{doc.artifact_type}:{doc.artifact_id}": doc
        for doc in docs
        if doc.problem_id == problem_id and doc.artifact_type.startswith(("dossier:", "campaign:"))
    }


def build_index(ot_dir: Path, embedder: Embedder | None = None) -> IndexStatus:
    """Gather all artifacts and persist the index under ``.math-research/index/``.

    When an ``embedder`` is supplied, document vectors are computed and cached so
    later queries only embed the query. Without one, a BM25-only index is built.
    """
    docs = gather_documents(ot_dir)
    index_dir(ot_dir).mkdir(parents=True, exist_ok=True)
    lines = [doc.model_dump_json() for doc in docs]
    _docs_path(ot_dir).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    embeddings_built = False
    model_name: str | None = None
    vectors_file = _vectors_path(ot_dir)
    if embedder is not None and docs:
        vectors = embedder.encode([f"{d.title} {d.text}" for d in docs])
        with vectors_file.open("w", encoding="utf-8") as fh:
            for doc, vec in zip(docs, vectors, strict=True):
                fh.write(json.dumps({"artifact_id": _vector_key(doc), "vector": vec}) + "\n")
        embeddings_built = True
        model_name = getattr(embedder, "model_name", embedder.__class__.__name__)
    elif vectors_file.exists():
        vectors_file.unlink()

    by_type: Counter[str] = Counter(doc.artifact_type for doc in docs)
    status = IndexStatus(
        built=True,
        count=len(docs),
        by_type=dict(sorted(by_type.items())),
        built_at=datetime.now(UTC),
        embeddings=embeddings_built,
        embeddings_model=model_name,
    )
    _status_path(ot_dir).write_text(status.model_dump_json(indent=2), encoding="utf-8")
    return status


def _load_vectors(ot_dir: Path) -> dict[str, list[float]]:
    path = _vectors_path(ot_dir)
    if not path.is_file():
        return {}
    vectors: dict[str, list[float]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            data = json.loads(line)
            vectors[data["artifact_id"]] = data["vector"]
    return vectors


def _vector_key(doc: IndexDoc) -> str:
    return f"{doc.problem_id or '-'}:{doc.artifact_type}:{doc.artifact_id}"


def load_documents(ot_dir: Path) -> list[IndexDoc]:
    """Load the cached index, falling back to a live gather if not yet built."""
    path = _docs_path(ot_dir)
    if not path.is_file():
        return gather_documents(ot_dir)
    docs: list[IndexDoc] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            docs.append(IndexDoc.model_validate_json(line))
    return docs


def index_status(ot_dir: Path) -> IndexStatus:
    path = _status_path(ot_dir)
    if not path.is_file():
        return IndexStatus(built=False)
    return IndexStatus.model_validate_json(path.read_text(encoding="utf-8"))


def _bm25_scores(query_tokens: list[str], doc_tokens: list[list[str]]) -> list[float]:
    n = len(doc_tokens)
    if n == 0:
        return []
    avgdl = sum(len(d) for d in doc_tokens) / n
    df: Counter[str] = Counter()
    for tokens in doc_tokens:
        for term in set(tokens):
            df[term] += 1
    scores = [0.0] * n
    for i, tokens in enumerate(doc_tokens):
        dl = len(tokens) or 1
        tf = Counter(tokens)
        score = 0.0
        for term in query_tokens:
            freq = tf.get(term, 0)
            if not freq:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (freq * (_K1 + 1)) / (freq + _K1 * (1 - _B + _B * dl / avgdl))
        scores[i] = score
    return scores


def search(
    ot_dir: Path, query: str, k: int = 5, *, problem_id: str | None = None
) -> list[tuple[IndexDoc, float]]:
    """Return the top-``k`` (document, score) matches for ``query`` (score > 0)."""
    docs = gather_documents(ot_dir, problem_id=problem_id) if problem_id else load_documents(ot_dir)
    return search_documents(docs, query, k)


def search_documents(docs: list[IndexDoc], query: str, k: int = 5) -> list[tuple[IndexDoc, float]]:
    """Rank an existing snapshot with the same BM25 implementation used by search."""
    if not docs:
        return []
    query_tokens = _tokenize(query)
    doc_tokens = [_tokenize(f"{d.title} {d.text}") for d in docs]
    scores = _bm25_scores(query_tokens, doc_tokens)
    ranked = sorted(zip(docs, scores, strict=True), key=lambda pair: pair[1], reverse=True)
    return [(doc, score) for doc, score in ranked[:k] if score > 0]


def _rrf(orderings: list[list[int]], rrf_k: int = _RRF_K) -> dict[int, float]:
    """Reciprocal-rank fusion: combine ranked index lists into a fused score map."""
    fused: dict[int, float] = {}
    for ordering in orderings:
        for rank, idx in enumerate(ordering, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (rrf_k + rank)
    return fused


def hybrid_search(
    ot_dir: Path,
    query: str,
    k: int = 5,
    *,
    embedder: Embedder | None = None,
    problem_id: str | None = None,
) -> list[tuple[IndexDoc, float]]:
    """Retrieve by BM25 fused with vector similarity (reciprocal-rank fusion).

    Degrades gracefully: with no ``embedder`` (and no usable query vector) this is
    exactly BM25. Document vectors are read from the cache when present, otherwise
    computed on the fly from the supplied embedder.
    """
    docs = gather_documents(ot_dir, problem_id=problem_id) if problem_id else load_documents(ot_dir)
    if not docs:
        return []

    if embedder is None:
        return search_documents(docs, query, k)

    query_tokens = _tokenize(query)
    doc_tokens = [_tokenize(f"{d.title} {d.text}") for d in docs]
    bm25 = _bm25_scores(query_tokens, doc_tokens)

    from math_research.retrieval.embeddings import cosine

    cached = _load_vectors(ot_dir)
    doc_vecs: list[list[float]]
    if all(_vector_key(d) in cached for d in docs) and cached:
        doc_vecs = [cached[_vector_key(d)] for d in docs]
    else:
        doc_vecs = embedder.encode([f"{d.title} {d.text}" for d in docs])
    query_vec = embedder.encode([query])[0]
    sims = [cosine(query_vec, dv) for dv in doc_vecs]

    bm25_order = sorted(range(len(docs)), key=lambda i: bm25[i], reverse=True)
    vec_order = sorted(range(len(docs)), key=lambda i: sims[i], reverse=True)
    fused = _rrf([bm25_order, vec_order])

    ranked_idx = sorted(fused, key=lambda i: fused[i], reverse=True)
    # Keep documents that surface in either signal (positive BM25 or similarity).
    return [(docs[i], fused[i]) for i in ranked_idx[:k] if bm25[i] > 0 or sims[i] > 0]
