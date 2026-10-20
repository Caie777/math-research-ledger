"""Read-compatible guards for saved source-digest proposals; no model runtime."""

import json
import re
from pathlib import Path

from math_research.core.errors import ResearchError
from math_research.ledger.episodes import Proposal
from math_research.ledger.sources import read_source


def validate_acceptance(ot_dir: Path, candidate: Proposal, edits: dict | None) -> None:
    if candidate.source_fields.get("origin") != "source_digest":
        return
    ident = candidate.source_fields.get("digest_id", "")
    if not re.fullmatch(r"DIGEST-[A-F0-9]{16}", ident):
        raise ResearchError("Invalid saved source digest identity.")
    base = ot_dir.resolve() / "source_digests" / ident
    if not base.resolve().is_relative_to(ot_dir.resolve()):
        raise ResearchError("Source digest storage escapes workspace.")
    try:
        request = json.loads((base / "request.json").read_text("utf-8"))
        digest = json.loads((base / "digest.json").read_text("utf-8"))
        paper, _, _ = read_source(ot_dir, candidate.problem_id, request["source_id"])
        if any(
            request.get(key) != digest.get(key)
            for key in ("digest_id", "problem_id", "source_id", "source_sha256")
        ) or request["problem_id"] != candidate.problem_id or paper.sha256 != request["source_sha256"]:
            raise ResearchError("Source version changed or scope mismatch.")
        item = next(p for p in digest["proposals"] if p["candidate_id"] == candidate.candidate_id)
        confirmed = False
        locations = base / "locations.jsonl"
        if locations.is_file():
            confirmed = any(
                json.loads(line).get("proposal_id") == item["proposal_id"]
                for line in locations.read_text("utf-8").splitlines() if line.strip()
            )
        if item.get("provenance_status") != "VALID" and not confirmed:
            raise ResearchError("Source proposal lacks confirmed provenance.")
        if item.get("provenance_status") == "INVALID":
            raise ResearchError("Invalid source provenance remains quarantined.")
        if item.get("confidence") == "LOW" and not (edits or {}).get("body"):
            raise ResearchError("LOW extraction confidence requires an edited body.")
        if candidate.relation == "PROVES" and item.get("citation_kind") == "SOURCE_CITES_EXTERNAL":
            raise ResearchError("External citation is not a source-inspected proof.")
    except (OSError, KeyError, StopIteration, ValueError) as exc:
        raise ResearchError("Saved source review evidence unavailable or malformed.") from exc
