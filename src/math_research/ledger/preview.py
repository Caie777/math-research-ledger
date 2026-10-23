"""One deterministic Episode preview over the existing decomposition parser.

Diagnostics concern persistence/identity, never mathematical correctness.
This layer is read-only and does not acquire a write lock or create state.
"""

import hashlib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from math_research.core.errors import ResearchError
from math_research.core.limits import MAX_UPLOAD_BYTES
from math_research.ledger.decomposition import parse_numbered_episode
from math_research.ledger.episodes import (
    EpisodeOutputMetadata,
    ResearchEpisode,
    _front_matter,
    checkpoint_metadata,
    list_candidates,
    list_episodes,
    list_reviews,
    parse_candidate_proposals,
    structured_episode_metadata,
)
from math_research.ledger.identity import ScopedIdentityResolver, reference_tokens, working_ref
from math_research.ledger.provisional import provisional_object_id
from math_research.ledger.records import store

TARGET_KEYS = ("target", "目标", "针对对象", "阻碍对象", "旧对象")


def preview_episode(state: Path, problem_id: str, filename: str, raw: bytes) -> dict:
    store.require_dossier(state, problem_id)
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ResearchError("Episode must contain at most 10 MiB of nonempty UTF-8 Markdown.")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ResearchError("Episode must be UTF-8.") from exc
    digest = hashlib.sha256(raw).hexdigest()
    old = next((e for e in list_episodes(state, problem_id) if e.content_sha256 == digest), None)
    episode = old or ResearchEpisode(
        episode_id="EPISODE-"
        + hashlib.sha256(f"project-source-v1:{digest}".encode()).hexdigest()[:16].upper(),
        problem_id=problem_id,
        archive_path="preview.md",
        imported_at=datetime.now(UTC),
        source_filename=Path(filename).name,
        content_sha256=digest,
    )
    diagnostics: list[dict] = []

    def issue(severity, code, message, candidate=None, refs=(), hint=None):
        diagnostics.append(
            {
                "severity": severity,
                "code": code,
                "message": message,
                "start_line": candidate.start_line if candidate else None,
                "end_line": candidate.end_line if candidate else None,
                "related_refs": list(refs),
                "remediation": hint,
            }
        )

    sections, _ = parse_numbered_episode(content)
    for section in sections:
        substantive = set(section.fields) - {
            *TARGET_KEYS,
            "uses",
            "使用的已有结果",
            "status",
            "状态",
            "当前状态",
            "与已有对象的关系",
        }
        body = section.raw_markdown.partition("\n")[2].strip()
        if not body or (section.fields and not any(section.fields[k].strip() for k in substantive)):
            issue(
                "ERROR",
                "MISSING_CONTENT",
                "No research content beyond reference/status fields.",
                section,
                [section.local_id],
                "Supply a statement, argument, gap, result or route content.",
            )
        if sum(s.local_id == section.local_id for s in sections) > 1:
            issue(
                "ERROR",
                "DUPLICATE_LOCAL_ID",
                "Local ID has multiple definitions.",
                section,
                [section.local_id],
                "Assign a unique local ID and update its explicit references.",
            )
        counts = Counter(key for key, _, _ in section.field_spans)
        for key, count in counts.items():
            if count > 1 and key not in {*TARGET_KEYS, "uses", "使用的已有结果"}:
                issue("ERROR", "DUPLICATE_FIELD", f"Repeated {key} has ambiguous meaning.", section)
    proposals = []
    metadata = EpisodeOutputMetadata()
    declared: dict = {}
    try:
        declared, _ = _front_matter(content)
        proposals = parse_candidate_proposals(
            content, episode, store.list_claims(state, problem_id)
        )
        delta, directions = checkpoint_metadata(content, digest, proposals)
        metadata = structured_episode_metadata(content).model_copy(
            update={
                "state_delta": delta,
                "next_research_directions": directions,
            }
        )
    except (ResearchError, ValidationError, yaml.YAMLError, ValueError) as exc:
        issue(
            "ERROR",
            "INVALID_STRUCTURE",
            str(exc),
            hint="Correct the reported field; raw-only archiving remains available.",
        )

    # New authored identities are deterministic; old proposal/review aliases retain their history.
    existing = ScopedIdentityResolver.from_state(state)
    saved, reviews = [], []
    for problem in store.list_dossiers(state):
        saved.extend(list_candidates(state, problem.id))
        reviews.extend(list_reviews(state, problem.id))
    known = {c.candidate_id for c in saved}
    fresh = [
        c.model_copy(update={"object_id": provisional_object_id(c)})
        for c in proposals
        if c.kind != "relation" and c.candidate_id not in known
    ]
    resolver = ScopedIdentityResolver(
        [*existing.refs.values(), *(working_ref(c) for c in fresh)], [*saved, *fresh], reviews
    )
    bindings: list[dict] = []
    pin_versions: dict[str, set[str]] = {}
    for pin in metadata.input_versions:
        resolution = resolver.resolve(pin.ref.qualified_id)
        key = (resolution.ref or pin.ref).qualified_id
        pin_versions.setdefault(key, set()).add(pin.version)
    for key, versions in pin_versions.items():
        if len(versions) > 1:
            issue(
                "ERROR",
                "CONFLICTING_INPUT_VERSIONS",
                "One input has conflicting authored versions.",
                refs=[key],
            )
    current_entries = None

    def resolve(reference, candidate, role, *, required=False):
        nonlocal current_entries
        resolution = resolver.resolve(
            reference, problem_id=problem_id, episode_id=episode.episode_id
        )
        key = resolution.ref.qualified_id if resolution.ref else None
        binding = {
            "source": candidate.local_id or candidate.candidate_id,
            "role": role,
            "reference": reference,
            "resolved_ref": key,
            "resolution_reason": resolution.reason,
            "version_status": "UNRESOLVED",
            "expected_versions": sorted(pin_versions.get(key or reference, set())),
        }
        if key is None:
            issue(
                "ERROR" if required or resolution.reason == "SCOPE_AMBIGUITY" else "WARNING",
                resolution.reason or "UNRESOLVED_REFERENCE",
                "Explicit reference cannot be uniquely resolved.",
                candidate,
                [reference],
                "Use a qualified identity or correct the Episode-local reference.",
            )
        else:
            authored = any(working_ref(c) == resolution.ref for c in fresh)
            versions = pin_versions.get(key, set())
            if authored:
                binding["version_status"] = "AUTHORED_SNAPSHOT"
            elif not versions:
                binding["version_status"] = "MISSING"
                issue(
                    "WARNING",
                    "MISSING_INPUT_VERSION",
                    "Historical input version is unknown; freshness remains conservative.",
                    candidate,
                    [key],
                    "Supply the version actually used; never fill it from today's version.",
                )
            else:
                if current_entries is None:
                    from math_research.ledger.manifest import Ledger

                    current_entries = {e.qualified_id: e for e in Ledger(state).objects()}
                entry = current_entries.get(key)
                valid = (
                    entry is not None
                    and versions == {entry.version}
                    and entry.integrity != "FAILED"
                )
                binding["version_status"] = "MATCHING" if valid else "STALE"
                if not valid:
                    issue(
                        "WARNING",
                        "STALE_INPUT_VERSION",
                        "Authored input pin differs from the readable current snapshot.",
                        candidate,
                        [key],
                    )
        bindings.append(binding)
        return key

    normalized = []
    for candidate in proposals:
        target_text = "\n".join(candidate.source_fields.get(key, "") for key in TARGET_KEYS).strip()
        target_refs = (
            reference_tokens(target_text)
            if target_text
            else reference_tokens(candidate.target_id or "")
        )
        if candidate.local_id:
            target_refs = list(
                dict.fromkeys(
                    [
                        *target_refs,
                        *(
                            hint.target_id
                            for hint in metadata.relation_hints
                            if hint.source_id == candidate.local_id and hint.relation == "TARGETS"
                        ),
                    ]
                )
            )
        if candidate.kind == "relation" and candidate.target_id:
            target_refs = [candidate.target_id]
        required = candidate.kind in {"proof", "refutation", "revision"} or (
            candidate.kind == "relation"
            and candidate.relation in {"REVISES", "REFUTES", "INVALIDATES"}
        )
        if required and not target_refs:
            issue(
                "ERROR",
                "MISSING_TARGET",
                "This proposal requires one explicit target to determine its meaning.",
                candidate,
                hint="Label the target (旧对象 is supported for REVISION).",
            )
        targets = [resolve(value, candidate, "target", required=required) for value in target_refs]
        unique = {
            key or f"unresolved:{value}" for key, value in zip(targets, target_refs, strict=True)
        }
        if len(unique) > 1:
            issue(
                "ERROR",
                "AMBIGUOUS_TARGET",
                "Distinct target objects cannot be reduced to the first match.",
                candidate,
                target_refs,
            )
        target = (
            targets[0]
            if len(target_refs) > 1 and len(unique) == 1
            else target_refs[0]
            if len(target_refs) == 1
            else candidate.target_id
        )
        if target_text and not target_refs:
            issue(
                "ERROR" if required else "WARNING",
                "UNRESOLVED_TARGET",
                "Target field contains no explicit object reference.",
                candidate,
            )
        uses = []
        uses_text = "\n".join(
            candidate.source_fields.get(key, "") for key in ("uses", "使用的已有结果")
        ).strip()
        if uses_text and not candidate.uses:
            issue(
                "WARNING",
                "UNRESOLVED_USES",
                "Uses contains no explicit object identity; no dependency is inferred.",
                candidate,
            )
        for value in candidate.uses:
            resolve(value, candidate, "uses")
            uses.append(value)  # Preserve authored local names and historical alias semantics.
        if not candidate.body.strip() and not candidate.title.strip():
            issue(
                "ERROR",
                "MISSING_CONTENT",
                "Candidate needs content to preserve a meaningful source span.",
                candidate,
            )
        normalized.append(
            candidate.model_copy(update={"target_id": target, "uses": list(dict.fromkeys(uses))})
        )
    for assertion in metadata.state_delta:
        if assertion.action in {"Revised", "Refuted", "Invalidated"}:
            source = next(
                (
                    c
                    for c in normalized
                    if assertion.reference in {c.local_id, c.candidate_id, provisional_object_id(c)}
                ),
                None,
            )
            if source and source.target_id:
                continue  # Its target and source span were checked above.
            # A front-matter assertion can refer directly to an existing qualified object.
            holder: Any = source
            if source is None:
                from types import SimpleNamespace

                holder = SimpleNamespace(
                    local_id=None,
                    candidate_id="state_delta",
                    start_line=assertion.start_line,
                    end_line=assertion.end_line,
                )
            resolve(assertion.reference, holder, "state_delta", required=True)
    if not normalized:
        issue(
            "INFO",
            "ADVISORY_ONLY" if metadata.next_research_directions else "RAW_ONLY",
            "0 confirmed research increments; raw Markdown can be archived without objects.",
        )
    return {
        "sha256": digest,
        "episode_id": episode.episode_id,
        "detected_format": "numbered" if sections else "legacy" if normalized else "raw",
        "schema": declared.get("schema_version", declared.get("schema", "legacy-unspecified")),
        "candidates": normalized,
        "local_ids": [s.local_id for s in sections],
        "metadata": metadata,
        "bindings": bindings,
        "diagnostics": diagnostics,
        "can_publish": not any(d["severity"] == "ERROR" for d in diagnostics),
        "confirmed_research_increments": 0,
        "provisional_object_count": sum(c.kind != "relation" for c in normalized),
        "next_directions_advisory": True,
    }
