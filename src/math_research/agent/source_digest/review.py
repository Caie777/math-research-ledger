"""Advisory-to-existing Human Review adapter; never an independent acceptance path."""

import json
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from math_research.agent.source_digest import store
from math_research.agent.source_digest.context import validate_support
from math_research.agent.source_digest.models import (
    DigestRun,
    LocationConfirmation,
    Locator,
    SourceChunk,
    SourceProposal,
)
from math_research.core.atomicio import atomic_write_text, file_lock
from math_research.core.errors import ResearchError
from math_research.core.jsonl import append_jsonl, read_jsonl
from math_research.ledger.episodes import (
    Proposal,
    archive_episode,
    list_candidates,
    list_reviews,
    stage_candidates,
)
from math_research.ledger.records.write_boundary import human_write
from math_research.ledger.sources import read_source

ORIGIN = "source_digest"
EPISODE_PROVENANCE = "SOURCE_DIGEST:"


def _confirmed_support(ot_dir: Path, run: DigestRun, locator: Locator, span: str) -> bool:
    """A human may inspect an omitted page; this never expands the model's context."""
    context = store.read_context(ot_dir, run)
    _, _, raw = read_source(ot_dir, run.problem_id, run.source_id)
    if context.unit == "page":
        if locator.page is None or locator.page > context.total_units:
            return False
        text = PdfReader(BytesIO(raw)).pages[locator.page - 1].extract_text() or ""
        chunk = SourceChunk(chunk_id="HUMAN-LOCATION", page=locator.page, text=text)
    else:
        if (
            locator.line_start is None
            or locator.line_end is None
            or locator.line_start > locator.line_end
            or locator.line_end > context.total_units
        ):
            return False
        text = "".join(
            raw.decode("utf-8-sig").splitlines(keepends=True)[
                locator.line_start - 1 : locator.line_end
            ]
        )
        chunk = SourceChunk(
            chunk_id="HUMAN-LOCATION",
            line_start=locator.line_start,
            line_end=locator.line_end,
            text=text,
        )
    return (
        validate_support(context.model_copy(update={"chunks": [chunk]}), locator, span) == "VALID"
    )


def source_current(ot_dir: Path, run: DigestRun) -> bool:
    try:
        paper, _, _ = read_source(ot_dir, run.problem_id, run.source_id)
        return paper.sha256 == run.source_sha256
    except (ResearchError, OSError):
        return False


def proposals(ot_dir: Path, run: DigestRun) -> list[SourceProposal]:
    if run.digest is None:
        return []
    changes = read_jsonl(
        store.directory(ot_dir, run.digest_id) / "locations.jsonl", LocationConfirmation
    )
    reviews = {r.candidate_id: r for r in list_reviews(ot_dir, run.problem_id)}
    from math_research.ledger.relations.ledger import list_pool

    relation_reviews = {
        p.explicit_candidate_id: p
        for p in list_pool(ot_dir, run.problem_id)
        if p.explicit_candidate_id and p.confirmed_by == "human"
    }
    output = [p.model_copy(deep=True) for p in run.digest.proposals]
    for item in output:
        correction = next((v for v in reversed(changes) if v.proposal_id == item.proposal_id), None)
        if correction:
            item.locator = correction.locator
            item.supporting_span = correction.supporting_span
            item.provenance_status = "VALID"
        decision = reviews.get(item.candidate_id)
        if decision:
            item.review_decision, item.mapped_id = decision.decision, decision.mapped_id
        elif item.proposal_type == "relation" and item.candidate_id in relation_reviews:
            relation = relation_reviews[item.candidate_id]
            if relation.latest_decision and relation.latest_decision.decision == "REJECT":
                item.review_decision = "reject"
            elif relation.active:
                item.review_decision, item.mapped_id = "accept", relation.effective_target_id
    return output


@human_write
def confirm_location(
    ot_dir: Path, run: DigestRun, proposal_id: str, locator: Locator, supporting_span: str
) -> None:
    if not source_current(ot_dir, run):
        raise ResearchError("Source changed/unavailable; inspect the current source before review.")
    item = next((p for p in proposals(ot_dir, run) if p.proposal_id == proposal_id), None)
    if item is None or item.review_decision in {"accept", "reject"}:
        raise ResearchError("Proposal is missing/already reviewed.")
    if item.provenance_status == "INVALID":
        raise ResearchError("Invalid model provenance is quarantined; start a new digest.")
    if len(supporting_span) > 350 or not _confirmed_support(ot_dir, run, locator, supporting_span):
        raise ResearchError("Location/span must match the saved source text exactly.")
    if any(c.candidate_id == item.candidate_id for c in list_candidates(ot_dir, run.problem_id)):
        raise ResearchError("Location already staged; provenance cannot be changed after staging.")
    path = store.directory(ot_dir, run.digest_id) / "locations.jsonl"
    with file_lock(path):
        append_jsonl(
            path,
            LocationConfirmation(
                proposal_id=proposal_id,
                locator=locator,
                supporting_span=supporting_span,
                confirmed_at=datetime.now(UTC),
            ),
        )


