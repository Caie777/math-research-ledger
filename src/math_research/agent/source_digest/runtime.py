"""At most one structure pass and four independent extraction calls; no tools."""

import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from typing import Protocol

from pydantic import ValidationError

from math_research.agent.codex import CodexToolProvider
from math_research.agent.model import SemanticModel
from math_research.agent.providers.base import ProviderResponse
from math_research.agent.session import SessionMessage
from math_research.agent.source_digest import store
from math_research.agent.source_digest.context import coverage, validate_support
from math_research.agent.source_digest.models import (
    DigestRun,
    ExtractedProposal,
    ExtractionOutput,
    SourceDigest,
    SourceProposal,
    StructureOutput,
    Support,
)
from math_research.agent.source_digest.prompt import DIGEST_PROMPT, STRUCTURE_PROMPT
from math_research.core.errors import ResearchError
from math_research.ledger.records.write_boundary import automated_research
from math_research.ledger.relations.policy import LOGICAL_RELATIONS
from math_research.ledger.state import KnowledgeStateResolver
from math_research.retrieval.recall import ResearchRecall


class Transport(Protocol):
    def generate(self, messages: list[SessionMessage], schema: dict) -> ProviderResponse: ...


def _generate(
    ot_dir: Path, run: DigestRun, messages: list[SessionMessage], schema: dict, deadline: float
) -> ProviderResponse:
    settings = run.settings
    if settings.provider == "codex":
        provider = CodexToolProvider(
            settings.model,
            settings.reasoning_effort,
            deadline=deadline,
            should_stop=lambda: False,
            tool_free=True,
        )
        try:
            return provider.generate(messages, tools=[])
        finally:
            provider.close()
    model = SemanticModel(
        ot_dir,
        provider_name=settings.provider,
        model=settings.model,
        reasoning_effort=settings.reasoning_effort,
    )
    model.budget = model.budget.model_copy(
        update={"max_calls": 1, "timeout_seconds": max(1, int(deadline - time.monotonic()))}
    )
    return model.generate(messages, schema)


