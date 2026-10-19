"""Bounded Evidence fields and rendering; no additional store or review system."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TypedDict, cast, get_args

from math_research.core.errors import ResearchError
from math_research.memory.decomposition import parse_numbered_episode
from math_research.memory.records.models import EvidenceRecord, EvidenceType, KeyExample

SCOPE_FIELDS = ("验证范围", "范围", "verification scope", "scope")
EXAMPLE_FIELDS = (
    "关键算例",
    "代表性算例",
    "key example",
    "key examples",
    "representative example",
    "representative cases",
)
_EXAMPLE_HEADING = re.compile(r"^###\s+(?:Key example|关键算例)\s+\d+\b", re.I)
_EXAMPLE_ITEM = re.compile(r"^(?:[-*]|\d+[.)])\s+")
_SIGNIFICANCE = re.compile(
    r"^(?:\*\*)?(?:significance|意义|保留原因)(?:\*\*)?\s*[:：]\s*(.*)$", re.I | re.M
)


class EvidenceFields(TypedDict):
    evidence_type: EvidenceType
    source_reported_type: str | None
    summary: str
    verification_scope: str | None
    key_examples: list[KeyExample]
    limitations: list[str]


def _pick(fields: dict[str, str], labels: tuple[str, ...]) -> str | None:
    return next((fields[key] for key in labels if fields.get(key)), None)


def parse_key_examples(text: str) -> list[KeyExample]:
    """Split explicit top-level list items/example headings, otherwise keep one paragraph."""
    lines = text.strip().splitlines()
    starts = [i for i, line in enumerate(lines) if _EXAMPLE_HEADING.match(line)]
    if not starts:
        starts = [i for i, line in enumerate(lines) if _EXAMPLE_ITEM.match(line)]
    if not starts or starts[0] != 0:
        blocks = [text.strip()] if text.strip() else []
    else:
        blocks = [
            "\n".join(lines[start:end]).strip()
            for start, end in zip(starts, [*starts[1:], len(lines)], strict=True)
        ]
    examples = []
    for block in blocks:
        if re.match(r"^###\s+(?:Key example|关键算例)\s+\d+\s*$", block.splitlines()[0], re.I):
            block = block.split("\n", 1)[-1].strip()
        match = _SIGNIFICANCE.search(block)
        description = block[: match.start()].strip() if match else block
        # An isolated significance label must not discard the original instance.
        examples.append(
            KeyExample(
                description=description or block,
                significance=(match.group(1) + "\n" + block[match.end() :]).strip()
                if match
                else None,
            )
        )
    return examples


def reviewed_evidence_fields(
    body: str, legacy_fields: dict[str, str] | None = None
) -> EvidenceFields:
    """Read the reviewed body. Legacy metadata is used only for unchanged opaque bodies."""
    sections, _ = parse_numbered_episode("## EVIDENCE-1\n\n" + body)
    fields = sections[0].fields
    if not fields and legacy_fields and body == _pick(legacy_fields, ("结果", "evidence")):
        fields = legacy_fields
    source_type = _pick(fields, ("类型", "type"))
    evidence_type: EvidenceType = (
        cast(EvidenceType, source_type)
        if source_type in get_args(EvidenceType)
        else "COMPUTATION"
        if source_type
        and any(word in source_type.casefold() for word in ("comput", "search", "numerical"))
        else "MANUAL_NOTE"
    )
    return dict(
        evidence_type=evidence_type,
        source_reported_type=source_type,
        summary=_pick(fields, ("结果", "result", "evidence")) or body,
        verification_scope=_pick(fields, SCOPE_FIELDS),
        key_examples=parse_key_examples(_pick(fields, EXAMPLE_FIELDS) or ""),
        limitations=[
            _pick(fields, ("逻辑强度", "logical strength")) or "source-reported; not verified"
        ],
    )


def evidence_review_body(record: EvidenceRecord) -> str:
    """Expose structured staged fields in the existing editable Proposal body."""
    examples = "\n\n".join(
        f"### Key example {i}\n\n{example.description}"
        + (f"\n\nSignificance: {example.significance}" if example.significance else "")
        for i, example in enumerate(record.key_examples, 1)
    )
    return "\n\n".join(
        f"**{label}**\n\n{value}"
        for label, value in (
            ("Type", record.source_reported_type or record.type),
            ("Target", record.claim_id),
            ("Verification scope", record.verification_scope or ""),
            ("Result", record.summary),
            ("Key examples", examples),
            ("Logical strength", "\n".join(record.limitations)),
        )
    )


def render_evidence(record: EvidenceRecord) -> str:
    """Shared retrieval, Recall object and Context body; authority comes from the resolver."""
    examples = "\n\n".join(
        f"### Key example {i}\n\n{example.description}"
        + (f"\n\nSignificance: {example.significance}" if example.significance else "")
        for i, example in enumerate(record.key_examples, 1)
    )
    return (
        f"Type: {record.source_reported_type or record.type} (record type: {record.type})\n"
        f"Target: {record.claim_id}\n\n"
        f"## Verification scope\n\n{record.verification_scope or 'Not specified'}\n\n"
        f"## Result\n\n{record.summary}\n\n"
        f"## Key examples\n\n{examples or 'None recorded'}\n\n"
        f"## Logical strength\n\n"
        + "\n".join(record.limitations)
        + "\n\nEvidence is an independent check, never a proof substitute.\n\n"
        + f"Source provenance: {', '.join(record.source_artifacts)}\n"
        + (f"Artifact path: {record.path}\n" if record.path else "")
    )


def get_key_example(ot_dir: Path, problem_id: str, evidence_id: str, index: int) -> KeyExample:
    """Read-only future explicit Human promotion seam; index is zero-based, scoped by Problem."""
    from math_research.memory.records import store

    record = next((e for e in store.list_evidence(ot_dir, problem_id) if e.id == evidence_id), None)
    if record is None or index < 0 or index >= len(record.key_examples):
        raise ResearchError("Evidence key example is unavailable in this Problem.")
    return record.key_examples[index].model_copy(deep=True)