@human_write
def stage_for_review(ot_dir: Path, run: DigestRun, proposal_id: str) -> dict[str, str]:
    if run.digest is None or not source_current(ot_dir, run):
        raise ResearchError("A completed digest of the unchanged source is required.")
    items = proposals(ot_dir, run)
    selected = next((p for p in items if p.proposal_id == proposal_id), None)
    if selected is None or selected.provenance_status != "VALID":
        raise ResearchError("Proposal provenance must be confirmed before Human Review.")
    existing = {c.candidate_id for c in list_candidates(ot_dir, run.problem_id)}
    eligible = {
        p.proposal_id
        for p in items
        if p.provenance_status == "VALID"
        and (
            p.relation_to_problem in {"DIRECT", "SUPPORTING"}
            or p.proposal_id == proposal_id
            or p.candidate_id in existing
        )
    }

    def references_ready(item: SourceProposal) -> bool:
        return all(
            not ref or not ref.startswith("SP-") or ref in eligible
            for ref in (item.target_id, item.source_candidate_id)
        )

    if not references_ready(selected):
        raise ResearchError("Review referenced source proposals with valid provenance first.")
    path = store.directory(ot_dir, run.digest_id)
    with file_lock(path / "proposal-pool"):
        snapshot = path / "review-proposals.md"
        if not snapshot.exists():
            # One stable advisory snapshot; corrections remain separate append-only evidence.
            atomic_write_text(
                snapshot, "# Advisory Source Digest\n\n" + run.digest.model_dump_json(indent=2)
            )
        episode = archive_episode(
            ot_dir, run.problem_id, snapshot, provenance=EPISODE_PROVENANCE + run.digest_id
        )
        existing = {c.candidate_id for c in list_candidates(ot_dir, run.problem_id)}
        for item in items:
            if (
                item.provenance_status != "VALID"
                or not references_ready(item)
                or item.candidate_id in existing
                or item.relation_to_problem not in {"DIRECT", "SUPPORTING"}
                and item.proposal_id != proposal_id
            ):
                continue
            assert item.locator is not None
            fields = {
                "origin": ORIGIN,
                "source_id": run.source_id,
                "source_filename": item.source_filename,
                "source_sha256": run.source_sha256,
                "digest_id": run.digest_id,
                "proposal_id": item.proposal_id,
                "locator": item.locator.model_dump_json(),
                "supporting_span": item.supporting_span,
                "confidence": item.confidence,
                "citation_kind": item.citation_kind,
                "relation_to_problem": item.relation_to_problem,
                "possible_duplicate_ids": json.dumps(item.possible_duplicate_ids),
            }
            origin = next(
                (p.candidate_id for p in items if p.proposal_id == item.source_candidate_id),
                item.source_candidate_id,
            )
            candidate = Proposal(
                candidate_id=item.candidate_id,
                episode_id=episode.episode_id,
                problem_id=run.problem_id,
                kind=item.proposal_type,
                title=item.title,
                body=item.statement,
                summary=item.notes,
                target_id=item.target_id,
                relation=item.relation,
                local_id=item.proposal_id,
                source_local_id=item.source_candidate_id,
                origin_candidate_id=origin,
                source_section="Source Digest / " + item.locator.model_dump_json(),
                start_line=1,
                end_line=len(snapshot.read_text("utf-8").splitlines()),
                source_fields=fields,
                source_reported_status=item.citation_kind,
            )
            stage_candidates(ot_dir, run.problem_id, [candidate])
    return {
        "candidate_id": selected.candidate_id,
        "episode_id": episode.episode_id,
        "proposal_id": selected.proposal_id,
        "digest_id": run.digest_id,
    }


def validate_acceptance(ot_dir: Path, candidate: Proposal, edits: dict | None) -> None:
    """Called by existing Review and Relation Review before any canonical write."""
    if candidate.source_fields.get("origin") != ORIGIN:
        return
    run = store.read_run(ot_dir, candidate.source_fields.get("digest_id", ""))
    if run.problem_id != candidate.problem_id or not source_current(ot_dir, run):
        raise ResearchError("Source version changed or scope mismatch; acceptance refused.")
    item = next(
        (p for p in proposals(ot_dir, run) if p.candidate_id == candidate.candidate_id), None
    )
    if item is None or item.provenance_status != "VALID":
        raise ResearchError("Source proposal lacks verified location/span; acceptance refused.")
    if item.confidence == "LOW" and (not edits or not edits.get("body")):
        raise ResearchError("LOW extraction confidence requires Edit before acceptance.")
    if (
        candidate.kind == "relation"
        and candidate.relation == "PROVES"
        and item.citation_kind == "SOURCE_CITES_EXTERNAL"
    ):
        raise ResearchError(
            "A cited external proof cannot establish a source-inspected logical relation."
        )
