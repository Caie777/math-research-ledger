"""Validated bounded JSON adapter; no shell, path or acceptance capability."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.records.write_boundary import automated_scope
from math_research.services.acceptance import request_acceptance
from math_research.services.research import get_object
from math_research.services.retrieval import export_context_packet, search_research
from math_research.services.stale import stale_report


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchArgs(Arguments):
    query: str = Field(min_length=1, max_length=4000)
    problem_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
    limit: int = Field(default=20, ge=1, le=50)


class ObjectArgs(Arguments):
    ref: ObjectRef
    offset: int = Field(default=0, ge=0)
    length: int = Field(default=4000, ge=1, le=8000)


class ContextArgs(Arguments):
    ref: ObjectRef
    query: str = Field(default="", max_length=4000)
    token_budget: int = Field(default=8000, ge=256, le=16000)
    purpose: str = "CONTINUE_RESEARCH"


class RequestArgs(Arguments):
    ref: ObjectRef
    verification_id: str = Field(min_length=1, max_length=128)


class StaleArgs(Arguments):
    problem_id: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=50)


SCHEMAS = {"search_research": SearchArgs, "get_research_object": ObjectArgs, "export_context_packet": ContextArgs, "request_acceptance": RequestArgs, "get_stale_report": StaleArgs}


class LedgerAdapter:
    def __init__(self, state: Path):
        self.state = state

    def call(self, name: str, arguments: dict) -> dict:
        schema = SCHEMAS.get(name)
        if schema is None:
            raise ResearchError("Tool is not exposed. Human acceptance is never a model tool.")
        args = schema.model_validate(arguments)
        with automated_scope():
            if isinstance(args, SearchArgs):
                result = search_research(self.state, args.query, problem_id=args.problem_id, limit=args.limit)
            elif isinstance(args, ObjectArgs):
                view = get_object(self.state, args.ref)
                entry = view.object
                text = entry.full_content
                result = {"ref": entry.ref.model_dump(), "content_hash": entry.content_hash, "version": entry.version, "authority": view.authority, "verification": view.verification, "freshness": view.freshness, "research_state": entry.research_state, "provenance": entry.provenance[:20], "provenance_omitted": max(0, len(entry.provenance) - 20), "content": text[args.offset:args.offset + args.length], "offset": args.offset, "total_characters": len(text), "truncated": args.offset > 0 or args.offset + args.length < len(text)}
            elif isinstance(args, ContextArgs):
                result = export_context_packet(self.state, args.ref, query=args.query, purpose=args.purpose, token_budget=args.token_budget).model_dump(mode="json")
            elif isinstance(args, RequestArgs):
                result = request_acceptance(self.state, args.ref, args.verification_id).model_dump(mode="json")
            else:
                report = stale_report(self.state, args.problem_id)
                result = {"source_version": report["source_version"], **{key: values[args.offset:args.offset + args.limit] for key, values in report.items() if isinstance(values, list)}, "totals": {key: len(values) for key, values in report.items() if isinstance(values, list)}}
        if len(json.dumps(result, ensure_ascii=False).encode()) > 65536:
            raise ResearchError("Bounded output exceeds 64 KiB; reduce limit/budget/window.")
        return result
