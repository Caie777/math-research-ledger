"""Human-reviewed Markdown episodes, without a second mathematical truth ledger.

The archive and review log are provenance/control metadata. Accepted mathematical
objects are written through the existing dossier APIs; extraction writes none.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, model_validator

from math_research.core.atomicio import file_lock
from math_research.core.errors import ResearchError
from math_research.core.jsonl import append_jsonl, atomic_append_jsonl, read_jsonl
from math_research.ledger.archive import source_path
from math_research.ledger.decomposition import (
    has_numbered_headings,
    local_ids,
    mathematical_lines,
    parse_numbered_episode,
)
from math_research.ledger.records import claims, store
from math_research.ledger.records.models import Approach, ClaimRecord, ClaimType
from math_research.ledger.records.write_boundary import human_write
from math_research.ledger.relations.policy import LOGICAL_RELATIONS

ProposalKind = Literal[
    "claim",
    "proof",
    "gap",
    "failed_attempt",
    "counterexample",
    "branch",
    "relation",
    "evidence",
    "refutation",
    "revision",
]
RelationKind = Literal[
    "SAME_AS",
    "REVISES",
    "PROVES",
    "USES",
    "DEPENDS_ON",
    "REFUTES",
    "INVALIDATES",
    "SPECIAL_CASE_OF",
    "GENERALIZES",
    "RELATED_TO",
    "NO_LINK",
    "SUPERSEDES",
    "STRENGTHENS",
    "WEAKENS",
]
DecisionKind = Literal["accept", "reject", "defer"]

_HEADING = re.compile(
    r"^## (Claim|Proof|Gap|Failed Attempt|Counterexample|Branch)(?::\s*(.*))?$", re.I
)
_FIELD = re.compile(r"^(Target|Uses|Revises|Relates|Summary|Strategy):\s*(.*)$", re.I)
_DOSSIER_CLAIM = re.compile(r"\bCLAIM-(?:\d{4,}|P[0-9A-F]{16})\b")
_DOSSIER_OBJECT = re.compile(
    r"\b(?:CLAIM|PROOF|APPROACH|APPR|COUNTEREXAMPLE|EVIDENCE|FAILED)-"
    r"(?:\d{4,}|P[0-9A-F]{16})\b"
)
_KINDS: dict[str, ProposalKind] = {
    "claim": "claim",
    "proof": "proof",
    "gap": "gap",
    "failed attempt": "failed_attempt",
    "counterexample": "counterexample",
    "branch": "branch",
}
_RELATIONS = LOGICAL_RELATIONS | {"RELATED_TO", "NO_LINK"}


class EpisodeDependency(BaseModel):
    source_id: str
    target_id: str


class EpisodeRelationHint(EpisodeDependency):
    """Agent-local candidate, never an active Logical Relation."""

    relation: RelationKind | Literal["TARGETS"]


class EpisodeOutputMetadata(BaseModel):
    """Local IDs point to existing full Markdown objects without duplicating text."""

    new_claims: list[str] = Field(default_factory=list)
    new_gaps: list[str] = Field(default_factory=list)
    proof_attempts: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    counterexamples: list[str] = Field(default_factory=list)
    failed_attempts: list[str] = Field(default_factory=list)
    explicit_dependencies: list[EpisodeDependency] = Field(default_factory=list)
    relation_hints: list[EpisodeRelationHint] = Field(default_factory=list)


class ResearchEpisode(EpisodeOutputMetadata):
    """Project source identity with a compatibility interpretation scope.

    ``problem_id`` is the requested Problem view (empty for an unscoped source).
    Physical ownership is never inferred from this field.
    """

    episode_id: str
    problem_id: str = ""
    primary_problem_id: str | None = None
    related_problem_ids: list[str] = Field(default_factory=list)
    archive_path: str
    imported_at: datetime
    source_filename: str
    source_language: str | None = None
    content_sha256: str
    provenance: str | None = None
    thread_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def legacy_scope(cls, value: object) -> object:
        if isinstance(value, dict) and "primary_problem_id" not in value:
            value = {**value, "primary_problem_id": value.get("problem_id") or None}
        return value


class Proposal(BaseModel):
    """Review proposal, never a verified mathematical fact.

    ``source_reported_status`` exists on every in-memory candidate. Old JSONL
    records omit it and load as an empty string; it is neither review decision
    nor the Problem Record Claim/Proof epistemic status.
    """

    candidate_id: str
    object_id: str | None = None
    episode_id: str
    problem_id: str
    kind: ProposalKind
    title: str = ""
    body: str = ""
    summary: str = ""
    strategy: str = ""
    target_id: str | None = None
    relation: RelationKind | None = None
    uses: list[str] = Field(default_factory=list)
    revises_proof_id: str | None = None
    action: Literal["NEW", "SAME_AS"] = "NEW"
    source_section: str
    start_line: int
    end_line: int
    local_id: str | None = None
    source_local_id: str | None = None
    origin_candidate_id: str | None = None
    raw_markdown: str = ""
    source_reported_status: str = ""
    source_fields: dict[str, str] = Field(default_factory=dict)
    thread_ids: list[str] = Field(default_factory=list)
    relation_wording: str = ""
    semantic_validation_status: str | None = None
    semantic_confidence: float | None = None


class ReviewDecision(BaseModel):
    candidate_id: str
    episode_id: str
    problem_id: str
    decision: DecisionKind
    decided_at: datetime
    mapped_id: str | None = None
    reviewed_candidate: Proposal | None = None
    source_id: str | None = None
    target_id: str | None = None
    relation: RelationKind | None = None


def _archive_dir(ot_dir: Path, problem_id: str) -> Path:
    return store.dossier_dir(ot_dir, problem_id) / "archive" / "episodes"


def _episode_index(ot_dir: Path, problem_id: str) -> Path:
    return _archive_dir(ot_dir, problem_id) / "index.jsonl"


def _candidate_path(ot_dir: Path, problem_id: str) -> Path:
    return _archive_dir(ot_dir, problem_id) / "candidates.jsonl"


def _review_path(ot_dir: Path, problem_id: str) -> Path:
    return _archive_dir(ot_dir, problem_id) / "reviews.jsonl"


def list_episodes(ot_dir: Path, problem_id: str | None = None) -> list[ResearchEpisode]:
    from math_research.ledger.archive import load_episodes

    return load_episodes(ot_dir, problem_id)


def list_candidates(ot_dir: Path, problem_id: str, episode_id: str | None = None) -> list[Proposal]:
    items = read_jsonl(_candidate_path(ot_dir, problem_id), Proposal)
    return [item for item in items if episode_id is None or item.episode_id == episode_id]


def list_reviews(ot_dir: Path, problem_id: str) -> list[ReviewDecision]:
    return read_jsonl(_review_path(ot_dir, problem_id), ReviewDecision)


def archive_episode(
    ot_dir: Path,
    problem_id: str | None,
    source: Path,
    *,
    now: datetime | None = None,
    provenance: str | None = None,
    thread_ids: list[str] | None = None,
    related_problem_ids: list[str] | None = None,
) -> ResearchEpisode:
    """Archive a project source verbatim; Problem membership is metadata."""
    from math_research.ledger.archive import archive_source

    raw = source.read_bytes()
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ResearchError("Research Episode must be UTF-8 Markdown.") from exc
    if not content.strip():
        raise ResearchError("Research Episode cannot be empty.")
    metadata, _ = _front_matter(content)
    output_metadata = structured_episode_metadata(content)
    scope_threads = thread_ids if thread_ids is not None else metadata.get("thread_ids", [])
    if not isinstance(scope_threads, list) or any(
        not isinstance(t, str) or not t.strip() or len(t) > 128 for t in scope_threads
    ):
        raise ResearchError("thread_ids must contain strings of 1–128 characters.")
    instant = now or datetime.now().astimezone()
    if instant.tzinfo is None:
        raise ResearchError("Episode import time must include a timezone.")
    language = metadata.get("language")
    return archive_source(
        ot_dir,
        problem_id,
        source.name,
        raw,
        instant,
        provenance=provenance,
        thread_ids=scope_threads,
        related_problem_ids=related_problem_ids or [],
        source_language=language if isinstance(language, str) and language.strip() else None,
        output_metadata=output_metadata,
    )


def _front_matter(content: str) -> tuple[dict[str, object], int]:
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, 0
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ResearchError("Unterminated YAML front matter.") from exc
    data = yaml.safe_load("\n".join(lines[1:end])) or {}
    if not isinstance(data, dict):
        raise ResearchError("Episode front matter must be a YAML mapping.")
    return data, end + 1


def structured_episode_metadata(content: str) -> EpisodeOutputMetadata:
    """Reuse Episode V4 objects and explicit links; no model or canonical writes."""
    metadata, _ = _front_matter(content)
    sections, relations = parse_numbered_episode(content)
    groups = {
        "new_claims": {"RESULT"},
        "new_gaps": {"GAP"},
        "proof_attempts": {"PROOF", "REFUTATION"},
        "evidence": {"EVIDENCE"},
        "counterexamples": {"COUNTEREXAMPLE"},
        "failed_attempts": {"FAILED-ATTEMPT"},
    }
    declared = {key: metadata[key] for key in EpisodeOutputMetadata.model_fields if key in metadata}
    try:
        output = EpisodeOutputMetadata.model_validate(declared)
    except ValidationError as exc:
        raise ResearchError(f"Invalid Episode structured output metadata: {exc}") from exc
    known = {s.local_id for s in sections}

    def refs(text: str) -> list[str]:
        return list(dict.fromkeys([*local_ids(text), *_DOSSIER_OBJECT.findall(text)]))

    for key, kinds in groups.items():
        actual = [s.local_id for s in sections if s.kind in kinds]
        if key in declared and getattr(output, key) != actual:
            raise ResearchError(f"Episode {key} must list its matching numbered objects in order.")
        setattr(output, key, actual)
    if "explicit_dependencies" not in declared:
        output.explicit_dependencies = [
            EpisodeDependency(source_id=s.local_id, target_id=ref)
            for s in sections
            for ref in refs(s.fields.get("uses", s.fields.get("使用的已有结果", "")))
        ]
    if "relation_hints" not in declared:
        output.relation_hints = [
            EpisodeRelationHint.model_validate(
                {"source_id": r.source_id, "target_id": r.target_id, "relation": r.relation}
            )
            for r in relations
            if r.relation in _RELATIONS
        ]
        output.relation_hints.extend(
            EpisodeRelationHint(source_id=d.source_id, target_id=d.target_id, relation="USES")
            for d in output.explicit_dependencies
        )
        for s in sections:
            target = next(
                (
                    s.fields[k]
                    for k in ("target", "目标", "针对对象", "阻碍对象")
                    if s.fields.get(k)
                ),
                "",
            )
            output.relation_hints.extend(
                EpisodeRelationHint(source_id=s.local_id, target_id=ref, relation="TARGETS")
                for ref in refs(target)
            )

    def valid_link(link: EpisodeDependency) -> bool:
        return link.source_id in known and bool(
            link.target_id in known or _DOSSIER_OBJECT.fullmatch(link.target_id)
        )

    for key in ("explicit_dependencies", "relation_hints"):
        links = getattr(output, key)
        if key in declared and any(not valid_link(link) for link in links):
            raise ResearchError(
                "Episode metadata links require local objects or explicit record IDs."
            )
        setattr(output, key, [link for link in links if valid_link(link)])
    return output


def _parse_section(lines: list[str]) -> tuple[dict[str, str], str]:
    fields: dict[str, str] = {}
    offset = 0
    for line in lines:
        match = _FIELD.match(line)
        if match:
            fields[match.group(1).lower()] = match.group(2).strip()
            offset += 1
        elif not line.strip() and offset == len(fields):
            offset += 1
        else:
            break
    return fields, "\n".join(lines[offset:]).strip()


def extract_candidates(ot_dir: Path, episode: ResearchEpisode) -> list[Proposal]:
    """Deterministic, conservative parser; unknown prose remains in the archive."""
    if not episode.problem_id:
        raise ResearchError("Proposal extraction requires an explicit Problem scope.")
    path = source_path(ot_dir, episode.archive_path)
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != episode.content_sha256:
        raise ResearchError(
            "Archived Episode changed; restore its original content before extraction."
        )
    content = raw.decode("utf-8-sig")
    proposed = parse_candidate_proposals(
        content, episode, store.list_claims(ot_dir, episode.problem_id)
    )
    stage_candidates(ot_dir, episode.problem_id, proposed)
    ids = {candidate.candidate_id for candidate in proposed}
    return [c for c in list_candidates(ot_dir, episode.problem_id) if c.candidate_id in ids]


def parse_candidate_proposals(
    content: str, episode: ResearchEpisode, existing_claims: list[ClaimRecord]
) -> list[Proposal]:
    """Use the existing parser without Archive, staging, or Problem Record writes."""
    if has_numbered_headings(content):
        proposed = _numbered_candidates(content, episode)
        if not proposed:
            raise ResearchError("Numbered Episode headings found but no candidates parsed.")
        return proposed
    metadata, offset = _front_matter(content)
    default_target = metadata.get("target_claim_id")
    if default_target is not None and not isinstance(default_target, str):
        raise ResearchError("target_claim_id must be a Claim ID string.")
    lines = content.splitlines()
    math_lines = mathematical_lines(content)
    headings = [
        (i, match)
        for i, line in enumerate(math_lines[offset:], offset)
        if (match := _HEADING.match(line))
    ]
    proposed = []
    for position, (start, match) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        end = next(
            (
                i
                for i in range(start + 1, end)
                if lines[i].strip().upper() == "## CURRENT RESEARCH HANDOFF"
            ),
            end,
        )
        fields, body = _parse_section(lines[start + 1 : end])
        kind = _KINDS[match.group(1).lower()]
        title = (match.group(2) or "").strip()
        if not body and not title:
            continue
        target = fields.get("target") or default_target
        key = f"{episode.episode_id}:{start + 1}"
        candidate_id = "CANDIDATE-" + hashlib.sha256(key.encode()).hexdigest()[:16].upper()
        match_claim = next(
            (c for c in existing_claims if kind == "claim" and c.statement == body), None
        )
        candidate = Proposal(
            candidate_id=candidate_id,
            episode_id=episode.episode_id,
            problem_id=episode.problem_id,
            kind=kind,
            title=title,
            body=body,
            summary=fields.get("summary", ""),
            strategy=fields.get("strategy", ""),
            target_id=match_claim.id if match_claim else target,
            action="SAME_AS" if match_claim else "NEW",
            uses=[item.strip() for item in fields.get("uses", "").split(",") if item.strip()],
            revises_proof_id=fields.get("revises"),
            source_section=lines[start],
            start_line=start + 1,
            end_line=end,
        )
        proposed.append(candidate)
        relates = fields.get("relates", "")
        if relates:
            parts = relates.split(maxsplit=1)
            if len(parts) != 2 or parts[0].upper() not in _RELATIONS:
                raise ResearchError(f"Invalid Relates field at line {start + 1}.")
            relation_id = candidate_id + "-REL"
            proposed.append(
                candidate.model_copy(
                    update={
                        "candidate_id": relation_id,
                        "kind": "relation",
                        "relation": parts[0].upper(),
                        "target_id": parts[1].strip(),
                        "action": "NEW",
                    }
                )
            )
    if not proposed and re.search(r"^##\s+\S+-\d+", "\n".join(math_lines), re.M):
        raise ResearchError("Numbered Episode format is unsupported; no candidates extracted.")
    return proposed


def stage_candidates(ot_dir: Path, problem_id: str, proposed: list[Proposal]) -> None:
    """Append proposals once to the canonical Proposal Store; never commit facts."""
    if any(candidate.problem_id != problem_id for candidate in proposed):
        raise ResearchError("Proposal scope differs from the destination Problem Record.")
    index = _candidate_path(ot_dir, problem_id)
    episodes = {e.episode_id: e for e in list_episodes(ot_dir, problem_id)}
    with file_lock(index):
        known = {item.candidate_id for item in list_candidates(ot_dir, problem_id)}
        for candidate in proposed:
            if candidate.candidate_id not in known:
                from math_research.ledger.provisional import provisional_object_id

                candidate = candidate.model_copy(
                    update={"object_id": provisional_object_id(candidate)}
                )
                if not candidate.thread_ids and candidate.episode_id in episodes:
                    candidate = candidate.model_copy(
                        update={
                            "thread_ids": episodes[candidate.episode_id].thread_ids,
                        }
                    )
                append_jsonl(index, candidate)
                known.add(candidate.candidate_id)


def _numbered_candidates(content: str, episode: ResearchEpisode) -> list[Proposal]:
    sections, end_relations = parse_numbered_episode(content)
    declared, _ = _front_matter(content)
    output_metadata = structured_episode_metadata(content)
    kind_map: dict[str, ProposalKind] = {
        "RESULT": "claim",
        "PROOF": "proof",
        "GAP": "gap",
        "EVIDENCE": "evidence",
        "REFUTATION": "refutation",
        "COUNTEREXAMPLE": "counterexample",
        "REVISION": "revision",
        "FAILED-ATTEMPT": "failed_attempt",
        "BRANCH": "branch",
    }
    body_fields = {
        "RESULT": ("陈述", "statement"),
        "PROOF": ("完整证明", "full proof", "proof"),
        "GAP": ("缺失步骤", "gap"),
        "EVIDENCE": (),
        "REFUTATION": ("反例 / 证明", "反例", "proof"),
        "COUNTEREXAMPLE": (),
        "REVISION": ("修正后的内容", "revision"),
        "FAILED-ATTEMPT": ("失败原因", "reason"),
        "BRANCH": ("研究路线", "approach"),
    }
    proposed: list[Proposal] = []
    known_local = {section.local_id for section in sections}

    def candidate_key(key: str) -> str:
        return (
            "CANDIDATE-"
            + hashlib.sha256(f"{episode.episode_id}:{key}".encode()).hexdigest()[:16].upper()
        )

    for section in sections:
        fields = section.fields
        body = next((fields[key] for key in body_fields[section.kind] if fields.get(key)), "")
        if not body:
            body = section.raw_markdown.split("\n", 1)[-1].strip()
        target_text = next(
            (fields[key] for key in ("目标", "针对对象", "阻碍对象", "target") if fields.get(key)),
            "",
        )
        target_refs = [ref for ref in local_ids(target_text) if ref in known_local]
        explicit_claims = (
            _DOSSIER_OBJECT if section.kind == "COUNTEREXAMPLE" else _DOSSIER_CLAIM
        ).findall(target_text)
        target = target_refs[0] if target_refs else explicit_claims[0] if explicit_claims else None
        uses_text = fields.get("使用的已有结果", fields.get("uses", ""))
        uses = [ref for ref in local_ids(uses_text) if ref in known_local]
        uses.extend(ref for ref in _DOSSIER_OBJECT.findall(uses_text) if ref not in uses)
        proposed.append(
            Proposal(
                candidate_id=candidate_key(section.local_id),
                episode_id=episode.episode_id,
                problem_id=episode.problem_id,
                kind=kind_map[section.kind],
                title=section.local_id,
                body=body,
                summary=fields.get("证明摘要", fields.get("summary", "")),
                target_id=target,
                uses=uses,
                source_section=section.heading,
                start_line=section.start_line,
                end_line=section.end_line,
                local_id=section.local_id,
                raw_markdown=section.raw_markdown,
                source_reported_status=next(
                    (fields[key] for key in ("状态", "当前状态", "status") if fields.get(key)), ""
                ),
                source_fields=fields,
            )
        )
    relation_map: dict[str, RelationKind] = {
        "SAME_AS": "SAME_AS",
        "NO_LINK": "NO_LINK",
        "PROVES": "PROVES",
        "USES": "USES",
        "DEPENDS_ON": "DEPENDS_ON",
        "REFUTES": "REFUTES",
        "INVALIDATES": "INVALIDATES",
        "REVISES": "REVISES",
        "SUPERSEDES": "SUPERSEDES",
        "STRENGTHENS": "STRENGTHENS",
        "WEAKENS": "WEAKENS",
        "SPECIAL_CASE_OF": "SPECIAL_CASE_OF",
        "GENERALIZES": "GENERALIZES",
        "RELATED_TO": "RELATED_TO",
    }
    relation_rows: set[tuple[str, str, str, int, str]] = set()
    for dependency in (
        output_metadata.explicit_dependencies if "explicit_dependencies" in declared else []
    ):
        source = next(item for item in proposed if item.local_id == dependency.source_id)
        if dependency.target_id not in source.uses:
            source.uses.append(dependency.target_id)
    for hint in output_metadata.relation_hints if "relation_hints" in declared else []:
        if hint.relation != "TARGETS":
            relation_rows.add(
                (
                    hint.source_id,
                    hint.relation,
                    hint.target_id,
                    1,
                    "Agent-local relation_hints: "
                    f"{hint.source_id} {hint.relation} {hint.target_id}",
                )
            )
    for relation in end_relations:
        if relation.source_id in known_local and (
            relation.target_id in known_local or _DOSSIER_OBJECT.fullmatch(relation.target_id)
        ):
            relation_rows.add(
                (
                    relation.source_id,
                    relation.relation,
                    relation.target_id,
                    relation.line,
                    relation.raw_markdown,
                )
            )
    for section in sections:
        candidate = next(item for item in proposed if item.local_id == section.local_id)
        if candidate.target_id and section.kind == "PROOF":
            relation_rows.add(
                (
                    section.local_id,
                    "PROVES",
                    candidate.target_id,
                    section.start_line,
                    section.heading,
                )
            )
        if candidate.target_id and section.kind in {"COUNTEREXAMPLE", "REFUTATION"}:
            target_section = next((s for s in sections if s.local_id == candidate.target_id), None)
            if candidate.target_id.startswith("CLAIM-") or (
                target_section and target_section.kind in {"RESULT", "GAP"}
            ):
                relation_rows.add(
                    (
                        section.local_id,
                        "REFUTES",
                        candidate.target_id,
                        section.start_line,
                        section.heading,
                    )
                )
        for ref in candidate.uses:
            relation_rows.add((section.local_id, "USES", ref, section.start_line, section.heading))
    seen_edges: set[tuple[str, str, str]] = set()
    for source_id, wording, target_id, line, raw_line in sorted(relation_rows, key=lambda x: x[3]):
        edge = (source_id, wording, target_id)
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        proposed.append(
            Proposal(
                candidate_id=candidate_key(f"relation:{source_id}:{wording}:{target_id}"),
                episode_id=episode.episode_id,
                problem_id=episode.problem_id,
                kind="relation",
                title=f"{source_id} {wording} {target_id}",
                body=raw_line,
                target_id=target_id,
                source_local_id=source_id,
                relation=relation_map.get(wording, "RELATED_TO"),
                relation_wording=wording,
                source_section=raw_line,
                start_line=line,
                end_line=line,
                raw_markdown=raw_line,
            )
        )
    return proposed


def _source_note(candidate: Proposal) -> str:
    location = f"lines {candidate.start_line}-{candidate.end_line}"
    if candidate.source_fields.get("origin") == "source_digest":
        fields = candidate.source_fields
        return (
            f"Source {fields['source_id']} ({fields['source_filename']}; "
            f"SHA-256 {fields['source_sha256']}), "
            f"Digest {fields['digest_id']}, Proposal {fields['proposal_id']}, "
            f"locator {fields['locator']}; {fields['citation_kind']}; "
            f"supporting span: {fields['supporting_span']}"
        )
    return f"Episode {candidate.episode_id}, {location} ({candidate.source_section})"


def counterexample_parts(body: str) -> tuple[str, str, str]:
    """Read the reviewed full body, rather than an immutable extraction snapshot."""
    sections, _ = parse_numbered_episode(f"## COUNTEREXAMPLE-1\n{body}")
    fields = sections[0].fields
    values = tuple(
        next((fields[key] for key in aliases if fields.get(key)), "")
        for aliases in (
            ("构造 / 反例", "构造", "反例", "construction", "counterexample"),
            ("验证", "verification"),
            ("作用范围", "scope"),
        )
    )
    if not all(values):
        raise ResearchError("Counterexample needs labelled construction, verification and scope.")
    return values[0], values[1], values[2]


@contextmanager
def _review_rollback(base: Path, index: Path) -> Iterator[None]:
    """Undo an interrupted Human Review while its existing review lock is held.

    Only canonical files touched by _commit and the review ledger are backed up.
    Backups are allocated before any commit, so rollback uses rename/unlink even
    if the later write fails because the disk is full. Raw Episodes, Sources and
    advisory artifacts are never copied or rolled back.
    """
    paths = [
        base / name
        for name in (
            "claims.jsonl",
            "approaches.jsonl",
            "failed_attempts.jsonl",
            "status_changes.jsonl",
        )
    ]
    paths.append(index)
    directories = [base / name for name in ("proof_attempts", "counterexamples", "evidence")]
    for directory in directories:
        paths.extend(
            p for p in directory.glob("*") if p.is_file() and p.suffix in {".md", ".jsonl"}
        )
    existing = {p for p in paths if p.is_file()}
    with tempfile.TemporaryDirectory(prefix=".review-rollback-", dir=index.parent) as temporary:
        backups = {}
        for number, path in enumerate(sorted(existing)):
            backup = Path(temporary) / str(number)
            shutil.copyfile(path, backup)
            backups[path] = backup
        try:
            yield
        except BaseException:
            created = set(paths) - existing
            for directory in directories:
                created.update(
                    p
                    for p in directory.glob("*")
                    if p.is_file() and p.suffix in {".md", ".jsonl"} and p not in existing
                )
            for path in created:
                path.unlink(missing_ok=True)
            for path, backup in backups.items():
                # Atomic publication may fail without touching the old review.
                # Do not retry the same denied replace for an unchanged file.
                if not path.is_file() or path.read_bytes() != backup.read_bytes():
                    os.replace(backup, path)
            raise


@human_write
def review_candidate(
    ot_dir: Path,
    problem_id: str,
    candidate_id: str,
    decision: DecisionKind,
    *,
    edits: dict[str, object] | None = None,
) -> ReviewDecision:
    """Commit an explicitly accepted proposal to the dossier; never verify a Claim."""
    store.require_dossier(ot_dir, problem_id)
    candidate = next(
        (c for c in list_candidates(ot_dir, problem_id) if c.candidate_id == candidate_id), None
    )
    if candidate is None:
        raise ResearchError(f"No candidate {candidate_id} in {problem_id}.")
    episode = next(
        (e for e in list_episodes(ot_dir, problem_id) if e.episode_id == candidate.episode_id),
        None,
    )
    if (
        episode is None
        or hashlib.sha256(source_path(ot_dir, episode.archive_path).read_bytes()).hexdigest()
        != episode.content_sha256
    ):
        raise ResearchError("Archived Episode is missing or changed; review refused.")
    index = _review_path(ot_dir, problem_id)
    with file_lock(index), _review_rollback(store.dossier_dir(ot_dir, problem_id), index):
        previous = next(
            (
                r
                for r in list_reviews(ot_dir, problem_id)
                if r.candidate_id == candidate_id and r.decision != "defer"
            ),
            None,
        )
        if previous is not None:
            if previous.decision == decision and not edits:
                return previous
            raise ResearchError("Proposal already decided; create a new Episode for a revision.")
        if edits:
            allowed = {
                "title",
                "body",
                "summary",
                "strategy",
                "target_id",
                "uses",
                "revises_proof_id",
                "relation",
                "action",
            }
            if not set(edits) <= allowed:
                raise ResearchError(
                    "Edits may change only candidate content and links, not provenance."
                )
            candidate = Proposal.model_validate(candidate.model_dump() | edits)
        mapped: str | None = None
        committed_candidate = (
            _resolve_local_references(ot_dir, candidate) if decision == "accept" else candidate
        )
        if decision == "accept":
            from math_research.ledger.source_review import validate_acceptance

            validate_acceptance(ot_dir, candidate, edits)
            mapped = _commit(ot_dir, committed_candidate)
        relation_source: str | None = None
        if candidate.kind == "relation":
            origin_id = candidate.origin_candidate_id or candidate.candidate_id.removesuffix("-REL")
            accepted_origin = next(
                (
                    r
                    for r in list_reviews(ot_dir, problem_id)
                    if r.decision == "accept"
                    and (
                        r.candidate_id == origin_id
                        or (
                            candidate.source_local_id is not None
                            and r.episode_id == candidate.episode_id
                            and r.reviewed_candidate
                            and r.reviewed_candidate.local_id == candidate.source_local_id
                        )
                    )
                ),
                None,
            )
            relation_source = accepted_origin.mapped_id if accepted_origin else origin_id
        record = ReviewDecision(
            candidate_id=candidate_id,
            episode_id=candidate.episode_id,
            problem_id=problem_id,
            decision=decision,
            decided_at=datetime.now().astimezone(),
            mapped_id=mapped,
            reviewed_candidate=candidate,
            source_id=relation_source,
            target_id=committed_candidate.target_id if candidate.kind == "relation" else None,
            relation=candidate.relation if candidate.kind == "relation" else None,
        )
        atomic_append_jsonl(index, record)
        return record


def _resolve_local_references(ot_dir: Path, candidate: Proposal) -> Proposal:
    """Resolve Episode-local names only through accepted review mappings."""
    accepted = {
        review.reviewed_candidate.local_id: review.mapped_id
        for review in list_reviews(ot_dir, candidate.problem_id)
        if review.decision == "accept"
        and review.episode_id == candidate.episode_id
        and review.reviewed_candidate
        and review.reviewed_candidate.local_id
        and review.mapped_id
    }
    episode_locals = {
        item.local_id
        for item in list_candidates(ot_dir, candidate.problem_id, candidate.episode_id)
        if item.local_id
    }
    # Human Review still requires accepted dependencies, but a subsequent Agent
    # may have cited their stable working IDs rather than the original local IDs.
    accepted_reviews = {
        review.candidate_id: review.mapped_id
        for review in list_reviews(ot_dir, candidate.problem_id)
        if review.decision == "accept" and review.mapped_id
    }
    accepted.update(
        {
            item.object_id: accepted_reviews[item.candidate_id]
            for item in list_candidates(ot_dir, candidate.problem_id)
            if item.object_id and item.candidate_id in accepted_reviews
        }
    )

    def resolve(value: str | None) -> str | None:
        if value and value.startswith("CANDIDATE-"):
            reviewed = next(
                (
                    r
                    for r in list_reviews(ot_dir, candidate.problem_id)
                    if r.candidate_id == value and r.decision == "accept"
                ),
                None,
            )
            if reviewed and reviewed.mapped_id:
                return reviewed.mapped_id
            raise ResearchError(f"Accept candidate {value} before this candidate.")
        if value and value in accepted:
            return accepted[value]
        if value and value in episode_locals:
            raise ResearchError(f"Accept local object {value} before this candidate.")
        return value

    return candidate.model_copy(
        update={
            "target_id": resolve(candidate.target_id),
            "uses": [resolve(item) or item for item in candidate.uses],
            "revises_proof_id": resolve(candidate.revises_proof_id),
        }
    )


def _commit(ot_dir: Path, candidate: Proposal) -> str | None:
    pid = candidate.problem_id
    source = _source_note(candidate)
    source_artifacts = [candidate.episode_id]
    if candidate.source_fields.get("origin") == "source_digest":
        source_artifacts.extend(
            candidate.source_fields[key] for key in ("source_id", "digest_id", "proposal_id")
        )
    if candidate.kind == "relation":
        if candidate.semantic_validation_status not in {None, "accepted_by_validator"}:
            raise ResearchError("Only validator-qualified hard proposals can be accepted.")
        if candidate.relation not in LOGICAL_RELATIONS | {"NO_LINK"}:
            raise ResearchError("Topical relevance belongs to Related Memory, not hard relations.")
        if (
            candidate.relation != "NO_LINK"
            and candidate.target_id
            and not _dossier_object_exists(ot_dir, pid, candidate.target_id)
        ):
            raise ResearchError(f"Relation target {candidate.target_id} is absent in {pid}.")
        if candidate.relation != "NO_LINK":
            origin_id = candidate.origin_candidate_id or candidate.candidate_id.removesuffix("-REL")
            accepted_source = next(
                (
                    review
                    for review in list_reviews(ot_dir, pid)
                    if review.decision == "accept"
                    and (
                        review.candidate_id == origin_id
                        or (
                            candidate.source_local_id is not None
                            and review.episode_id == candidate.episode_id
                            and review.reviewed_candidate
                            and review.reviewed_candidate.local_id == candidate.source_local_id
                        )
                    )
                ),
                None,
            )
            if accepted_source is None or not accepted_source.mapped_id:
                raise ResearchError("Accept the source mathematical object before its relation.")
            if candidate.relation in {"REFUTES", "INVALIDATES", "PROVES"}:
                from math_research.ledger.relations.policy import validate_mathematical_relation

                validate_mathematical_relation(
                    ot_dir,
                    pid,
                    accepted_source.mapped_id,
                    candidate.relation,
                    candidate.target_id or "",
                )
        # Confirmed relation remains review metadata; no truth/status promotion.
        return candidate.target_id
    if candidate.kind == "claim" and candidate.action == "SAME_AS":
        if not candidate.target_id or store.get_claim(ot_dir, pid, candidate.target_id) is None:
            raise ResearchError("SAME_AS requires an existing Claim in this dossier.")
        return candidate.target_id
    if candidate.kind == "counterexample":
        from math_research.ledger.records.counterexamples import add_counterexample

        construction, verification, scope = counterexample_parts(candidate.body)
        return add_counterexample(
            ot_dir,
            pid,
            target_id=candidate.target_id or "",
            construction=construction,
            verification=verification,
            scope=scope,
            title=candidate.title,
            notes=source,
            source_artifacts=source_artifacts,
        ).id
    if candidate.kind in {"claim", "gap"}:
        if not candidate.body:
            raise ResearchError("Claim-like candidate needs a statement body.")
        kind: ClaimType = "CLAIM"
        if candidate.kind == "gap":
            kind = "OPEN_GAP"
        elif (
            candidate.kind == "claim" and candidate.source_reported_status == "computational_result"
        ):
            kind = "EXPERIMENTAL_OBSERVATION"
        record = claims.add_claim(
            ot_dir,
            pid,
            claim_type=kind,
            statement=candidate.body,
            source_artifacts=source_artifacts,
            notes=f"Source-reported status: {candidate.source_reported_status or 'unspecified'}\n"
            f"{candidate.summary}\n{source}".strip(),
        )
        return record.id
    if candidate.kind in {"proof", "refutation"}:
        if (
            not candidate.body
            or not candidate.target_id
            or store.get_claim(ot_dir, pid, candidate.target_id) is None
        ):
            raise ResearchError(
                "Proof needs a full body and existing target Claim; review its Claim first."
            )
        for used in candidate.uses:
            if store.get_claim(ot_dir, pid, used) is None and not any(
                p.id == used for p in store.list_proof_attempts(ot_dir, pid)
            ):
                raise ResearchError(f"Proof USES Claim {used} is absent in {pid}.")
        if candidate.revises_proof_id and not any(
            p.id == candidate.revises_proof_id for p in store.list_proof_attempts(ot_dir, pid)
        ):
            raise ResearchError("Revised Proof does not exist in this dossier.")
        uses = ", ".join(candidate.uses) or "none recorded"
        revision = candidate.revises_proof_id or "none"
        body = f"<!-- {source} -->\n\nUses: {uses}\nRevises: {revision}\n\n{candidate.body}"
        proof = claims.add_proof_attempt(
            ot_dir,
            pid,
            title=candidate.title or "Episode candidate proof",
            body=body,
            scope="exploration",
            claim_links=[candidate.target_id],
            conclusion_relation="REFUTES" if candidate.kind == "refutation" else "PROVES",
        )
        return proof.id
    if candidate.kind == "evidence":
        from math_research.ledger.records.evidence_content import reviewed_evidence_fields

        if not candidate.target_id or store.get_claim(ot_dir, pid, candidate.target_id) is None:
            raise ResearchError("Evidence needs an accepted target Claim; review the Claim first.")
        fields = reviewed_evidence_fields(candidate.body, candidate.source_fields)
        fields["summary"] += f"\n\n{source}"
        evidence, _ = claims.add_evidence(
            ot_dir,
            pid,
            candidate.target_id,
            direction="neutral",
            source_artifacts=source_artifacts,
            **fields,
        )
        return evidence.id
    if candidate.kind == "revision":
        if "invalidates" in candidate.source_fields.get(
            "变更类型", ""
        ).lower() or "作废" in candidate.source_fields.get("变更类型", ""):
            failed = store.add_failed_attempt(
                ot_dir,
                pid,
                attempted_method=candidate.title,
                summary=candidate.source_fields.get("原因", ""),
                reason_failed=candidate.raw_markdown,
                artifacts=[candidate.episode_id],
                tags=[source],
            )
            return failed.id
        approach = Approach(
            id=f"APPROACH-{len(store.list_approaches(ot_dir, pid)) + 1:04d}",
            problem_id=pid,
            strategy="proof_sketch",
            objective=candidate.title,
            method=candidate.raw_markdown,
            notes=source,
            resulting_artifacts=[candidate.episode_id],
        )
        store.add_approach(ot_dir, approach)
        return approach.id
    if candidate.kind == "failed_attempt":
        if not candidate.body:
            raise ResearchError("Failed Attempt needs a reason/body.")
        if (
            candidate.target_id
            and candidate.target_id.startswith("PROOF-")
            and not any(p.id == candidate.target_id for p in store.list_proof_attempts(ot_dir, pid))
        ):
            raise ResearchError(f"Failed Proof {candidate.target_id} is absent in {pid}.")
        failed = store.add_failed_attempt(
            ot_dir,
            pid,
            attempted_method=candidate.title or "Episode failed approach",
            summary=candidate.summary,
            reason_failed=candidate.body,
            artifacts=[
                *source_artifacts,
                *([candidate.target_id] if candidate.target_id else []),
            ],
            tags=[source],
        )
        return failed.id
    if candidate.kind == "branch":
        if not candidate.body:
            raise ResearchError("Branch needs a research approach body.")
        existing = store.list_approaches(ot_dir, pid)
        approach = Approach(
            id=f"APPROACH-{len(existing) + 1:04d}",
            problem_id=pid,
            strategy="proof_sketch",
            objective=candidate.title,
            method=candidate.body,
            notes=f"{source}\nOriginal strategy: {candidate.strategy}".strip(),
            resulting_artifacts=[candidate.episode_id],
        )
        store.add_approach(ot_dir, approach)
        return approach.id
    raise ResearchError(f"Unsupported candidate kind: {candidate.kind}")


def _dossier_object_exists(ot_dir: Path, problem_id: str, object_id: str) -> bool:
    return bool(
        store.get_claim(ot_dir, problem_id, object_id)
        or any(
            item.id == object_id
            for items in (
                store.list_proof_attempts(ot_dir, problem_id),
                store.list_evidence(ot_dir, problem_id),
                store.list_failed_attempts(ot_dir, problem_id),
                store.list_approaches(ot_dir, problem_id),
                store.list_counterexamples(ot_dir, problem_id),
            )
            for item in items
        )
    )
