"""Public operational handoffs and a regenerable, read-only Episode projection.

No planning ledger, model calls, mathematical decisions or persistent cache.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, Field

from math_research.memory.archive import _verified_bytes
from math_research.memory.episodes import list_candidates, list_episodes, list_reviews
from math_research.memory.state import KnowledgeState, KnowledgeStateResolver
from math_research.memory.target import ResearchTarget, validate_research_target

HANDOFF_HEADING = "## CURRENT RESEARCH HANDOFF"
HANDOFF_FIELDS = (
    "What changed this session",
    "Resolved / no longer needs work",
    "Active obstacles",
    "Active routes worth continuing",
    "Routes not worth repeating",
    "Boundary / counterexample status",
    "Next worthwhile directions",
)
_ID = re.compile(r"\b(?:CLAIM|PROOF|APPROACH|APPR|CANDIDATE|COUNTEREXAMPLE)-[A-Z0-9-]+\b")


def read_handoff(content: str) -> tuple[str | None, dict[str, str]]:
    """Read a reserved operational H2 through the next H1, never infer math truth."""
    lines = content.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.strip().upper() == HANDOFF_HEADING), None
    )
    if start is None:
        return None, {}
    target = None
    fields: dict[str, str] = {}
    current = ""
    for line in lines[start + 1 :]:
        if line.startswith("# "):
            break
        if match := re.fullmatch(r"Target:\s*(CLAIM-(?:\d+|P[0-9A-F]{16}))", line.strip(), re.I):
            target = match.group(1).upper()
        if line.startswith("### "):
            title = line[4:].strip()
            current = next((f for f in HANDOFF_FIELDS if f.casefold() == title.casefold()), "")
            if current:
                fields[current] = ""
        elif current:
            fields[current] += line + "\n"
    return target, {key: value.strip()[:2400] for key, value in fields.items()}


def ensure_handoff(
    content: str,
    target_id: str,
    stop_reason: str | None,
    *,
    completion_state: str | None = None,
) -> str:
    """Guarantee an honest handoff on a NEW output, including offline fallback Episodes."""
    from math_research.memory.decomposition import parse_numbered_episode

    _, supplied = read_handoff(content)
    sections, _ = parse_numbered_episode(content)
    fallback = {
        HANDOFF_FIELDS[0]: "Public Episode objects: "
        + (", ".join(s.local_id for s in sections) or "none")
        + f". Session stop: {stop_reason or 'unknown'}; inspect their source sections.",
        HANDOFF_FIELDS[
            1
        ]: "No additional resolution asserted by the handoff; consult canonical Resolver.",
        HANDOFF_FIELDS[2]: "\n".join(
            s.raw_markdown[:500].replace("\n", " ") for s in sections if s.kind == "GAP"
        )
        or "No explicit obstacle summary provided; inspect public observations before continuing.",
        HANDOFF_FIELDS[3]: "No specific continuation route explicitly recorded.",
        HANDOFF_FIELDS[4]: "\n".join(
            s.raw_markdown[:500].replace("\n", " ") for s in sections if s.kind == "FAILED-ATTEMPT"
        )
        or "No additional excluded route asserted.",
        HANDOFF_FIELDS[5]: "\n".join(
            s.raw_markdown[:500].replace("\n", " ")
            for s in sections
            if s.kind in {"COUNTEREXAMPLE", "EVIDENCE"}
        )
        or "No additional boundary result asserted; finite evidence is not universal proof.",
        HANDOFF_FIELDS[6]: (
            "Inspect the current obstacle and latest public source IDs; "
            "choose a worthwhile route without repeating excluded work."
        ),
    }
    # Normalize only this new output. Old archived Episodes are never rewritten.
    match = re.search(r"^## CURRENT RESEARCH HANDOFF\s*$", content, re.M | re.I)
    suffix = ""
    if match:
        next_h1 = re.search(r"^# \S", content[match.end() :], re.M)
        block = content[match.end() :]
        if next_h1:
            suffix = content[match.end() + next_h1.start() :]
            block = block[: next_h1.start()]
        completion = re.search(
            r"^Session completion:\s*"
            r"(CONTINUE|TARGET_RESOLVED|ROUTES_EXHAUSTED|LOW_MARGINAL_VALUE)\s*$",
            block,
            re.M,
        )
        if completion_state is None and completion:
            completion_state = completion.group(1)
        content = content[: match.start()].rstrip()
    # Reserved H1 may already precede H2 (even twice in old model output).
    # Normalize only this NEW Episode; do not rewrite archived source history.
    content = re.sub(r"^# Research operations[ \t]*\r?$", "", content, flags=re.M | re.I).rstrip()
    handoff = (
        "\n\n# Research operations\n\n"
        + HANDOFF_HEADING
        + "\n\n"
        + f"Target: {target_id}\n\n"
        + (f"Session completion: {completion_state}\n\n" if completion_state else "")
        + "Operational planning; PROVISIONAL / source-reported. Not a theorem or Human Accept.\n"
    )
    for field in HANDOFF_FIELDS:
        handoff += f"\n### {field}\n\n{supplied.get(field) or fallback[field]}\n"
    return content.rstrip() + handoff + ("\n\n" + suffix if suffix else "")


def _bullets(text: str) -> list[str]:
    return [
        re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()[:500]
        for line in text.splitlines()
        if line.strip()
    ][:8]


def _route(text: str) -> str:
    return (
        re.sub(r"\s+", " ", re.split(r"(?:;?\s*reason\s*:|原因\s*:)", text, flags=re.I)[0])
        .strip(" .;：:")
        .casefold()
    )


class CurrentResearchState(BaseModel):
    target_id: str
    research_status: str
    latest_handoff_episode_id: str | None = None
    handoff: dict[str, str] = Field(default_factory=dict)
    resolved_subproblems: list[str] = Field(default_factory=list)
    active_routes: list[str] = Field(default_factory=list)
    active_obstacles: list[str] = Field(default_factory=list)
    unresolved_subclaims: list[str] = Field(default_factory=list)
    boundaries: list[str] = Field(default_factory=list)
    blocked_routes: list[str] = Field(default_factory=list)
    latest_evidence: list[str] = Field(default_factory=list)
    next_directions: list[str] = Field(default_factory=list)
    cold_episode_ids: list[str] = Field(default_factory=list)
    markdown: str = ""


def resolved_work_ids(states: dict[str, KnowledgeState]) -> set[str]:
    """Existing resolution witnesses can close research without formal verification.

    Resolver marks OPEN_GAP as RESOLVED, but retains CURRENT for a proved Claim.
    Both can be faded operationally; their actual authority/state is unchanged.
    """
    return {
        oid
        for oid, state in states.items()
        if state.authority == "CANONICAL"
        and (
            state.research_state == "RESOLVED"
            or state.research_state == "CURRENT"
            and any(
                states.get(source)
                and states[source].authority == "CANONICAL"
                and states[source].kind == "proof"
                and states[source].usable_premise
                for source in state.resolution_ids
            )
        )
    }


def current_research_state(
    ot_dir: Path,
    target: ResearchTarget,
    *,
    include_provisional: bool = True,
    states: dict[str, KnowledgeState] | None = None,
) -> CurrentResearchState:
    """Newest explicit handoff wins; later explicit failures/Resolver states update it.

    No fuzzy route matching or inferred mathematical resolution. Historical handoff
    directions remain in immutable cold sources rather than active planning text.
    """
    validate_research_target(ot_dir, target)
    pid, tid = target.problem_id, target.node_id
    states = states if states is not None else KnowledgeStateResolver(ot_dir).resolve(pid)
    candidates = list_candidates(ot_dir, pid)
    from math_research.memory.provisional import episode_local_mapping

    mappings = {
        eid: episode_local_mapping(ot_dir, pid, eid) for eid in {c.episode_id for c in candidates}
    }
    reviews = {r.candidate_id: r for r in list_reviews(ot_dir, pid)}
    related = [
        c
        for c in candidates
        if (
            c.object_id == tid
            or mappings[c.episode_id].get(c.target_id or "", c.target_id) == tid
            or tid in c.uses
        )
        and (
            c.source_fields.get("origin") != "source_digest"
            or states[c.candidate_id].canonical_id is not None
        )
    ]
    if not include_provisional:
        related = [c for c in related if states[c.candidate_id].authority == "CANONICAL"]
    episodes = sorted(
        (
            e
            for e in list_episodes(ot_dir, pid)
            if not (e.provenance or "").startswith("SOURCE_DIGEST:")
        ),
        key=lambda e: (e.imported_at, e.episode_id),
        reverse=True,
    )
    episode_dates = {e.episode_id: e.imported_at for e in list_episodes(ot_dir, pid)}
    relevant_ids = {c.episode_id for c in related}
    result = CurrentResearchState(target_id=tid, research_status=states[tid].research_state)
    latest_at = None
    if include_provisional:
        for episode in episodes:
            # Read existing source service; never concatenate the archive into the prompt.
            raw = _verified_bytes(ot_dir, episode).decode("utf-8")
            explicit_target, handoff = read_handoff(raw)
            if handoff and (
                explicit_target == tid
                or explicit_target is None
                and episode.episode_id in relevant_ids
            ):
                result.latest_handoff_episode_id = episode.episode_id
                result.handoff = handoff
                latest_at = episode.imported_at
                relevant_ids.add(episode.episode_id)
                break
    result.cold_episode_ids = [e.episode_id for e in episodes if e.episode_id in relevant_ids][:12]
    h = result.handoff
    result.active_routes = _bullets(h.get(HANDOFF_FIELDS[3], ""))
    result.active_obstacles = _bullets(h.get(HANDOFF_FIELDS[2], ""))
    result.blocked_routes = _bullets(h.get(HANDOFF_FIELDS[4], ""))
    result.boundaries = _bullets(h.get(HANDOFF_FIELDS[5], ""))
    result.next_directions = _bullets(h.get(HANDOFF_FIELDS[6], ""))
    related.sort(key=lambda c: (episode_dates.get(c.episode_id), c.start_line), reverse=True)
    blocked_names: list[str] = []
    blocked_ids: set[str] = set()
    for c in related:
        state = states[c.candidate_id]
        authority = (
            f"{state.authority}; {state.verification}; "
            f"source-reported={c.source_reported_status or 'unspecified'}"
        )
        if c.kind == "failed_attempt":
            route = c.source_fields.get("研究路线") or c.source_fields.get("approach") or c.strategy
            result.blocked_routes.append(
                f"{c.candidate_id} [{authority}]: {route or c.title}; {c.body[:300]}"
            )
            if latest_at is None or episode_dates[c.episode_id] > latest_at:
                if route:
                    blocked_names.append(_route(route))
                blocked_ids.update(i for i in [c.target_id, *c.uses] if i and i != tid)
        if c.kind in {"claim", "gap"} and state.canonical_id is None and state.review != "REJECTED":
            result.unresolved_subclaims.append(f"{c.candidate_id} [{authority}]: {c.body[:300]}")
        if c.kind in {"counterexample", "refutation"}:
            result.boundaries.append(f"{c.candidate_id} [{authority}]: {c.body[:300]}")
        if c.kind == "evidence":
            result.latest_evidence.append(f"{c.candidate_id} [{authority}]: {c.body[:300]}")
    for entry in _bullets(h.get(HANDOFF_FIELDS[4], "")):
        blocked_names.append(_route(entry))
    related_object_ids = {tid, *states[tid].dependencies}
    related_object_ids.update(_ID.findall("\n".join(h.values())))
    for c in related:
        review = reviews.get(c.candidate_id)
        if review and review.mapped_id:
            related_object_ids.add(review.mapped_id)
        related_object_ids.update(c.uses)
    closed = resolved_work_ids(states)
    resolved_ids: set[str] = set()
    for oid in sorted(related_object_ids):
        object_state = states.get(oid)
        if not object_state:
            continue
        if oid != tid and oid in closed:
            resolved_ids.add(oid)
            result.resolved_subproblems.append(
                f"{oid} [CANONICAL; {object_state.verification}] → "
                + (", ".join(object_state.resolution_ids) or "Resolver")
                + "; research resolution witness, not automatic verification; "
                + "confirmations: "
                + ("; ".join(object_state.relation_confirmations)[:500] or "Resolver")
                + "; "
                "do not redo; read full proof by ID if needed."
            )
        if object_state.research_state in {"REVISED", "SUPERSEDED", "REFUTED", "INVALIDATED"}:
            blocked_ids.add(oid)
            result.blocked_routes.append(
                f"{oid}: {object_state.research_state}; successor IDs: "
                + (", ".join(object_state.replacement_ids) or "none")
            )
        if object_state.kind in {"OPEN_GAP", "gap"} and object_state.research_state == "OPEN":
            result.active_obstacles.append(f"{oid} [{object_state.authority}]: unresolved gap")

    def active(entry: str) -> bool:
        return _route(entry) not in blocked_names and not set(_ID.findall(entry)) & (
            blocked_ids | resolved_ids
        )

    result.active_routes = [entry for entry in result.active_routes if active(entry)]
    result.next_directions = [entry for entry in result.next_directions if active(entry)]
    parts = [
        f"# Current Research State: {tid}\nStatus: {result.research_status}\n"
        "Read-only projection. Handoff/planning is PROVISIONAL/source-reported, "
        "not a mathematical premise.\n"
        "CANONICAL, verification and MODEL_CONFIRMED labels keep their existing meanings.\n"
    ]
    for title, entries in [
        ("Resolved subproblems (WARM summaries)", result.resolved_subproblems),
        ("Current active routes (HOT)", result.active_routes),
        ("Active obstacles (HOT)", result.active_obstacles),
        ("Unresolved subclaims (PROVISIONAL)", result.unresolved_subclaims),
        ("Counterexamples / boundaries", result.boundaries),
        ("Blocked / failed / superseded routes (WARM)", result.blocked_routes),
        ("Latest finite evidence (WARM)", result.latest_evidence),
        ("Next worthwhile directions (HOT)", result.next_directions),
    ]:
        parts.append(
            f"\n## {title}\n"
            + (
                "\n".join("- " + entry.replace("\n", " ") for entry in entries[:6])
                or "No explicit state recorded."
            )
            + "\n"
        )
    if result.latest_handoff_episode_id:
        parts.append(
            "\n## Latest Research Handoff\nSource: "
            + result.latest_handoff_episode_id
            + " [PROVISIONAL/source-reported]\n"
            + h.get(HANDOFF_FIELDS[0], "")[:2000]
            + "\n"
            + "Source-reported resolved work (not canonical resolution): "
            + h.get(HANDOFF_FIELDS[1], "")[:1500]
            + "\n"
        )
    parts.append(
        "\nCOLD sources (read by Episode ID): " + ", ".join(result.cold_episode_ids) + "\n"
    )
    result.markdown = "".join(parts)
    return result
