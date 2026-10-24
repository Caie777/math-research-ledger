"""Validated, bounded model capabilities over deterministic services only."""

import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from math_research.core.errors import ResearchError
from math_research.ledger.manifest import Ledger
from math_research.ledger.publication import publication_navigation
from math_research.ledger.records.write_boundary import automated_scope
from math_research.services.acceptance import request_acceptance
from math_research.services.ingest import ingest_episode, preview_episode, save_note
from math_research.services.problems import (
    CreateProblemInput,
    UpdateProblemInput,
    create_problem,
    update_problem,
)
from math_research.services.research import get_object, list_objects, status
from math_research.services.retrieval import export_context_packet, search_research
from math_research.services.review import prepare_review
from math_research.services.stale import stale_report

MAX_OUTPUT_BYTES = 64 * 1024
ProblemId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    workspace: str | None = Field(
        default=None,
        max_length=4096,
        description="Optional compatibility assertion of the pinned session workspace root. "
        "Omit normally; equivalent resolved paths only. Cannot select or authorize another Ledger.",
    )


class PageArgs(Arguments):
    problem_id: ProblemId | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)


class StatusArgs(PageArgs):
    since: dict[str, Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]] | None = Field(
        default=None,
        max_length=32,
        description="Prior continuation_snapshot for this explicit Problem; no inferred history.",
    )


class SearchArgs(Arguments):
    query: str = Field(min_length=1, max_length=4000)
    problem_id: ProblemId | None = None
    limit: int = Field(default=20, ge=1, le=50)


class RefArgs(Arguments):
    ref: str = Field(min_length=1, max_length=400, description="Qualified problem:kind:object ID")


class ObjectArgs(RefArgs):
    offset: int = Field(
        default=0, ge=0, description="Character offset, default 0; follow next_offset."
    )
    length: int = Field(
        default=4000,
        ge=1,
        le=8000,
        description="Characters per page; default 4000, maximum 8000. "
        "Use next_offset for another page.",
    )
    produced_offset: int = Field(
        default=0,
        ge=0,
        description="Episode publication navigation offset, independent of text offset; "
        "follow next_produced_offset/next_relation_offset. Six entries per page.",
    )


class ContextArgs(RefArgs):
    query: str = Field(default="", max_length=4000)
    token_budget: int = Field(
        default=8000,
        ge=256,
        le=16000,
        description="Estimated tokens for entire packet: 256..16000, recommended/default 8000. "
        "Do not exceed 16000; retrieve omitted originals with paginated get_object.",
    )
    purpose: Literal["CONTINUE_RESEARCH", "RECOVER_PROOF", "TRACE_HISTORY", "FIND_FAILURES"] = (
        "CONTINUE_RESEARCH"
    )


class RequestArgs(RefArgs):
    verification_id: str = Field(min_length=1, max_length=128)


class EpisodeArgs(Arguments):
    problem_id: ProblemId
    markdown: str = Field(min_length=1, max_length=128000)
    provenance: str = Field(min_length=1, max_length=1000)
    dry_run: bool = False
    archive_only: bool = False


class NoteArgs(Arguments):
    problem_id: ProblemId
    kind: Literal["claim", "gap", "failed_attempt", "evidence", "counterexample"]
    title: str = Field(min_length=1, max_length=300, pattern=r"^[^\r\n]+$")
    body: str = Field(min_length=1, max_length=32000)
    provenance: str = Field(min_length=1, max_length=1000)


class CreateProblemArgs(Arguments, CreateProblemInput):
    pass


class UpdateProblemArgs(Arguments, UpdateProblemInput):
    pass


SCHEMAS: dict[str, type[Arguments]] = {
    "research_status": StatusArgs,
    "research_search": SearchArgs,
    "research_get_object": ObjectArgs,
    "research_context_packet": ContextArgs,
    "research_review_packet": RefArgs,
    "research_stale_report": PageArgs,
    "research_ingest_episode": EpisodeArgs,
    "research_save_note": NoteArgs,
    "research_request_acceptance": RequestArgs,
    "research_create_problem": CreateProblemArgs,
    "research_update_problem": UpdateProblemArgs,
}

