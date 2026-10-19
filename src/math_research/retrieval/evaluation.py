"""Offline synthetic retrieval measurement, never a product runtime or authority writer.

Only this module's temporary workspace is ingested. Gold is static fixture data;
rankers receive query text/anchor, never labels. Existing retrieval stays unchanged.
"""

from __future__ import annotations

import hashlib
import math
import random
import re
import tempfile
import time
from collections import Counter, deque
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from math_research.app.maintenance.migration import LEGACY_ROOT
from math_research.core.workspace import init_workspace, workspace_dir
from math_research.memory.episodes import (
    Proposal,
    archive_episode,
    review_candidate,
    stage_candidates,
)
from math_research.memory.records import store
from math_research.memory.relations.ledger import active_relations
from math_research.memory.state import KnowledgeStateResolver
from math_research.memory.target import ResearchTarget
from math_research.retrieval.context import QueryPurpose, ResearchContextBuilder, estimate_tokens
from math_research.retrieval.index import IndexDoc, scoped_memory_documents, search_documents
from math_research.retrieval.recall import ResearchRecall

QueryType = Literal[
    "EXACT",
    "SEMANTIC",
    "DEPENDENCY",
    "OPEN_GAP",
    "FAILED_ROUTE",
    "COUNTEREXAMPLE",
    "CURRENT_STATE",
    "HISTORICAL",
    "MULTI_HOP",
    "AUTHORITY",
]
SYSTEMS = ("Random", "Recency", "Lexical", "Relations", "Current Recall")
CATEGORIES: tuple[QueryType, ...] = (
    "EXACT",
    "SEMANTIC",
    "DEPENDENCY",
    "OPEN_GAP",
    "FAILED_ROUTE",
    "COUNTEREXAMPLE",
    "CURRENT_STATE",
    "HISTORICAL",
    "MULTI_HOP",
    "AUTHORITY",
)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvalQuery(Strict):
    query_id: str
    problem_id: str
    query_type: QueryType
    query_text: str = Field(min_length=1)
    gold_record_ids: list[str] = Field(min_length=1)
    acceptable_record_ids: list[str]
    forbidden_record_ids: list[str]
    notes: str = Field(min_length=1)
    anchor_id: str | None = None
    expected_types: list[str] = Field(default_factory=list)


class ContextEvalCase(Strict):
    case_id: str
    problem_id: str
    target_id: str
    purpose: QueryPurpose
    query: str
    token_budget: int = Field(ge=128, le=200000)
    required_record_ids: list[str] = Field(min_length=1)
    optional_record_ids: list[str]
    forbidden_record_ids: list[str]


class RankRequest(Strict):
    """Label-free input for an optional explicitly enabled online ranker."""

    query_id: str
    problem_id: str
    query_text: str
    anchor_id: str | None


class RecordSpec(Strict):
    id: str
    role: str
    kind: Literal["claim", "gap", "proof", "evidence", "counterexample", "failed_attempt"]
    phase: int = Field(ge=1, le=3)
    body: str
    title: str = ""
    summary: str = ""
    target_id: str | None = None
    uses: list[str] = Field(default_factory=list)


class RelationSpec(Strict):
    source_id: str
    relation: str
    target_id: str


class ProblemSpec(Strict):
    dataset_version: str
    problem_id: str
    title: str
    domain: str
    statement: str
    primary_target_id: str
    records: list[RecordSpec]
    relations: list[RelationSpec]


class Dataset(Strict):
    version: str
    sha256: str
    problems: list[ProblemSpec]
    queries: list[EvalQuery]
    contexts: list[ContextEvalCase]


