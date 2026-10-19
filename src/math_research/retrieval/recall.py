"""PRIMARY read-only facade over existing recall, state and context services.

No new index, memory store, mathematical decision writer or context allocator.
Free-text similarity is always soft; formal conclusions require independent
accepted relations and current canonical witnesses in KnowledgeStateResolver.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from math_research.core.errors import ResearchError
from math_research.memory.archive import source_path
from math_research.memory.episodes import list_candidates, list_episodes
from math_research.memory.records import store
from math_research.memory.records.counterexamples import read_counterexample
from math_research.memory.records.models import (
    Approach,
    ClaimRecord,
    EvidenceRecord,
    FailedAttempt,
    ProofAttempt,
)
from math_research.memory.relations.ledger import active_relations
from math_research.memory.relations.policy import LOGICAL_RELATIONS
from math_research.memory.state import KnowledgeState, KnowledgeStateResolver
from math_research.memory.target import ResearchTarget
from math_research.retrieval.context import (
    QueryPurpose,
    ResearchContextBuilder,
    ResearchContextBundle,
)
from math_research.retrieval.index import (
    IndexDoc,
    gather_documents,
    scoped_memory_documents,
    search_documents,
)
from math_research.retrieval.policy import rank_records
from math_research.retrieval.related_research import (
    MemoryHit,
    RelatedResearch,
    retrieve_related_memory,
)

HistoryClassification = Literal[
    "NEW",
    "PARTIAL_OVERLAP",
    "POSSIBLE_OVERLAP",
    "ALREADY_PROVED",
    "ALREADY_REFUTED",
    "KNOWN_FAILED_ROUTE",
    "CURRENT_OPEN_WORK",
]


class MemoryObjectNotFound(ResearchError):
    """Valid scoped lookup with no readable object; not a storage/permission error."""


class RecallFile(BaseModel):
    artifact_id: str
    kind: str
    path: str | None
    title: str
    why_relevant: list[str]
    state: KnowledgeState
    authority: str
    relation_to_target: list[str] = Field(default_factory=list)
    problem_id: str | None
    problem_scope: list[str]
    provenance: list[str] = Field(default_factory=list)
    conclusion_relation: Literal["PROVES", "REFUTES"] | None = None
    lexical_score: float = 0
    warnings: list[str] = Field(default_factory=list)


class FileSearchResult(BaseModel):
    problem_id: str
    target_id: str | None
    query: str
    cross_problem: bool
    files: list[RecallFile]
    warnings: list[str] = Field(default_factory=list)
    debug_trace: dict | None = Field(default=None, exclude=True)


class HistoryCheckResult(BaseModel):
    classification: HistoryClassification
    basis: Literal["HARD_STATE", "SOFT_OVERLAP", "NO_MATCH"]
    target_id: str | None
    query: str
    canonical_matches: list[RecallFile]
    open_matches: list[RecallFile]
    failed_routes: list[RecallFile]
    counterexamples: list[RecallFile]
    proofs: list[RecallFile]
    source_files: list[RecallFile]
    soft_overlaps: list[RecallFile]
    warnings: list[str]
    recommended_context_ids: list[str]


class ResearchRecall:
    """Find original files, inspect prior work, or build a budgeted Context Bundle."""

    def __init__(self, ot_dir: Path, problem_id: str | None = None):
        self.ot_dir = ot_dir
        self.problem_id = problem_id

    def _scope(self, problem_id: str | None) -> str:
        pid = problem_id or self.problem_id
        if pid is None:
            pointer = self.ot_dir / "problems" / ".current"
            pid = pointer.read_text("utf-8").strip() if pointer.is_file() else None
        if not pid:
            raise ResearchError("Choose a Problem scope before using Recall.")
        store.require_dossier(self.ot_dir, pid)
        return pid

    def read_original_file(
        self,
        artifact_id: str,
        kind: str,
        *,
        problem_id: str | None = None,
        cross_problem: bool = False,
    ) -> tuple[RecallFile, bytes]:
        """Explicit download/read support, resolving scoped IDs rather than user paths."""
        pid = self._scope(problem_id)
        doc = scoped_memory_documents(self.ot_dir, pid).get(f"{kind}:{artifact_id}")
        if doc is None and kind == "dossier:provisional":
            # Accepted aliases stay readable by their original working identity,
            # but are not indexed twice as fresh mathematical output.
            proposal = next(
                (c for c in list_candidates(self.ot_dir, pid) if c.object_id == artifact_id), None
            )
            if proposal:
                doc = IndexDoc(
                    artifact_id=artifact_id,
                    artifact_type=kind,
                    title=proposal.title,
                    text="",
                    problem_id=pid,
                )
        if doc is None and cross_problem and kind == "dossier:episode":
            doc = next(
                (
                    d
                    for d in gather_documents(self.ot_dir)
                    if d.artifact_type == kind
                    and d.artifact_id == artifact_id
                    and d.problem_id is None
                ),
                None,
            )
            if doc:
                file = self._file(
                    None,
                    doc,
                    MemoryHit(
                        object_id=artifact_id,
                        object_type=kind,
                        title=doc.title,
                        excerpt="",
                        retrieval_reasons=[],
                    ),
                    {},
                    None,
                )
                assert file.path is not None
                import hashlib

                content = Path(file.path).read_bytes()
                ep = next(e for e in list_episodes(self.ot_dir) if e.episode_id == artifact_id)
                if hashlib.sha256(content).hexdigest() != ep.content_sha256:
                    raise ResearchError("Archived Episode source SHA mismatch.")
                return file, content
        if doc is None:
            self._validate_absent_source(pid, kind)
            raise MemoryObjectNotFound("Artifact not found in this Problem scope.")
        file = self._file(
            pid,
            doc,
            MemoryHit(
                object_id=artifact_id,
                object_type=kind,
                title=doc.title,
                excerpt="",
                retrieval_reasons=[],
            ),
            KnowledgeStateResolver(self.ot_dir).resolve(pid),
            None,
        )
        if kind == "dossier:provisional":
            candidate = next(
                c for c in list_candidates(self.ot_dir, pid) if c.object_id == artifact_id
            )
            from math_research.memory.episodes import list_reviews

            review = next(
                (
                    r
                    for r in reversed(list_reviews(self.ot_dir, pid))
                    if r.candidate_id == candidate.candidate_id
                ),
                None,
            )
            body = review.reviewed_candidate if review and review.reviewed_candidate else candidate
            return file, body.body.encode("utf-8")
        if file.path is None:
            # Campaign navigation records have no original source reader.
            # A Proof losing its source is instead a genuine storage failure;
            # _file may have retained that failure as a navigation warning.
            if kind in {"campaign:branch", "campaign:obligation"}:
                raise MemoryObjectNotFound("No original file reader for this artifact kind.")
            raise ResearchError("No original file for this artifact.")
        if kind == "dossier:episode":
            from math_research.app.workflows.episodes import episode_source

            episode_source(self.ot_dir, pid, artifact_id)  # source SHA gate
        if kind == "dossier:source":
            from math_research.memory.sources import read_source

            _, _, raw = read_source(self.ot_dir, pid, artifact_id)
            return file, raw
        return file, Path(file.path).read_bytes()

    def _validate_absent_source(self, pid: str, kind: str) -> None:
        """Do not translate a tolerant reader's skipped corrupt row into a miss."""
        sources: dict[str, tuple[str, type[BaseModel]]] = {
            "dossier:claim": ("claims.jsonl", ClaimRecord),
            "dossier:proof": ("proof_attempts/index.jsonl", ProofAttempt),
            "dossier:failed": ("failed_attempts.jsonl", FailedAttempt),
            "dossier:approach": ("approaches.jsonl", Approach),
            "dossier:evidence": ("evidence/index.jsonl", EvidenceRecord),
        }
        if kind not in sources:
            return  # Episode/campaign readers already fail closed on corrupt metadata.
        relative, model = sources[kind]
        try:
            raw = (store.dossier_dir(self.ot_dir, pid) / relative).read_text("utf-8")
        except FileNotFoundError:
            return  # No ledger yet is ordinary absence; other I/O errors propagate.
        for line in raw.splitlines():
            if line.strip():
                model.model_validate_json(line)  # JSON and schema failures remain fatal.

    def _file(
        self,
        pid: str | None,
        doc: IndexDoc,
        hit: MemoryHit,
        states: dict[str, KnowledgeState],
        target_id: str | None,
    ) -> RecallFile:
        ident = doc.artifact_id
        base = store.dossier_dir(self.ot_dir, pid) if pid else self.ot_dir
        state = states.get(
            ident,
            KnowledgeState(
                object_id=ident,
                kind=doc.artifact_type,
                authority="REJECTED/HISTORICAL",
                review="PROVISIONAL",
                research_state="HISTORICAL",
                warnings=["Source/navigation material, not a canonical mathematical premise"],
            ),
        )
        path: Path | None = None
        scope = [pid] if pid else []
        provenance = list(state.provenance)
        warnings = list(doc.caveats)
        role: Literal["PROVES", "REFUTES"] | None = None
        if doc.artifact_type == "dossier:episode":
            ep = next(e for e in list_episodes(self.ot_dir, pid) if e.episode_id == ident)
            path = source_path(self.ot_dir, ep.archive_path)
            state = state.model_copy(update={"thread_ids": ep.thread_ids})
            scope = list(
                dict.fromkeys(
                    [
                        *([ep.primary_problem_id] if ep.primary_problem_id else []),
                        *ep.related_problem_ids,
                    ]
                )
            )
            provenance.extend([ep.episode_id, f"SHA-256:{ep.content_sha256}", ep.provenance or ""])
        elif doc.artifact_type == "dossier:source":
            from math_research.memory.sources import read_source

            assert pid is not None
            try:
                paper, path, _ = read_source(self.ot_dir, pid, ident)
                provenance.extend(["User-supplied raw source", f"SHA-256:{paper.sha256}"])
            except (ResearchError, OSError):
                warnings.append(
                    "Pinned Source unavailable; content excluded. Check workspace doctor."
                )
        elif doc.artifact_type == "dossier:proof":
            assert pid is not None
            proof = next(p for p in store.list_proof_attempts(self.ot_dir, pid) if p.id == ident)
            role = proof.conclusion_relation
            from math_research.app.workflows.episodes import read_full_proof

            try:
                _, path = read_full_proof(self.ot_dir, pid, ident)
            except ResearchError as exc:
                warnings.append(str(exc))
        elif doc.artifact_type == "dossier:counterexample":
            assert pid is not None
            ce = next(c for c in store.list_counterexamples(self.ot_dir, pid) if c.id == ident)
            _, path = read_counterexample(self.ot_dir, ce)
            provenance.extend(ce.source_artifacts)
        else:
            ledger = {
                "dossier:claim": "claims.jsonl",
                "dossier:failed": "failed_attempts.jsonl",
                "dossier:approach": "approaches.jsonl",
                "dossier:evidence": "evidence/index.jsonl",
            }.get(doc.artifact_type)
            if ledger:
                path = base / ledger
        relations = [
            f"{r.source_id} {r.relation} {r.target_id} ({r.label})"
            for r in (active_relations(self.ot_dir, pid) if pid else [])
            if r.relation in LOGICAL_RELATIONS
            and ident in {r.source_id, r.target_id}
            and (
                target_id is None
                or target_id in {r.source_id, r.target_id}
                or r.relation == "INVALIDATES"
            )
        ]
        if doc.artifact_type == "dossier:counterexample" and not any(
            " REFUTES " in r or " INVALIDATES " in r for r in relations
        ):
            relations.append("Counterexample object only; no accepted relation to this target")
        return RecallFile(
            artifact_id=ident,
            kind=doc.artifact_type,
            path=str(path.resolve()) if path else None,
            title=doc.title,
            why_relevant=hit.retrieval_reasons,
            state=state,
            authority=state.authority,
            relation_to_target=relations,
            problem_id=pid,
            problem_scope=scope,
            provenance=list(dict.fromkeys(p for p in provenance if p)),
            conclusion_relation=role,
            lexical_score=hit.retrieval_score,
            warnings=warnings,
        )

    def find_files(
        self,
        target_id: str | None = None,
        *,
        query: str = "",
        problem_id: str | None = None,
        thread_id: str | None = None,
        cross_problem: bool = False,
        limit: int = 50,
        debug: bool = False,
    ) -> FileSearchResult:
        """Return original file references. Limit counts files, never model tokens."""
        pid = self._scope(problem_id)
        # Future callers may pass a proposed mathematical question positionally.
        # ID-shaped typos still fail validation instead of becoming a text query.
        if target_id and not re.fullmatch(r"[A-Z][A-Z0-9_]*(?:-[A-Za-z0-9_]+)+", target_id):
            query = " ".join(part for part in (target_id, query) if part).strip()
            target_id = None
        if not target_id and not query.strip():
            raise ResearchError("Provide a formal target ID or mathematical query.")
        if not 1 <= limit <= 100:
            raise ResearchError("File limit must be between 1 and 100.")
        if thread_id is not None and (not thread_id.strip() or len(thread_id) > 128):
            raise ResearchError("Thread ID must contain 1–128 characters.")
        all_documents = gather_documents(self.ot_dir, problem_id=None if cross_problem else pid)
        docs = scoped_memory_documents(self.ot_dir, pid, documents=all_documents)
        target_doc = next((d for d in docs.values() if d.artifact_id == target_id), None)
        related = (
            retrieve_related_memory(
                self.ot_dir,
                pid,
                target_id,
                query=query,
                recall_limit=100,
                documents=list(docs.values()),
            )
            if target_id
            else None
        )
        query_text = query.strip() or (related.query if related else "")
        scopes = [pid] + (
            [d.id for d in store.list_dossiers(self.ot_dir) if d.id != pid] if cross_problem else []
        )
        files: list[RecallFile] = []
        scores: dict[tuple[str, str], float] = {}
        traces: dict[str, dict] = {}
        for scope in scopes:
            scope_docs = (
                docs
                if scope == pid
                else scoped_memory_documents(self.ot_dir, scope, documents=all_documents)
            )
            states = KnowledgeStateResolver(self.ot_dir).resolve(scope)
            hits = (
                {(h.object_type, h.object_id): h for h in related.hits}
                if related and scope == pid
                else {}
            )
            if scope == pid and target_doc:
                hits[(target_doc.artifact_type, target_doc.artifact_id)] = MemoryHit(
                    object_id=target_doc.artifact_id,
                    object_type=target_doc.artifact_type,
                    title=target_doc.title,
                    excerpt="",
                    retrieval_reasons=["target_record"],
                )
            if not related or scope != pid:
                for doc, score in search_documents(list(scope_docs.values()), query_text, k=100):
                    hits[(doc.artifact_type, doc.artifact_id)] = MemoryHit(
                        object_id=doc.artifact_id,
                        object_type=doc.artifact_type,
                        title=doc.title,
                        excerpt="",
                        retrieval_score=score,
                        retrieval_reasons=["textual"],
                    )
            intent, ranking = rank_records(
                self.ot_dir,
                scope,
                list(scope_docs.values()),
                states,
                query_text,
                anchor_id=target_id if scope == pid else None,
                existing_ids={hit.object_id for hit in hits.values()},
                thread_id=thread_id,
            )
            if debug:
                traces[scope] = dict(
                    intent=intent.model_dump(),
                    records=[
                        dict(
                            record_id=rank.record_id,
                            total_score=rank.score.total_score,
                            score_breakdown=rank.score.model_dump(),
                            relation_expansion=rank.expansion,
                        )
                        for rank in ranking
                    ],
                )
            docs_by_id = {doc.artifact_id: doc for doc in scope_docs.values()}
            for rank in ranking:
                doc = docs_by_id[rank.record_id]
                key = (doc.artifact_type, doc.artifact_id)
                if key not in hits:
                    hits[key] = MemoryHit(
                        object_id=doc.artifact_id,
                        object_type=doc.artifact_type,
                        title=doc.title,
                        excerpt="",
                        retrieval_reasons=rank.reasons,
                    )
                hits[key].retrieval_score = rank.lexical_score
                scores[(scope, rank.record_id)] = rank.score.total_score
            for hit in hits.values():
                scoped_doc = scope_docs.get(f"{hit.object_type}:{hit.object_id}")
                if scoped_doc:
                    files.append(
                        self._file(
                            scope, scoped_doc, hit, states, target_id if scope == pid else None
                        )
                    )
            # A Proposal target is navigation to its full original Episode.
            if scope == pid and target_id and not target_doc:
                candidate = next(
                    c
                    for c in list_candidates(self.ot_dir, pid)
                    if target_id in {c.candidate_id, c.object_id}
                )
                for file in files:
                    if file.artifact_id == candidate.episode_id:
                        file.why_relevant.insert(0, "target_source")

        if cross_problem:
            global_sources = [
                d
                for d in all_documents
                if d.artifact_type == "dossier:episode" and d.problem_id is None
            ]
            for doc, score in search_documents(global_sources, query_text, k=limit):
                files.append(
                    self._file(
                        None,
                        doc,
                        MemoryHit(
                            object_id=doc.artifact_id,
                            object_type=doc.artifact_type,
                            title=doc.title,
                            excerpt="",
                            retrieval_score=score,
                            retrieval_reasons=["textual"],
                        ),
                        {},
                        None,
                    )
                )

        def priority(file: RecallFile) -> tuple[float, int, str, str]:
            return (
                -scores.get((file.problem_id or "", file.artifact_id), file.lexical_score - 4),
                0 if thread_id and thread_id in file.state.thread_ids else 1,
                file.problem_id or "",
                file.artifact_id,
            )

        files.sort(key=priority)
        # A shared global Episode appears once, with all its logical memberships.
        unique: dict[tuple[str, str], RecallFile] = {}
        for file in files:
            key = (
                "" if file.kind == "dossier:episode" else file.problem_id or "",
                file.artifact_id,
            )
            unique.setdefault(key, file)
        return FileSearchResult(
            problem_id=pid,
            target_id=target_id,
            query=query_text,
            cross_problem=cross_problem,
            files=list(unique.values())[:limit],
            debug_trace=traces if debug else None,
        )

    def check_history(
        self,
        target_id: str | None = None,
        *,
        query: str = "",
        problem_id: str | None = None,
        thread_id: str | None = None,
        cross_problem: bool = False,
        limit: int = 50,
    ) -> HistoryCheckResult:
        result = self.find_files(
            target_id,
            query=query,
            problem_id=problem_id,
            thread_id=thread_id,
            cross_problem=cross_problem,
            limit=100,
        )
        pid = result.problem_id
        target_id = result.target_id
        states = KnowledgeStateResolver(self.ot_dir).resolve(pid)
        target = states.get(target_id or "")
        docs = scoped_memory_documents(self.ot_dir, pid)
        proofs = {p.id: p for p in store.list_proof_attempts(self.ot_dir, pid)}
        counterexamples = {c.id: c for c in store.list_counterexamples(self.ot_dir, pid)}
        conclusions: set[str] = set()
        warnings = [
            "Similarity and context recommendations do not authorize STOP, Accept "
            "or a state change."
        ]
        if target and target.authority == "CANONICAL":
            for review in active_relations(self.ot_dir, pid):
                if review.target_id != target_id:
                    continue
                source = states.get(review.source_id or "")
                if not source or source.authority != "CANONICAL" or not source.usable_premise:
                    continue
                if (
                    review.source_id not in target.resolution_ids
                    or review.decision_id not in target.derivation_ids
                ):
                    continue
                proof = proofs.get(review.source_id or "")
                if (
                    review.relation == "PROVES"
                    and proof
                    and proof.conclusion_relation == "PROVES"
                    and target.research_state in {"CURRENT", "RESOLVED"}
                ):
                    from math_research.app.workflows.episodes import read_full_proof

                    try:
                        body, proof_path = read_full_proof(self.ot_dir, pid, proof.id)
                        if not body.strip() or not proof_path.is_relative_to(
                            store.dossier_dir(self.ot_dir, pid).resolve() / "proof_attempts"
                        ):
                            continue
                    except ResearchError:
                        continue
                    conclusions.add("ALREADY_PROVED")
                if (
                    review.relation == "REFUTES"
                    and target.research_state in {"REFUTED", "RESOLVED"}
                    and (
                        review.source_id in counterexamples
                        or proof
                        and proof.conclusion_relation == "REFUTES"
                    )
                ):
                    conclusions.add("ALREADY_REFUTED")
                if review.source_id and not any(
                    f.artifact_id == review.source_id and f.problem_id == pid for f in result.files
                ):
                    doc = next(
                        (d for d in docs.values() if d.artifact_id == review.source_id), None
                    )
                    if doc:
                        result.files.insert(
                            0,
                            self._file(
                                pid,
                                doc,
                                MemoryHit(
                                    object_id=doc.artifact_id,
                                    object_type=doc.artifact_type,
                                    title=doc.title,
                                    excerpt="",
                                    retrieval_reasons=["accepted_resolution_witness"],
                                ),
                                states,
                                target_id,
                            ),
                        )
        files = result.files

        def direct(f: RecallFile) -> bool:
            return (
                target_id is not None
                and f.problem_id == pid
                and any(
                    r in f.why_relevant for r in ("target_record", "hard_neighbor_or_direct_record")
                )
            )

        failed = [
            f
            for f in files
            if direct(f)
            and f.authority == "CANONICAL"
            and (f.kind == "dossier:failed" or f.state.research_state == "INVALIDATED")
        ]
        open_matches = [
            f
            for f in files
            if direct(f) and f.state.research_state in {"OPEN", "PARTIALLY_RESOLVED"}
        ]
        classification: HistoryClassification = "NEW"
        basis: Literal["HARD_STATE", "SOFT_OVERLAP", "NO_MATCH"] = "NO_MATCH"
        if len(conclusions) > 1:
            warnings.append("Conflicting accepted conclusions; Human must inspect both witnesses.")
            classification, basis = "CURRENT_OPEN_WORK", "HARD_STATE"
        elif "ALREADY_REFUTED" in conclusions:
            classification, basis = "ALREADY_REFUTED", "HARD_STATE"
        elif "ALREADY_PROVED" in conclusions:
            classification, basis = "ALREADY_PROVED", "HARD_STATE"
        elif target and target.authority == "CANONICAL" and failed:
            classification, basis = "KNOWN_FAILED_ROUTE", "HARD_STATE"
            warnings.append(
                "A failed/invalidated route does not imply the underlying Claim is false."
            )
        elif (
            target
            and target.authority == "CANONICAL"
            and (open_matches or target.research_state in {"CURRENT", "OPEN", "PARTIALLY_RESOLVED"})
        ):
            classification, basis = "CURRENT_OPEN_WORK", "HARD_STATE"
        elif files:
            classification, basis = "POSSIBLE_OVERLAP", "SOFT_OVERLAP"
            if any(
                " SPECIAL_CASE_OF " in r or " GENERALIZES " in r
                for f in files
                for r in f.relation_to_target
            ):
                classification = "PARTIAL_OVERLAP"
                warnings.append(
                    "Special-case/generalization history is not a proof of this question."
                )
        if not 1 <= limit <= 100:
            raise ResearchError("File limit must be between 1 and 100.")
        return HistoryCheckResult(
            classification=classification,
            basis=basis,
            target_id=target_id,
            query=result.query,
            canonical_matches=[f for f in files if f.authority == "CANONICAL"][:limit],
            open_matches=open_matches[:limit],
            failed_routes=failed[:limit],
            counterexamples=[f for f in files if f.kind == "dossier:counterexample"][:limit],
            proofs=[f for f in files if f.kind == "dossier:proof"][:limit],
            source_files=[f for f in files if f.kind == "dossier:episode"][:limit],
            soft_overlaps=[f for f in files if "textual" in f.why_relevant and not direct(f)][
                :limit
            ],
            warnings=list(
                dict.fromkeys([*warnings, *result.warnings, *(target.warnings if target else [])])
            ),
            recommended_context_ids=list(dict.fromkeys(f.artifact_id for f in files))[:limit],
        )

    def build_context(
        self,
        target: ResearchTarget,
        *,
        purpose: QueryPurpose = "CONTINUE_RESEARCH",
        token_budget: int = 8000,
        thread_id: str | None = None,
        include_provisional: bool = True,
        query: str = "",
        related_memory: RelatedResearch | None = None,
    ) -> ResearchContextBundle:
        """Delegate without changing Bundle selection, accounting or budget policy."""
        if self.problem_id and target.problem_id != self._scope(None):
            raise ResearchError("Target differs from Recall Problem scope.")
        return ResearchContextBuilder(self.ot_dir).build(
            target,
            purpose=purpose,
            token_budget=token_budget,
            thread_id=thread_id,
            include_provisional=include_provisional,
            query=query,
            related_memory=related_memory,
        )