DESCRIPTIONS = {
    "research_create_problem": (
        "Explicitly register a new active Problem with title, statement and primary_target "
        "mathematical text. Use dry_run=true first; preview IDs are not reserved. Each real "
        "call allocates a new ID, even with the same title. Does not initialize missing "
        "workspaces, create Claims or grant verification/acceptance."
    ),
    "research_update_problem": (
        "Update an explicit Problem's metadata or active/paused/closed lifecycle. Closing "
        "requires closure_kind and closure_reason; resolution_refs are advisory object links. "
        "statement/primary_target require revision_kind='semantic'; metadata never changes "
        "mathematical versions. Preview with dry_run=true; optionally pin expected_version. "
        "Does not verify, accept or promote any Claim; no deletion."
    ),
    "research_status": (
        "Call first when continuing long-running research or asked where an existing Problem "
        "stands. Returns paginated Problem/object references and authority/check/freshness "
        "summaries. Follow with research_context_packet before substantial work. Do not use "
        "omitted problem_id as an implicit .current selection; choose a Problem explicitly. "
        "Do not use this as full research context or as a substitute for checking originals."
    ),
    "research_search": (
        "Find prior results, gaps and failed routes by keywords before doing overlapping work. "
        "Returns ranked scoped hits with provenance and trust labels. Do not treat a search "
        "excerpt as an accepted premise; load the object/context before relying on it. "
        "A whole qualified ref or unique object/Episode/candidate ID uses exact navigation first."
    ),
    "research_get_object": (
        "Read an existing qualified research object or continue an omitted body. Returns a "
        "bounded text window, version, provenance, authority and freshness. Page with offset "
        "and length: offset >=0 (default 0), length 1..8000 characters (default 4000). "
        "Follow next_offset/remaining, never enlarge length past 8000. Episode publication "
        "navigation uses produced_offset separately. Do not use for arbitrary filesystem paths "
        "or whole-Problem context."
    ),
    "research_context_packet": (
        "Load bounded current research context for an existing problem/claim/gap before "
        "starting or resuming substantial research. Returns provenance/trust/freshness labels "
        "and explicit missing/truncated mandatory material. Normally call once near the start "
        "of a research run, not every turn. token_budget 256..16000, default/recommended 8000; "
        "read omitted originals with paginated get_object. Never assume omissions were checked."
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
        "or accept anything. Object risks include UNKNOWN (unbound), separately from STALE "
        "(confirmed drift). Do not interpret absence of staleness as verification."
    ),
    "research_ingest_episode": (
        "Consolidate a meaningful checkpoint as complete UTF-8 Research Episode Markdown "
        "with provenance. Separate Confirmed Research Increment (state_delta) from advisory "
        "Next Research Directions; never capture every chat turn. "
        "Use dry_run=true to preview diagnostics without writes; ERROR blocks structured "
        "publication. archive_only=true explicitly preserves raw text without extraction. "
        "Stages provisional candidates in the existing archive/Proposal Store; repeated identical "
        "content reuses identities. Returns candidate references, counts and omissions, not full "
        "bodies. Do not send fragments, promote facts, run checks or request human acceptance here."
    ),
    "research_save_note": (
        "Preserve one complete useful Claim, Gap, FailedAttempt, Evidence or Counterexample with "
        "provenance. Use sparingly for an important isolated capture, not every chat turn. "
        "Stages a single provisional Episode candidate in the existing Proposal Store "
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
        "structured_published": value.get("structured_published", True),
        "diagnostics": value.get("diagnostics", [])[:20],
        "diagnostics_omitted": max(0, len(value.get("diagnostics", [])) - 20),
        "authority": "PROVISIONAL",
        "candidate_count": len(candidates),
        "state_delta_count": len(value["episode"].get("state_delta", [])),
        "next_directions_advisory": True,
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
        from math_research.ledger.checkpoint import checkpoint_read, consistent_checkpoint_read

        preview = name == "research_ingest_episode" and arguments.get("dry_run") is True
        if name in {"research_create_problem", "research_update_problem"}:
            # The shared Problem service owns both pure preview and journaled mutation.
            return self._call(name, arguments)
        if name == "research_save_note" or name == "research_ingest_episode" and not preview:
            return self._call(name, arguments)
        if name == "research_request_acceptance":
            # This persists a request. Never replay it as an optimistic read.
            with checkpoint_read(self.state):
                return self._call(name, arguments)
        return consistent_checkpoint_read(self.state, lambda: self._call(name, arguments))

    def _call(self, name: str, arguments: dict) -> dict:
        schema = SCHEMAS.get(name)
        if schema is None:
            raise ResearchError("Tool is not exposed. Human acceptance is never a model tool.")
        args = schema.model_validate(arguments)
        with automated_scope():
            ref = Ledger(self.state).resolve(args.ref) if isinstance(args, RefArgs) else None
            if isinstance(args, CreateProblemArgs):
                result = create_problem(self.state, **args.model_dump(exclude={"workspace"}))
            elif isinstance(args, UpdateProblemArgs):
                result = update_problem(
                    self.state, **args.model_dump(exclude={"workspace"}, exclude_unset=True)
                )
            elif name == "research_status":
                result = status(self.state, **args.model_dump(exclude={"workspace"}))
            elif isinstance(args, SearchArgs):
                result = search_research(self.state, **args.model_dump(exclude={"workspace"}))
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
                    "integrity": entry.integrity,
                    "usable_working_premise": view.usable_working_premise,
                    "trusted_formal_premise": view.trusted_formal_premise,
                    "premise_eligibility": view.premise_eligibility,
                    "conditional_premise": view.conditional_premise,
                    "premise_reasons": view.premise_reasons,
                    "research_state": entry.research_state,
                    "provenance": entry.provenance[:20],
                    "provenance_omitted": max(0, len(entry.provenance) - 20),
                    "content": text[args.offset : args.offset + args.length],
                    "offset": args.offset,
                    "total_characters": len(text),
                    "next_offset": args.offset + len(text[args.offset : args.offset + args.length])
                    if args.offset + args.length < len(text)
                    else None,
                    "remaining": max(0, len(text) - args.offset - args.length),
                    "max_window": 8000,
                    "truncated": args.offset > 0 or args.offset + args.length < len(text),
                }
                if entry.ref.kind == "episode":
                    assert entry.ref.problem_id is not None
                    result.update(
                        publication_navigation(
                            self.state,
                            entry.ref.problem_id,
                            entry.ref.object_id,
                            list_objects(self.state, entry.ref.problem_id),
                            offset=args.produced_offset,
                        )
                    )
                    delta = entry.record.get("state_delta", [])
                    start = args.offset
                    result["checkpoint"] = {
                        "state_delta": [
                            {
                                **item,
                                "statement": item["statement"][:600],
                                "statement_truncated": len(item["statement"]) > 600,
                            }
                            for item in delta[start : start + 20]
                        ],
                        "delta_total": len(delta),
                        "delta_offset": start,
                        "delta_truncated": start > 0 or start + 20 < len(delta),
                        "next_research_directions": entry.record.get(
                            "next_research_directions", ""
                        )[:2000],
                        "directions_truncated": len(
                            entry.record.get("next_research_directions", "")
                        )
                        > 2000,
                        "next_directions_advisory": True,
                        "authority": "SOURCE_REPORTED",
                    }
            elif isinstance(args, ContextArgs):
                assert ref is not None
                result = export_context_packet(
                    self.state, ref, **args.model_dump(exclude={"ref", "workspace"})
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
                    "object_scope": report["object_scope"],
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
                if args.dry_run:
                    result = preview_summary(
                        preview_episode(
                            self.state,
                            args.problem_id,
                            "research-episode.md",
                            args.markdown.encode("utf-8"),
                        )
                    )
                else:
                    result = _ingest_summary(
                        ingest_episode(
                            self.state,
                            args.problem_id,
                            "research-episode.md",
                            args.markdown.encode("utf-8"),
                            provenance=args.provenance,
                            archive_only=args.archive_only,
                        )
                    )
            elif isinstance(args, NoteArgs):
                result = _ingest_summary(
                    save_note(self.state, **args.model_dump(exclude={"workspace"}))
                )
            else:
                raise ResearchError("Unsupported validated tool arguments.")
        if len(json.dumps(result, ensure_ascii=False).encode("utf-8")) > MAX_OUTPUT_BYTES:
            raise ResearchError("Bounded output exceeds 64 KiB; reduce limit/budget/window.")
        return result


def preview_summary(value: dict) -> dict:
    """Bounded transport projection; the full service preview remains available to CLI."""
    result = {
        key: value[key]
        for key in (
            "sha256",
            "episode_id",
            "detected_format",
            "schema",
            "can_publish",
            "confirmed_research_increments",
            "provisional_object_count",
            "next_directions_advisory",
        )
    }
    for key in ("diagnostics", "bindings", "local_ids"):
        result[key] = value[key][:20]
        result[key + "_omitted"] = max(0, len(value[key]) - 20)
    result["candidates"] = [
        c.model_dump(
            include={
                "candidate_id",
                "kind",
                "local_id",
                "target_id",
                "uses",
                "start_line",
                "end_line",
            }
        )
        for c in value["candidates"][:20]
    ]
    result["candidates_omitted"] = max(0, len(value["candidates"]) - 20)
    metadata = value["metadata"]
    result["state_delta"] = [
        {
            **d.model_dump(),
            "statement": d.statement[:600],
            "statement_truncated": len(d.statement) > 600,
        }
        for d in metadata.state_delta[:20]
    ]
    result["state_delta_omitted"] = max(0, len(metadata.state_delta) - 20)
    result["input_versions"] = [p.model_dump(mode="json") for p in metadata.input_versions[:20]]
    result["input_versions_omitted"] = max(0, len(metadata.input_versions) - 20)
    result["next_research_directions"] = metadata.next_research_directions[:2000]
    result["directions_truncated"] = len(metadata.next_research_directions) > 2000
    return result