def load_dataset(path: Path) -> Dataset:
    """Fail closed on malformed labels before any evaluation/model activity."""
    files = [
        *sorted((path / "problems").glob("*.json")),
        path / "queries.jsonl",
        path / "contexts.jsonl",
    ]
    digest = hashlib.sha256()
    for file in files:
        raw = file.read_bytes()
        digest.update(file.relative_to(path).as_posix().encode() + b"\0" + raw + b"\0")
        text = raw.decode("utf-8")
        legacy_guard = rf"[A-Za-z]:[\\/]|/Users/|/home/|{re.escape(LEGACY_ROOT[1:])}|数值半群"
        if re.search(legacy_guard, text, re.I):
            raise ValueError(f"Private path or legacy fixture prohibited: {file.name}")
    problems = [ProblemSpec.model_validate_json(p.read_text("utf-8")) for p in files[:-2]]
    queries = [
        EvalQuery.model_validate_json(row)
        for row in files[-2].read_text("utf-8").splitlines()
        if row.strip()
    ]
    contexts = [
        ContextEvalCase.model_validate_json(row)
        for row in files[-1].read_text("utf-8").splitlines()
        if row.strip()
    ]
    if not 12 <= len(problems) <= 20 or not 80 <= len(queries) <= 120:
        raise ValueError("Expected 12–20 Problems and 80–120 queries.")
    for identifiers in (
        [p.problem_id for p in problems],
        [q.query_id for q in queries],
        [c.case_id for c in contexts],
    ):
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Fixture IDs must be unique within their namespace.")
    versions = {p.dataset_version for p in problems}
    if len(versions) != 1:
        raise ValueError("Mixed dataset versions.")
    counts = Counter(q.query_type for q in queries)
    if any(counts[c] < (15 if c in {"FAILED_ROUTE", "CURRENT_STATE"} else 5) for c in CATEGORIES):
        raise ValueError("Insufficient query category coverage.")
    domains = {p.domain for p in problems}
    if (
        not {
            "number theory",
            "combinatorics",
            "linear algebra",
            "analysis",
            "graph theory",
            "algebra",
            "geometry",
            "probability",
        }
        <= domains
    ):
        raise ValueError("Missing mathematical domain.")
    by_pid = {p.problem_id: p for p in problems}
    for problem in problems:
        ids = [r.id for r in problem.records]
        if len(ids) != len(set(ids)) or problem.primary_target_id not in ids:
            raise ValueError("Duplicate/missing Problem record IDs.")
        for record in problem.records:
            if any(
                ref not in ids
                for ref in [*record.uses, *([record.target_id] if record.target_id else [])]
            ):
                raise ValueError("Dangling record dependency.")
        if any(r.source_id not in ids or r.target_id not in ids for r in problem.relations):
            raise ValueError("Dangling relation.")
    validation_cases: list[EvalQuery | ContextEvalCase] = [*queries, *contexts]
    for case in validation_cases:
        case_problem = by_pid.get(case.problem_id)
        if case_problem is None:
            raise ValueError("Unknown query Problem.")
        case_ids = {r.id for r in case_problem.records}
        if isinstance(case, EvalQuery):
            positive, acceptable, forbidden = (
                case.gold_record_ids,
                case.acceptable_record_ids,
                case.forbidden_record_ids,
            )
            extra = [case.anchor_id] if case.anchor_id else []
            if case.query_type == "CURRENT_STATE" and not forbidden:
                raise ValueError("Current-state cases require stale distractors.")
            if case.query_type in {"DEPENDENCY", "MULTI_HOP"} and not case.anchor_id:
                raise ValueError("Relation cases require an explicit query anchor.")
            kinds = {r.id: r.kind for r in case_problem.records}
            if case.query_type == "FAILED_ROUTE" and any(
                kinds.get(i) != "failed_attempt" for i in positive
            ):
                raise ValueError("Failed-route gold must be a failed attempt.")
        else:
            positive, acceptable, forbidden = (
                case.required_record_ids,
                case.optional_record_ids,
                case.forbidden_record_ids,
            )
            extra = [case.target_id]
        if any(ref not in case_ids for ref in [*positive, *acceptable, *forbidden, *extra]):
            raise ValueError("Unresolvable label ID.")
        if set(positive) & set(forbidden) or set(acceptable) & set(forbidden):
            raise ValueError("Positive and forbidden labels overlap.")
        if any(len(group) != len(set(group)) for group in (positive, acceptable, forbidden)):
            raise ValueError("Duplicate label ID.")
    return Dataset(
        version=versions.pop(),
        sha256=digest.hexdigest(),
        problems=problems,
        queries=queries,
        contexts=contexts,
    )


