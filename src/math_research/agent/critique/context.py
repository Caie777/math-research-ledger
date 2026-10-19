"""Deterministic bounded material selection, without trajectory or critique retrieval."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from pydantic import BaseModel

from math_research.agent.critique.models import ContextItem, CritiqueBundle
from math_research.core.errors import ResearchError
from math_research.memory.records import store
from math_research.memory.relations.ledger import active_relations
from math_research.memory.source_records import get_paper
from math_research.memory.state import KnowledgeStateResolver
from math_research.retrieval.research_map import unique_canonical_target

MAX_CHARS = 100_000
MAX_ITEMS = 40
_ID = re.compile(r"\b[A-Z][A-Z_]*-[A-Za-z0-9]+\b")


def item(
    ident: str, kind: str, authority: str, status: str, reason: str, content: str
) -> ContextItem:
    return ContextItem(
        record_id=ident,
        record_type=kind,
        authority=authority,
        status=status,
        reason_included=reason,
        content=content,
        sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
    )


def _body(ot_dir: Path, pid: str, path: str | None, folder: str) -> str:
    if not path:
        raise ResearchError("Full mathematical body is unavailable.")
    base = store.dossier_dir(ot_dir, pid) / folder
    actual = (store.dossier_dir(ot_dir, pid) / path).resolve()
    if base.resolve() != base or not actual.is_relative_to(base):
        raise ResearchError("Mathematical body must stay inside its canonical record folder.")
    if actual.stat().st_size > MAX_CHARS * 4:
        raise ResearchError("Mathematical body exceeds the bounded critique context.")
    return actual.read_text(encoding="utf-8")


def build_critique_context(ot_dir: Path, problem_id: str, target_id: str) -> CritiqueBundle:
    """Only canonical records, immediate references and touching active relations.

    Never read chat, handoff, research_runs, raw Episodes or critiques. Oversized target
    content fails closed; omitted necessary context is reported, never silently truncated.
    """
    problem = store.require_dossier(ot_dir, problem_id)
    states = KnowledgeStateResolver(ot_dir).resolve(problem_id)
    records: dict[str, tuple[str, BaseModel]] = {}
    for kind, objects in (
        ("claim", store.list_claims(ot_dir, problem_id)),
        ("proof", store.list_proof_attempts(ot_dir, problem_id)),
        ("counterexample", store.list_counterexamples(ot_dir, problem_id)),
        ("evidence", store.list_evidence(ot_dir, problem_id)),
        ("definition", store.list_definitions(ot_dir, problem_id)),
        ("assumption", store.list_assumptions(ot_dir, problem_id)),
        ("known_result", store.list_known_results(ot_dir, problem_id)),
        ("theorem_ref", store.list_theorem_refs(ot_dir, problem_id)),
    ):
        for record in objects:
            records[str(record.id)] = (kind, record)
    if target_id not in records or records[target_id][0] not in {
        "claim",
        "proof",
        "counterexample",
        "evidence",
    }:
        raise ResearchError(
            "Critique requires a canonical Claim, Proof, Counterexample or Evidence."
        )
    limitations: list[str] = []

    def material(ident: str, reason: str) -> ContextItem:
        kind, record = records[ident]
        state = states.get(ident)
        if state and state.authority != "CANONICAL":
            raise ResearchError("Critique context cannot treat provisional records as accepted.")
        # Exact mathematical fields; storage paths and lineage are not model material.
        data = record.model_dump(
            mode="json",
            exclude={
                "created_at",
                "updated_at",
                "body_path",
                "verification_artifact",
                "path",
                "source_artifacts",
                "evidence_snapshot",
            },
        )
        if kind in {"proof", "counterexample"}:
            try:
                data["full_body"] = _body(
                    ot_dir,
                    problem_id,
                    getattr(record, "body_path", None),
                    "proof_attempts" if kind == "proof" else "counterexamples",
                )
            except (OSError, ResearchError) as exc:
                limitations.append(f"{ident}: {exc}")
        return item(
            ident,
            kind,
            state.authority if state else "CANONICAL",
            state.research_state if state else "recorded",
            reason,
            json.dumps(data, ensure_ascii=False, sort_keys=True),
        )

    target = material(target_id, "selected mathematical result; exact stored content")
    statement = store.read_statement(ot_dir, problem_id)
    if len(statement) > 3000:
        limitations.append("Problem statement is excerpted to 3000 characters.")
    problem_item = item(
        problem_id,
        "problem",
        "CANONICAL",
        problem.status,
        "primary problem scope",
        json.dumps(
            {
                "title": problem.title,
                "statement": statement[:3000],
                "primary_target_id": problem.primary_claim_id,
            },
            ensure_ascii=False,
        ),
    )
    used = len(target.content) + len(problem_item.content)
    if used > MAX_CHARS:
        raise ResearchError("Exact target content exceeds the bounded critique context.")
    target_record = records[target_id][1]
    refs = set(_ID.findall(target.content)) - {target_id, problem_id}
    for field in ("depends_on", "claim_links", "evidence_links", "source_artifacts"):
        refs.update(getattr(target_record, field, []))
    refs.update(getattr(states.get(target_id), "dependencies", []))
    refs.update(ident for ident, (kind, _) in records.items() if kind == "assumption")
    for ident, (kind, definition) in records.items():
        if kind == "definition":
            term = getattr(definition, "term", "").strip()
            if term and re.search(
                r"(?<!\w)" + re.escape(term) + r"(?!\w)", target.content, re.IGNORECASE
            ):
                refs.add(ident)
    for field in ("target_id", "claim_id"):
        value = getattr(target_record, field, None)
        if value:
            refs.add(value)
    if problem.primary_claim_id:
        refs.add(problem.primary_claim_id)
    relations: list[ContextItem] = []
    for relation in sorted(active_relations(ot_dir, problem_id), key=lambda r: r.decision_id):
        if target_id not in {relation.source_id, relation.target_id}:
            continue
        content = json.dumps(
            {
                "source": relation.source_id,
                "target": relation.target_id,
                "relation": relation.relation,
            },
            sort_keys=True,
        )
        selected_relation = item(
            relation.decision_id,
            "logical_relation",
            relation.label,
            "active",
            "active Logical Relation touching target",
            content,
        )
        if used + len(content) > MAX_CHARS or len(relations) >= MAX_ITEMS:
            limitations.append("Touching relation context exceeded its bounded allowance.")
            continue
        used += len(content)
        relations.append(selected_relation)
        refs.update({relation.source_id, relation.target_id} - {target_id})
    # Local sources explicitly cited by a selected direct premise remain inspectable.
    for ident in tuple(refs):
        if ident in records:
            premise = records[ident][1]
            refs.update(getattr(premise, "source_artifacts", []))
            cited_paper = getattr(premise, "paper_artifact", None)
            if cited_paper:
                refs.add(cited_paper)
    context: list[ContextItem] = []
    for ident in sorted(refs - {target_id}):
        # Episode IDs are custody/provenance, never permission to replay an Episode.
        if ident.startswith("EPISODE-"):
            continue
        if ident not in records:
            if re.fullmatch(r"PAPER-\d{4,}", ident):
                paper = get_paper(ot_dir, ident)
                source = paper.text_path or paper.local_path if paper else None
                source_path = (ot_dir / source).resolve() if source else None
                expected = ot_dir.resolve() / "papers" / ident
                if (
                    source_path
                    and expected.resolve() == expected
                    and source_path.is_relative_to(expected)
                    and source_path.suffix.lower() in {".md", ".txt"}
                    and source_path.is_file()
                    and source_path.stat().st_size <= MAX_CHARS * 4
                ):
                    text = source_path.read_text("utf-8")
                    if used + len(text) <= MAX_CHARS and len(context) < MAX_ITEMS:
                        context.append(
                            item(
                                ident,
                                "source",
                                "RAW_SOURCE",
                                "local",
                                "source explicitly referenced by target",
                                text,
                            )
                        )
                        used += len(text)
                        continue
            limitations.append(
                f"Explicit reference {ident} is not available as local accepted material."
            )
            continue
        state = states.get(ident)
        if state and state.authority != "CANONICAL":
            limitations.append(f"Explicit reference {ident} has no canonical authority.")
            continue
        reason = (
            "Problem-scoped recorded assumption"
            if records[ident][0] == "assumption"
            else "explicit target reference/dependency or designated primary target"
        )
        selected = material(ident, reason)
        if len(context) >= MAX_ITEMS or used + len(selected.content) > MAX_CHARS:
            limitations.append(f"Necessary reference {ident} omitted by the context bound.")
            continue
        used += len(selected.content)
        context.append(selected)
    continuation = None
    if target.record_type == "claim":
        continuation = target_id
    elif target.record_type in {"counterexample", "evidence"}:
        direct_reference = getattr(target_record, "claim_id", None) or getattr(
            target_record, "target_id", ""
        )
        direct_targets = {str(direct_reference)} if direct_reference else set()
        continuation = unique_canonical_target(
            direct_targets,
            {
                ident
                for ident, (kind, _) in records.items()
                if kind == "claim" and getattr(states.get(ident), "authority", None) == "CANONICAL"
            },
        )
    elif target.record_type == "proof":
        explicit = set(getattr(target_record, "claim_links", []))
        explicit.update(
            r.target_id
            for r in active_relations(ot_dir, problem_id)
            if r.source_id == target_id and r.relation in {"PROVES", "REFUTES"}
        )
        continuation = unique_canonical_target(
            explicit,
            {
                ident
                for ident, (kind, _) in records.items()
                if kind == "claim" and getattr(states.get(ident), "authority", None) == "CANONICAL"
            },
        )
    return CritiqueBundle(
        problem_id=problem_id,
        target=target,
        problem=problem_item,
        context=context,
        relations=relations,
        limitations=sorted(set(limitations))[:59]
        + (
            [f"Additional omitted context limitations: {len(set(limitations)) - 59}"]
            if len(set(limitations)) > 59
            else []
        ),
        continuation_target_id=continuation,
    )
