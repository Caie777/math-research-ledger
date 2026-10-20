"""Small, read-only consistency check over the existing canonical file stores."""

from __future__ import annotations

from pathlib import Path
from typing import TypeAlias, TypeVar

from pydantic import BaseModel, ValidationError

from math_research.agent.critique import store as critique_store
from math_research.agent.source_digest import store as digest_store
from math_research.agent.state import AgentRun
from math_research.core.errors import ResearchError
from math_research.ledger.episodes import Proposal, ReviewDecision, list_episodes
from math_research.ledger.records import models, store
from math_research.ledger.relations.ledger import decision_history, list_proposals
from math_research.ledger.relations.models import RelationDecision, RelationProposal
from math_research.ledger.source_records import list_papers
from math_research.ledger.sources import read_source, source_papers
from math_research.ledger.target import validate_research_target

RecordT = TypeVar("RecordT", bound=BaseModel)
CanonicalRecord: TypeAlias = (
    models.ClaimRecord
    | models.ProofAttempt
    | models.CounterexampleRecord
    | models.EvidenceRecord
    | models.FailedAttempt
    | models.Approach
)


def _strict_rows(path: Path, model: type[RecordT], key: str | None = "id") -> list[RecordT]:
    if not path.exists():
        return []
    rows: list[RecordT] = []
    seen = set()
    for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = model.model_validate_json(line)
        except ValidationError as exc:
            raise ResearchError(f"Invalid stored row: {path.name}, line {number}") from exc
        if key:
            ident = getattr(row, key)
            if ident in seen:
                raise ResearchError(f"Duplicate {ident} in {path.name}")
            seen.add(ident)
        rows.append(row)
    return rows


def canonical_integrity(ot_dir: Path) -> str:
    """Detect corruption without repairing or promoting any mathematical record."""
    episodes = {e.episode_id for e in list_episodes(ot_dir)}
    paper_ids = {p.id for p in list_papers(ot_dir)}
    count = 0
    for problem in store.list_dossiers(ot_dir):
        base = store.dossier_dir(ot_dir, problem.id)
        objects: dict[str, CanonicalRecord] = {}
        ledgers: tuple[tuple[str, type[CanonicalRecord]], ...] = (
            ("claims.jsonl", models.ClaimRecord),
            ("proof_attempts/index.jsonl", models.ProofAttempt),
            ("counterexamples/index.jsonl", models.CounterexampleRecord),
            ("evidence/index.jsonl", models.EvidenceRecord),
            ("failed_attempts.jsonl", models.FailedAttempt),
            ("approaches.jsonl", models.Approach),
        )
        for relative, model in ledgers:
            for row in _strict_rows(base / relative, model):
                if row.problem_id != problem.id or row.id in objects:
                    raise ResearchError(f"Stored identity mismatch: {row.id}")
                objects[row.id] = row
        count += len(objects)
        for row in objects.values():
            refs = [
                *getattr(row, "depends_on", []),
                *getattr(row, "claim_links", []),
                *getattr(row, "evidence_links", []),
            ]
            for name in ("claim_id", "target_id"):
                ref = getattr(row, name, None)
                if ref:
                    refs.append(ref)
            if any(ref not in objects for ref in refs):
                raise ResearchError(f"Missing canonical target: {row.id}")
            body = getattr(row, "body_path", None)
            if body:
                path = (base / body).resolve()
                if not path.is_relative_to(base.resolve()) or not path.is_file():
                    raise ResearchError(f"Missing/unsafe canonical body: {row.id}")
        for related in _strict_rows(base / "related_papers.jsonl", models.RelatedPaper):
            if related.paper_artifact and related.paper_artifact not in paper_ids:
                raise ResearchError(f"Missing Source: {related.paper_artifact}")
        _strict_rows(base / "archive/episodes/candidates.jsonl", Proposal, "candidate_id")
        reviews = _strict_rows(base / "archive/episodes/reviews.jsonl", ReviewDecision, None)
        for review in reviews:
            if review.episode_id not in episodes:
                raise ResearchError(f"Missing review Episode: {review.candidate_id}")
            if review.decision != "accept":
                continue
            if review.mapped_id and review.mapped_id not in objects:
                raise ResearchError(f"Dangling accepted review: {review.candidate_id}")
            if (
                review.relation
                and review.relation != "NO_LINK"
                and any(ref not in objects for ref in (review.source_id, review.target_id))
            ):
                raise ResearchError(f"Missing reviewed relation target: {review.candidate_id}")
        hard = base / "archive/hard_relations"
        _strict_rows(hard / "pool.jsonl", RelationProposal, "proposal_id")
        _strict_rows(hard / "decisions.jsonl", RelationDecision, "decision_id")
        proposals = {p.proposal_id: p for p in list_proposals(ot_dir, problem.id)}
        for decision in decision_history(ot_dir, problem.id):
            if decision.proposal_id not in proposals:
                raise ResearchError(f"Missing relation proposal: {decision.decision_id}")
        for source in source_papers(ot_dir, problem.id):
            read_source(ot_dir, problem.id, source.id)
    for path in (ot_dir / "research_runs").glob("*/run.json"):
        run = AgentRun.model_validate_json(path.read_text("utf-8"))
        if run.run_id != path.parent.name:
            raise ResearchError("Research run identity mismatch")
        validate_research_target(ot_dir, run.request.target)
        if run.episode_id and run.episode_id not in episodes:
            raise ResearchError("Missing research run Episode")
    for path in (ot_dir / "source_digests").glob("*/request.json"):
        digest_run = digest_store.read_run(ot_dir, path.parent.name)
        digest_store.read_context(ot_dir, digest_run)
        if digest_run.source_id not in paper_ids:
            raise ResearchError("Missing Digest Source")
    for path in (ot_dir / "critiques").glob("*/request.json"):
        critique_run = critique_store.read_run(ot_dir, path.parent.name)
        critique_store.read_bundle(ot_dir, critique_run)
    return f"{count} canonical objects and review/source/run identities checked; no repair"