@automated_research
def execute(ot_dir: Path, run: DigestRun, *, transport: Transport | None = None) -> DigestRun:
    if store.read_run(ot_dir, run.digest_id).status != "RUNNING":
        raise ResearchError("Source digest cannot reuse a completed session.")
    store.claim_execution(ot_dir, run)
    try:
        context = store.read_context(ot_dir, run)
        base = context.model_dump(exclude={"chunks"})
        deadline = time.monotonic() + 600
        actual_models: list[str] = []

        def request(prompt: str, payload: dict, schema: dict) -> str:
            if time.monotonic() >= deadline:
                raise ResearchError("Source digest time budget exhausted.")
            messages = [
                SessionMessage(role="system", content=prompt + "\nSchema:\n" + json.dumps(schema)),
                SessionMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
            ]
            response = (
                transport.generate(messages, schema)
                if transport
                else _generate(ot_dir, run, messages, schema, deadline)
            )
            if response.kind != "message" or response.truncated or len(response.content) > 100000:
                raise ResearchError(
                    "Source digest returned tools/truncated/oversized output; no tools run."
                )
            actual_models.append(response.model or run.settings.model)
            return response.content

        selected = context.chunks
        structure_summary = ""
        warnings: list[str] = []
        if len(selected) > 1:
            outline = [
                {**chunk.model_dump(exclude={"text"}), "excerpt": chunk.text[:600]}
                for chunk in selected
            ]
            structure = StructureOutput.model_validate_json(
                request(
                    STRUCTURE_PROMPT,
                    {**base, "outline": outline, "max_chunks": run.settings.max_chunks},
                    StructureOutput.model_json_schema(),
                )
            )
            ids = structure.relevant_chunk_ids
            if len(ids) != len(set(ids)) or any(
                i not in {c.chunk_id for c in selected} for i in ids
            ):
                raise ResearchError("Structure pass returned invalid or duplicate chunk IDs.")
            structure_summary = structure.summary
            selected = [c for c in selected if c.chunk_id in ids][: run.settings.max_chunks]
        else:
            selected = selected[: run.settings.max_chunks]
        values: dict[str, list[str]] = {
            name: []
            for name in (
                "notation",
                "definitions",
                "results",
                "methods",
                "assumptions",
                "limitations",
            )
        }
        summaries = [structure_summary] if structure_summary else []
        proposals: list[SourceProposal] = []
        processed = []
        states = KnowledgeStateResolver(ot_dir).resolve(run.problem_id)
        context_ids = {context.primary_target_id} | {
            item["record_id"] for item in context.accepted_terminology
        }
        allowed_ids = {
            i
            for i, s in states.items()
            if i in context_ids and s.authority == "CANONICAL" and s.canonical_id is None
        }
        extraction_schema = ExtractionOutput.model_json_schema()
        item_schema = ExtractedProposal.model_json_schema()
        extraction_schema.setdefault("$defs", {}).update(item_schema.pop("$defs", {}))
        extraction_schema["properties"]["proposals"]["items"] = item_schema
        recall = ResearchRecall(ot_dir, run.problem_id)
        for chunk in selected:
            try:
                output = ExtractionOutput.model_validate_json(
                    request(
                        DIGEST_PROMPT,
                        {
                            **base,
                            "chunk": chunk.model_dump(),
                            "allowed_target_ids": sorted(allowed_ids),
                        },
                        extraction_schema,
                    )
                )
            except (ValidationError, ResearchError):
                warnings.append(f"{chunk.chunk_id}: extraction failed validation; no items staged.")
                continue
            processed.append(chunk)
            summaries.append(output.summary)
            for key in values:
                values[key].extend(getattr(output, key))
            counts = Counter(
                p.get("proposal_id")
                for p in output.proposals
                if isinstance(p.get("proposal_id"), str)
            )
            parsed: list[ExtractedProposal] = []
            for raw in output.proposals:
                try:
                    item = ExtractedProposal.model_validate(raw)
                    if counts[item.proposal_id] != 1:
                        raise ValueError("Duplicate proposal ID")
                    if (
                        not item.title.strip()
                        or not item.statement.strip()
                        or any(len(v) > 10000 for v in [item.notes, item.statement])
                    ):
                        raise ValueError("Blank/oversized item")
                    parsed.append(item)
                except (ValidationError, ValueError):
                    warnings.append(
                        f"{chunk.chunk_id}: invalid/duplicate proposal item quarantined."
                    )
            local = {p.proposal_id for p in parsed if p.proposal_type != "relation"}
            local_types = {p.proposal_id: p.proposal_type for p in parsed}
            prefix = chunk.chunk_id.replace("CHUNK", "SP") + "-"
            for item in parsed:
                references = [item.target_id, item.source_candidate_id]
                if any(ref and ref not in allowed_ids | local for ref in references):
                    warnings.append(
                        f"{chunk.chunk_id}/{item.proposal_id}: nonexistent/out-of-scope target."
                    )
                    continue
                if item.proposal_type == "relation" and (
                    item.relation not in LOGICAL_RELATIONS - {"SAME_AS"}
                    or not item.target_id
                    or not item.source_candidate_id
                    or item.source_candidate_id not in local
                    or item.relation == "PROVES"  # No new Proof object is extracted from a Source.
                    or item.relation in {"REFUTES", "INVALIDATES"}
                    and local_types.get(item.source_candidate_id) != "counterexample"
                ):
                    warnings.append(f"{chunk.chunk_id}/{item.proposal_id}: incomplete relation.")
                    continue
                if item.proposal_type != "relation" and (item.relation or item.source_candidate_id):
                    warnings.append(
                        f"{chunk.chunk_id}/{item.proposal_id}: relation fields on ordinary item."
                    )
                    continue
                ident = prefix + item.proposal_id
                candidate_id = (
                    "CANDIDATE-"
                    + hashlib.sha256((run.digest_id + ident).encode()).hexdigest()[:20].upper()
                )
                # Validate only against the chunk actually supplied to this invocation.
                status = validate_support(
                    context.model_copy(update={"chunks": [chunk]}),
                    item.locator,
                    item.supporting_span,
                )
                if status != "VALID":
                    warnings.append(f"{ident}: {status}; Human Accept is blocked.")
                try:
                    matches = recall.find_files(query=item.statement, limit=5).files
                except ResearchError:
                    # Optional overlap hints must not invalidate this independently
                    # verified Source when another pinned Source has gone stale.
                    matches = []
                    warnings.append(f"{ident}: overlap lookup unavailable; no duplicate hints.")
                data = item.model_dump()
                for key in ("target_id", "source_candidate_id"):
                    if data[key] in local:
                        data[key] = prefix + data[key]
                proposals.append(
                    SourceProposal(
                        **{**data, "proposal_id": ident},
                        source_id=run.source_id,
                        source_filename=context.source_filename,
                        digest_id=run.digest_id,
                        candidate_id=candidate_id,
                        provenance_status=status,
                        possible_duplicate_ids=[
                            f.artifact_id for f in matches if f.authority == "CANONICAL"
                        ],
                    )
                )
        # Exact extraction dedupe only. Preserve every supporting location; never SAME_AS.
        merged: dict[tuple, SourceProposal] = {}
        referenced = {p.target_id for p in proposals} | {p.source_candidate_id for p in proposals}
        for proposal in proposals:
            signature = (
                proposal.proposal_type,
                " ".join(proposal.statement.split()),
                proposal.target_id,
                proposal.source_candidate_id,
                proposal.relation,
                proposal.citation_kind,
                proposal.provenance_status,
                proposal.proposal_id
                if proposal.proposal_id in referenced or proposal.provenance_status != "VALID"
                else None,
            )
            if signature in merged:
                merged[signature].additional_support.append(
                    Support(locator=proposal.locator, supporting_span=proposal.supporting_span)
                )
            else:
                merged[signature] = proposal
        ranges, omissions, complete = coverage(context, processed)
        digest = SourceDigest(
            digest_id=run.digest_id,
            source_id=run.source_id,
            source_filename=context.source_filename,
            source_sha256=run.source_sha256,
            problem_id=run.problem_id,
            created_at=run.created_at,
            model=", ".join(sorted(set(actual_models))) or run.settings.model,
            reasoning_effort=run.settings.reasoning_effort,
            summary="\n\n".join(summaries),
            notation=list(dict.fromkeys(values["notation"])),
            definitions=list(dict.fromkeys(values["definitions"])),
            results=list(dict.fromkeys(values["results"])),
            methods=list(dict.fromkeys(values["methods"])),
            assumptions=list(dict.fromkeys(values["assumptions"])),
            limitations=[*context.limitations, *list(dict.fromkeys(values["limitations"]))],
            proposals=list(merged.values())[:100],
            coverage_complete=complete,
            processed_ranges=ranges,
            omitted_ranges=omissions,
            validation_warnings=warnings,
        )
        if len(merged) > 100:
            digest.validation_warnings.append("Proposal cap reached; remaining items not staged.")
        return store.finish(ot_dir, run, digest=digest)
    except Exception as exc:
        detail = (
            str(exc)
            if isinstance(exc, ResearchError)
            else f"Digest failed ({type(exc).__name__}); check output/configuration."
        )
        return store.finish(ot_dir, run, error=detail)