def ingest_dataset(root: Path, dataset: Dataset) -> Path:
    """Create only a new, empty temporary project, through existing Human Review APIs."""
    if root.exists() and any(root.iterdir()):
        raise ValueError("Synthetic ingestion requires an empty directory.")
    init_workspace(root)
    state = workspace_dir(root)
    for problem in dataset.problems:
        created = store.create_dossier(state, problem.statement, title=problem.title)
        if created.id != problem.problem_id:
            raise ValueError("Fixture Problem ID allocation changed.")
        origins = {}
        for phase in (1, 2, 3):
            records = [r for r in problem.records if r.phase == phase]
            source = root / f"{problem.problem_id}-phase-{phase}.md"
            source.write_text(
                f"# {problem.title}: research phase {phase}\n\n"
                + "\n\n".join(f"## {r.role}\n{r.body}" for r in records),
                encoding="utf-8",
            )
            episode = archive_episode(
                state,
                created.id,
                source,
                now=datetime(2025, 1, phase, tzinfo=UTC),
                provenance="Original synthetic evaluation fixture",
            )
            for record in records:
                proposal = Proposal.model_validate(
                    dict(
                        candidate_id=f"CANDIDATE-{created.id}-{record.role}",
                        episode_id=episode.episode_id,
                        problem_id=created.id,
                        kind=record.kind,
                        title=record.title,
                        body=record.body,
                        summary=record.summary,
                        target_id=record.target_id,
                        uses=record.uses,
                        source_section=record.role,
                        start_line=1,
                        end_line=len(source.read_text("utf-8").splitlines()),
                    )
                )
                stage_candidates(state, created.id, [proposal])
                review = review_candidate(state, created.id, proposal.candidate_id, "accept")
                if review.mapped_id != record.id:
                    raise ValueError(f"Fixture record ID allocation changed: {record.id}")
                origins[record.id] = proposal.candidate_id
        created.primary_claim_id = problem.primary_target_id
        store.save_dossier(state, created)
        for number, relation in enumerate(problem.relations):
            proposal = Proposal.model_validate(
                dict(
                    candidate_id=f"CANDIDATE-{created.id}-REL-{number}",
                    episode_id=episode.episode_id,
                    problem_id=created.id,
                    kind="relation",
                    origin_candidate_id=origins[relation.source_id],
                    relation=relation.relation,
                    target_id=relation.target_id,
                    body="Explicit synthetic human relation",
                    source_section="relations",
                    start_line=1,
                    end_line=1,
                )
            )
            stage_candidates(state, created.id, [proposal])
            review_candidate(state, created.id, proposal.candidate_id, "accept")
    return state


def recall_at(ranking: Iterable[str], gold: Iterable[str], k: int) -> float:
    if k < 1:
        raise ValueError("k must be positive.")
    relevant = set(gold)
    return len(set(list(ranking)[:k]) & relevant) / len(relevant) if relevant else 0.0


def reciprocal_rank(ranking: Iterable[str], gold: Iterable[str]) -> float:
    relevant = set(gold)
    return next(
        (1 / rank for rank, item in enumerate(dict.fromkeys(ranking), 1) if item in relevant), 0.0
    )


def current_state_accuracy(ranking: list[str], gold: list[str], stale: list[str]) -> float:
    positions = {item: rank for rank, item in enumerate(dict.fromkeys(ranking))}
    return float(
        bool(gold)
        and all(item in positions for item in gold)
        and max(positions[item] for item in gold)
        < min((positions.get(item, math.inf) for item in stale), default=math.inf)
    )


def stale_first(ranking: list[str], forbidden: list[str]) -> float:
    return float(bool(ranking) and ranking[0] in forbidden)


def ranking_metrics(
    query: EvalQuery, ranking: list[str], types: dict[str, str]
) -> dict[str, float]:
    ranks = list(dict.fromkeys(ranking))
    result = {f"recall@{k}": recall_at(ranks, query.gold_record_ids, k) for k in (1, 3, 5, 10)}
    result["mrr"] = reciprocal_rank(ranks, query.gold_record_ids)
    if query.query_type == "FAILED_ROUTE":
        result["failed_route_recall@5"] = recall_at(ranks, query.gold_record_ids, 5)
    if query.query_type == "CURRENT_STATE":
        result["current_state_accuracy"] = current_state_accuracy(
            ranks, query.gold_record_ids, query.forbidden_record_ids
        )
        result["stale_first_rate"] = stale_first(ranks, query.forbidden_record_ids)
    if query.expected_types:
        result["authority_type_accuracy"] = float(
            bool(ranks) and types.get(ranks[0]) in query.expected_types
        )
    if query.query_type in {"DEPENDENCY", "MULTI_HOP"}:
        result["relation_hop_recall@5"] = recall_at(ranks, query.gold_record_ids, 5)
    return result


