"""Validated, bounded model capabilities over deterministic services only."""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from math_research.core.errors import ResearchError
from math_research.ledger.manifest import Ledger
from math_research.ledger.records.write_boundary import automated_scope
from math_research.services.acceptance import request_acceptance
from math_research.services.ingest import ingest_episode, save_note
from math_research.services.research import get_object, status
from math_research.services.retrieval import export_context_packet, search_research
from math_research.services.review import prepare_review
from math_research.services.stale import stale_report

MAX_OUTPUT_BYTES = 64 * 1024
ProblemId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PageArgs(Arguments):
    problem_id: ProblemId | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)


class SearchArgs(Arguments):
    query: str = Field(min_length=1, max_length=4000)
    problem_id: ProblemId | None = None
    limit: int = Field(default=20, ge=1, le=50)


class RefArgs(Arguments):
    ref: str = Field(min_length=1, max_length=400, description="Qualified problem:kind:object ID")


class ObjectArgs(RefArgs):
    offset: int = Field(default=0, ge=0)
    length: int = Field(default=4000, ge=1, le=8000)


class ContextArgs(RefArgs):
    query: str = Field(default="", max_length=4000)
    token_budget: int = Field(default=8000, ge=256, le=16000)
    purpose: Literal["CONTINUE_RESEARCH", "RECOVER_PROOF", "TRACE_HISTORY", "FIND_FAILURES"] = (
        "CONTINUE_RESEARCH"
    )


class RequestArgs(RefArgs):
    verification_id: str = Field(min_length=1, max_length=128)


class EpisodeArgs(Arguments):
    problem_id: ProblemId
    markdown: str = Field(min_length=1, max_length=128000)
    provenance: str = Field(min_length=1, max_length=1000)


class NoteArgs(Arguments):
    problem_id: ProblemId
    kind: Literal["claim", "gap", "failed_attempt", "evidence", "counterexample"]
    title: str = Field(min_length=1, max_length=300, pattern=r"^[^\r\n]+$")
    body: str = Field(min_length=1, max_length=32000)
    provenance: str = Field(min_length=1, max_length=1000)


SCHEMAS: dict[str, type[BaseModel]] = {
    "research_status": PageArgs,
    "research_search": SearchArgs,
    "research_get_object": ObjectArgs,
    "research_context_packet": ContextArgs,
    "research_review_packet": RefArgs,
    "research_stale_report": PageArgs,
    "research_ingest_episode": EpisodeArgs,
    "research_save_note": NoteArgs,
    "research_request_acceptance": RequestArgs,
}

DESCRIPTIONS = {
    "research_status": (
        "Call first when continuing long-running research or asked where an existing Problem "
        "stands. Returns paginated Problem/object references and authority/check/freshness "
        "summaries. Follow with research_context_packet before substantial work. Do not use "
        "as full research context or as a substitute for checking original statements."
    ),
    "research_search": (
        "Find prior results, gaps and failed routes by keywords before doing overlapping work. "
        "Returns ranked scoped hits with provenance and trust labels. Do not treat a search "
        "excerpt as an accepted premise; load the object/context before relying on it."
    ),
    "research_get_object": (
        "Read an existing qualified research object or continue an omitted body. Returns a "
        "bounded text window, version, provenance, authority and freshness. Page with offset "
        "and length. Do not use for arbitrary filesystem paths or whole-Problem context."
    ),
    "research_context_packet": (
        "Load bounded current research context for an existing problem/claim/gap before "
        "starting or resuming substantial research. Returns provenance/trust/freshness labels "
        "and explicit missing/truncated mandatory material. Normally call once near the start "
        "of a research run, not every turn. Do not assume omitted material was checked."
    ),
    "research_review_packet": (
        "Prepare an existing exact Claim/Gap for independent soft review. Returns version-pinned "
        "full claim, definitions, assumptions, proofs and dependency/provenance information. "
        "Read-only and advisory: never grants authority. Do not use for acceptance or broad "
        "orientation; oversized packets return a bounded error rather than losing review inputs."
    ),
    "research_stale_report": (
        "Inspect drift before reusing old checks or pending acceptance requests. Returns paginated "
        "stale objects/verification/acceptance summaries and totals. Does not recheck, invalidate "
        "or accept anything. Do not interpret absence of staleness as verification."
    ),
    "research_ingest_episode": (
        "Save a completed research run as complete UTF-8 Research Episode Markdown "
        "with provenance. "
        "Stages provisional candidates in the existing archive/Proposal Store; repeated identical "
        "content reuses identities. Returns candidate references, counts and omissions, not full "
        "bodies. Do not send fragments, promote facts, run checks or request human acceptance here."
    ),
    "research_save_note": (
        "Preserve one complete useful Claim, Gap, FailedAttempt, Evidence or Counterexample with "
        "provenance. Stages a single provisional Episode candidate in the existing Proposal Store "
        "and returns its identity; duplicate content is idempotent. Do not use for a multi-section "
        "research run, arbitrary notes/files, canonicalization or granting authority."
    ),
    "research_request_acceptance": (
        "Create a pending human review request only after an existing current PASSED hard "
        "verification receipt. Returns an idempotent request pinned to exact versions. Checked "
        "is not accepted; MCP cannot accept. Do not call for soft reviews, unchecked results, "
        "stale receipts or automatic promotion."
    ),
}


