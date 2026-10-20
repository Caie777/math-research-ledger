"""Prepare exact review inputs and ingest advisory external reports."""

from pathlib import Path

from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash
from math_research.core.refs import ObjectRef
from math_research.ledger.manifest import Ledger
from math_research.ledger.persistence import append_once, records
from math_research.verification.models import VersionPin
from math_research.verification.review import ReviewPacket, ReviewReport


def ingest_report_file(state: Path, file: Path) -> ReviewReport:
    return submit_review(state, ReviewReport.model_validate_json(file.read_bytes()))


def prepare_review(state: Path, target: ObjectRef) -> ReviewPacket:
    ledger = Ledger(state)
    before = ledger.source_version(target.problem_id)
    entry = ledger.get(target)
    if target.kind not in {"claim", "gap"}:
        raise ResearchError("Review packet requires an exact Claim/Gap.")
    objects = ledger.objects(target.problem_id)

    def full(e):
        return {
            "ref": e.ref.model_dump(),
            "content_hash": e.content_hash,
            "record": e.record,
            "full_content": e.full_content,
        }

    values = dict(
        target=VersionPin(ref=target, version=entry.version),
        claim=full(entry),
        definitions=tuple(full(e) for e in objects if e.ref.kind == "definition"),
        assumptions=tuple(full(e) for e in objects if e.ref.kind == "assumption"),
        proofs=tuple(
            full(e)
            for e in objects
            if e.ref.kind in {"proof", "refutation"}
            and (
                target.object_id in e.record.get("claim_links", [])
                or e.record.get("target_id") == target.object_id
            )
        ),
        dependencies=tuple(d.model_dump(mode="json") for d in entry.dependencies),
        referenced_results=tuple(
            full(e)
            for e in objects
            if e.ref.kind == "known_result" or any(d.target == e.ref for d in entry.dependencies)
        ),
        provenance=tuple(entry.provenance),
    )
    serial = {**values, "target": values["target"].model_dump(mode="json")}
    if ledger.source_version(target.problem_id) != before:
        raise ResearchError("Research state changed while preparing review packet.")
    return ReviewPacket(**values, source_version=content_hash(serial))


def submit_review(state: Path, report: ReviewReport) -> ReviewReport:
    existing = next(
        (r for r in records(state, "review_reports", ReviewReport) if r.id == report.id), None
    )
    if existing:
        if existing != report:
            raise ResearchError("Review identity already has different content.")
        return existing
    packet = prepare_review(state, report.target.ref)
    if report.target != packet.target or report.packet_version != packet.source_version:
        raise ResearchError(
            "Review packet version changed; retain the report externally and review current inputs."
        )
    return append_once(state, "review_reports", report, key="id")