def context_metrics(
    selected: list[str],
    required: list[str],
    acceptable: list[str],
    forbidden: list[str],
    selected_chars: int,
    full_chars: int,
    selected_tokens: int,
    full_tokens: int,
) -> dict[str, float]:
    included = set(selected)
    return dict(
        required_coverage=len(included & set(required)) / len(set(required)) if required else 0.0,
        context_precision=len(included & (set(required) | set(acceptable))) / len(included)
        if included
        else 0.0,
        forbidden_inclusion_rate=len(included & set(forbidden)) / len(included)
        if included
        else 0.0,
        forbidden_case_rate=float(bool(included & set(forbidden))),
        selected_record_count=len(included),
        selected_characters=selected_chars,
        selected_token_estimate=selected_tokens,
        full_characters=full_chars,
        full_token_estimate=full_tokens,
        compression_ratio=selected_chars / full_chars if full_chars else 0.0,
        token_reduction_percent=100 * (1 - selected_tokens / full_tokens) if full_tokens else 0.0,
    )


def average_metrics(rows: list[dict[str, float]]) -> dict[str, float]:
    keys = sorted({key for row in rows for key in row})
    return {key: mean(row[key] for row in rows if key in row) for key in keys}


def latency_summary(values: list[float]) -> dict[str, float]:
    """Nearest-rank percentiles, milliseconds; reports only, never a CI gate."""
    ordered = sorted(values)
    return {
        "mean_ms": mean(ordered) if ordered else 0.0,
        **{
            f"p{int(p * 100)}_ms": ordered[max(0, math.ceil(p * len(ordered)) - 1)]
            if ordered
            else 0.0
            for p in (0.5, 0.95)
        },
    }


def relation_ranking(state: Path, pid: str, anchor: str | None, docs: list[IndexDoc]) -> list[str]:
    """Undirected explicit relation/dependency BFS; no labels, text or status scoring."""
    if anchor is None:
        return []  # No graph seed is inferred from query words or gold.
    adjacency: dict[str, set[str]] = {}

    def edge(a: str, b: str) -> None:
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)

    for relation in active_relations(state, pid):
        edge(relation.source_id, relation.target_id)
    for claim in store.list_claims(state, pid):
        for dependency in claim.depends_on:
            edge(claim.id, dependency)
    for proof in store.list_proof_attempts(state, pid):
        for target in proof.claim_links:
            edge(proof.id, target)
    for failed in store.list_failed_attempts(state, pid):
        for artifact in failed.artifacts:
            if artifact.startswith("PROOF-"):
                edge(failed.id, artifact)
    valid = {d.artifact_id for d in docs}
    distances = {anchor: 0}
    queue = deque([anchor])
    while queue:
        source = queue.popleft()
        for target in sorted(adjacency.get(source, ())):
            if target not in distances:
                distances[target] = distances[source] + 1
                queue.append(target)
    return sorted(valid & distances.keys(), key=lambda item: (distances[item], item))


def snapshot(state: Path) -> dict[str, str]:
    return {
        p.relative_to(state).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(state.rglob("*"))
        if p.is_file()
    }