def _ingest_summary(value: dict) -> dict:
    candidates = value["candidates"]
    return {
        "episode_id": value["episode"]["episode_id"],
        "duplicate": value["duplicate"],
        "canonical_records_created": 0,
        "authority": "PROVISIONAL",
        "candidate_count": len(candidates),
        "candidates": [
            {key: c[key] for key in ("candidate_id", "object_id", "kind", "problem_id")}
            for c in candidates[:20]
        ],
        "candidates_omitted": max(0, len(candidates) - 20),
    }


class LedgerAdapter:
    def __init__(self, state: Path):
        self.state = state

    def call(self, name: str, arguments: dict) -> dict:
        schema = SCHEMAS.get(name)
        if schema is None:
            raise ResearchError("Tool is not exposed. Human acceptance is never a model tool.")
        args = schema.model_validate(arguments)
        with automated_scope():
            ref = Ledger(self.state).resolve(args.ref) if isinstance(args, RefArgs) else None
            if name == "research_status":
                result = status(self.state, **args.model_dump())
            elif isinstance(args, SearchArgs):
                result = search_research(self.state, **args.model_dump())
            elif isinstance(args, ObjectArgs):
                assert ref is not None
                view = get_object(self.state, ref)
                entry = view.object
                text = entry.full_content
                result = {
                    "ref": entry.qualified_id,
                    "content_hash": entry.content_hash,
                    "version": entry.version,
                    "authority": view.authority,
                    "verification": view.verification,
                    "freshness": view.freshness,
                    "research_state": entry.research_state,
                    "provenance": entry.provenance[:20],
                    "provenance_omitted": max(0, len(entry.provenance) - 20),
                    "content": text[args.offset : args.offset + args.length],
                    "offset": args.offset,
                    "total_characters": len(text),
                    "truncated": args.offset > 0 or args.offset + args.length < len(text),
                }
            elif isinstance(args, ContextArgs):
                assert ref is not None
                result = export_context_packet(
                    self.state, ref, **args.model_dump(exclude={"ref"})
                ).model_dump(mode="json")
            elif isinstance(args, RequestArgs):
                assert ref is not None
                result = request_acceptance(self.state, ref, args.verification_id).model_dump(
                    mode="json"
                )
            elif name == "research_review_packet":
                assert ref is not None
                result = prepare_review(self.state, ref).model_dump(mode="json")
            elif isinstance(args, PageArgs):
                report = stale_report(self.state, args.problem_id)
                result = {
                    "source_version": report["source_version"],
                    **{
                        key: values[args.offset : args.offset + args.limit]
                        for key, values in report.items()
                        if isinstance(values, list)
                    },
                    "totals": {
                        key: len(values)
                        for key, values in report.items()
                        if isinstance(values, list)
                    },
                    "offset": args.offset,
                    "limit": args.limit,
                    "truncated": args.offset > 0
                    or any(
                        len(v) > args.offset + args.limit
                        for v in report.values()
                        if isinstance(v, list)
                    ),
                }
            elif isinstance(args, EpisodeArgs):
                result = _ingest_summary(
                    ingest_episode(
                        self.state,
                        args.problem_id,
                        "research-episode.md",
                        args.markdown.encode("utf-8"),
                        provenance=args.provenance,
                    )
                )
            elif isinstance(args, NoteArgs):
                result = _ingest_summary(save_note(self.state, **args.model_dump()))
            else:
                raise ResearchError("Unsupported validated tool arguments.")
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise ResearchError("Bounded output exceeds 64 KiB; reduce limit/budget/window.")
        return result