def evaluate(
    dataset: Dataset,
    *,
    seed: int = 1729,
    query_ids: set[str] | None = None,
    context_ids: set[str] | None = None,
    online_ranker: Callable[[Path, RankRequest], list[str]] | None = None,
) -> dict:
    """Default fully offline. An optional explicitly supplied online adapter is opt-in.

    The adapter can wrap existing rerank_related_memory; it is never constructed or
    called by the default runner/tests. No authority writes are permitted either way.
    """
    started = time.perf_counter()
    cases: list[dict] = []
    context_cases: list[dict] = []
    recall_times: list[float] = []
    context_times: list[float] = []
    queries = [q for q in dataset.queries if query_ids is None or q.query_id in query_ids]
    contexts = [c for c in dataset.contexts if context_ids is None or c.case_id in context_ids]
    if query_ids is not None and len(queries) != len(query_ids):
        raise ValueError("Unknown query subset IDs.")
    if context_ids is not None and len(contexts) != len(context_ids):
        raise ValueError("Unknown context subset IDs.")
    with tempfile.TemporaryDirectory(prefix="math-research-eval-") as temporary:
        state = ingest_dataset(Path(temporary), dataset)
        before = snapshot(state)
        corpus = {
            p.problem_id: list(scoped_memory_documents(state, p.problem_id).values())
            for p in dataset.problems
        }
        for problem in dataset.problems:
            docs = corpus[problem.problem_id]
            available = {d.artifact_id for d in docs}
            if not {r.id for r in problem.records} <= available:
                raise ValueError(
                    "Fixture records are not resolvable by the actual retrieval corpus."
                )
            resolved = KnowledgeStateResolver(state).resolve(problem.problem_id)
            superseded = [r.target_id for r in problem.relations if r.relation == "SUPERSEDES"]
            if any(resolved[item].research_state != "SUPERSEDED" for item in superseded):
                raise ValueError("Fixture historical semantics did not resolve.")
        for query in queries:
            docs = corpus[query.problem_id]
            types = {d.artifact_id: d.artifact_type for d in docs}
            problem = next(p for p in dataset.problems if p.problem_id == query.problem_id)
            chronology = {r.id: (r.phase, position) for position, r in enumerate(problem.records)}
            episodes = sorted(d.artifact_id for d in docs if d.artifact_type == "dossier:episode")
            chronology.update(
                {ident: (position + 1, -1) for position, ident in enumerate(episodes)}
            )
            random_ids = sorted(types)
            keyed_seed = int.from_bytes(
                hashlib.sha256(f"{seed}:{query.query_id}".encode()).digest()[:8], "big"
            )
            random.Random(keyed_seed).shuffle(random_ids)
            rankings = {
                "Random": random_ids,
                "Recency": sorted(
                    types,
                    key=lambda ident: (
                        -chronology.get(ident, (0, 0))[0],
                        -chronology.get(ident, (0, 0))[1],
                        ident,
                    ),
                ),
                "Lexical": [
                    d.artifact_id for d, _ in search_documents(docs, query.query_text, k=100)
                ],
                "Relations": relation_ranking(state, query.problem_id, query.anchor_id, docs),
            }
            instant = time.perf_counter()
            result = ResearchRecall(state, query.problem_id).find_files(
                query.anchor_id, query=query.query_text, limit=100, debug=True
            )
            recall_ms = (time.perf_counter() - instant) * 1000
            recall_times.append(recall_ms)
            rankings["Current Recall"] = [f.artifact_id for f in result.files]
            if online_ranker is not None:
                rankings["Optional online rerank"] = online_ranker(
                    state,
                    RankRequest(
                        query_id=query.query_id,
                        problem_id=query.problem_id,
                        query_text=query.query_text,
                        anchor_id=query.anchor_id,
                    ),
                )
            for system, ranking in rankings.items():
                if len(ranking) != len(set(ranking)) or any(item not in types for item in ranking):
                    raise ValueError(f"Invalid ranking from {system}.")
                cases.append(
                    dict(
                        query_id=query.query_id,
                        problem_id=query.problem_id,
                        query_type=query.query_type,
                        query_text=query.query_text,
                        anchor_id=query.anchor_id,
                        expected_types=query.expected_types,
                        notes=query.notes,
                        system=system,
                        ranking=ranking,
                        gold_record_ids=query.gold_record_ids,
                        acceptable_record_ids=query.acceptable_record_ids,
                        forbidden_record_ids=query.forbidden_record_ids,
                        metrics=ranking_metrics(query, ranking, types),
                        latency_ms=recall_ms if system == "Current Recall" else None,
                        trace=result.debug_trace if system == "Current Recall" else None,
                    )
                )
        for case in contexts:
            instant = time.perf_counter()
            bundle = ResearchContextBuilder(state).build(
                ResearchTarget(kind="claim", problem_id=case.problem_id, node_id=case.target_id),
                purpose=case.purpose,
                query=case.query,
                token_budget=case.token_budget,
                include_provisional=False,
            )
            elapsed = (time.perf_counter() - instant) * 1000
            context_times.append(elapsed)
            selected = list(dict.fromkeys(item.object_id for item in bundle.items))
            # Same indexed corpus for every system. Includes historical records and
            # original Episode text once each; not a provider transcript/token bill.
            full = "\n\n".join(
                f"{doc.artifact_id} {doc.artifact_type}\n{doc.text}"
                for doc in corpus[case.problem_id]
            )
            metrics = context_metrics(
                selected,
                case.required_record_ids,
                case.optional_record_ids,
                case.forbidden_record_ids,
                len(bundle.markdown),
                len(full),
                bundle.token_estimate,
                estimate_tokens(full),
            )
            full_ids = {i.object_id for i in bundle.items if i.full_text}
            metrics["required_full_text_coverage"] = len(
                full_ids & set(case.required_record_ids)
            ) / len(case.required_record_ids)
            metrics["forbidden_positive_premise_count"] = sum(
                item.object_id in case.forbidden_record_ids and item.state.usable_premise
                for item in bundle.items
            )
            context_cases.append(
                dict(
                    case_id=case.case_id,
                    problem_id=case.problem_id,
                    purpose=case.purpose,
                    target_id=case.target_id,
                    query=case.query,
                    token_budget=case.token_budget,
                    required_record_ids=case.required_record_ids,
                    optional_record_ids=case.optional_record_ids,
                    forbidden_record_ids=case.forbidden_record_ids,
                    selected_ids=selected,
                    forbidden_selected_ids=sorted(set(selected) & set(case.forbidden_record_ids)),
                    required_missing_ids=sorted(set(case.required_record_ids) - set(selected)),
                    complete=bundle.complete,
                    required_context_truncated=bundle.required_context_truncated,
                    metrics=metrics,
                    latency_ms=elapsed,
                )
            )
        if snapshot(state) != before:
            raise AssertionError("Evaluation mutated synthetic mathematical authority/state.")
    systems = list(SYSTEMS) + (["Optional online rerank"] if online_ranker else [])
    aggregate = {
        system: average_metrics([c["metrics"] for c in cases if c["system"] == system])
        for system in systems
    }
    categories = {
        system: {
            category: average_metrics(
                [
                    c["metrics"]
                    for c in cases
                    if c["system"] == system and c["query_type"] == category
                ]
            )
            for category in CATEGORIES
        }
        for system in systems
    }
    return dict(
        version="1.0",
        dataset_version=dataset.version,
        dataset_hash=dataset.sha256,
        timestamp=datetime.now(UTC).isoformat(),
        systems=systems,
        config=dict(
            seed=seed,
            recall_policy="v2 deterministic intent/state/relation scoring",
            offline=online_ranker is None,
            semantic_rerank="disabled" if online_ranker is None else "explicit online adapter",
            recall_limit=100,
            context_estimator="ceil(UTF-8 bytes / 3)",
            recency="static fixture phase/creation order; descending, ID ties",
            relevance="Recall/MRR use gold only; acceptable IDs carry no ranking credit",
            graph=(
                "explicit anchor; undirected relations/dependencies, proof links and "
                "failed-proof provenance; no unconnected fallback"
            ),
            context_size_reference=(
                "all scoped indexed record and Episode text, including history; no agent trajectory"
            ),
        ),
        dataset=dict(
            problem_count=len(dataset.problems),
            query_count=len(queries),
            context_count=len(contexts),
            category_counts=dict(sorted(Counter(q.query_type for q in queries).items())),
        ),
        aggregate_metrics=aggregate,
        category_metrics=categories,
        context_metrics=average_metrics([c["metrics"] for c in context_cases]),
        context_purpose_metrics={
            purpose: average_metrics(
                [c["metrics"] for c in context_cases if c["purpose"] == purpose]
            )
            for purpose in sorted({c["purpose"] for c in context_cases})
        },
        latency=dict(
            recall=latency_summary(recall_times),
            context=latency_summary(context_times),
            total_seconds=time.perf_counter() - started,
        ),
        state_integrity="unchanged",
        cases=cases,
        context_cases=context_cases,
    )


def print_summary(report: dict) -> None:
    print("System           R@1    R@3    R@5   R@10    MRR  Failed@5  StaleFirst")
    for system in report["systems"]:
        values = report["aggregate_metrics"][system]
        print(
            f"{system:16} "
            + " ".join(
                f"{values.get(key, 0):6.3f}"
                for key in (
                    "recall@1",
                    "recall@3",
                    "recall@5",
                    "recall@10",
                    "mrr",
                    "failed_route_recall@5",
                    "stale_first_rate",
                )
            )
        )
    context = report["context_metrics"]
    print(
        f"Context coverage={context.get('required_coverage', 0):.3f} "
        f"precision={context.get('context_precision', 0):.3f} "
        f"forbidden={context.get('forbidden_inclusion_rate', 0):.3f}"
    )
    print(
        f"Compression={context.get('compression_ratio', 0):.3f}; "
        f"estimated token reduction={context.get('token_reduction_percent', 0):.1f}%"
    )
    for kind in ("recall", "context"):
        print(f"{kind} latency (ms): {report['latency'][kind]}")
    print(f"Total: {report['latency']['total_seconds']:.2f}s; dataset {report['dataset_hash']}")
