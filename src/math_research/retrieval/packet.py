"""Budgeted external-harness view over the existing selection policy and typed ledger."""

from typing import Literal
from pathlib import Path

from pydantic import BaseModel, Field

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.manifest import Ledger
from math_research.ledger.target import ResearchTarget
from math_research.retrieval.context import ResearchContextBuilder, _excerpt, estimate_tokens
from math_research.retrieval.index import IndexDoc, search_documents
from math_research.services.research import list_objects


class PacketItem(BaseModel):
    ref: ObjectRef
    version: str
    label: Literal["TRUSTED", "PROVISIONAL", "STALE", "FAILED", "HISTORICAL"]
    tier: Literal["MUST", "SHOULD", "MAY"]
    authority: str
    verification: str
    review: str
    freshness: str
    research_state: str
    usable_working_premise: bool
    trusted_formal_premise: bool
    provenance: list[str]
    dependencies: list[dict]
    artifact_refs: list[dict]
    content: str = ""
    full_text: bool = False
    truncated: bool = True


class ContextPacket(BaseModel):
    schema_version: Literal[1] = 1
    target: ObjectRef
    source_version: str
    purpose: str
    protocol: str = "Canonical is not verified. Checked is not accepted. Soft review is advisory. STALE/HISTORICAL/FAILED are not positive premises. PROVISIONAL is a working assumption only. Retrieve omitted originals before relying on them. Return a Research Episode with IDs and source spans."
    items: list[PacketItem] = Field(default_factory=list)
    required_record_ids: list[str]
    required_omitted_ids: list[str] = Field(default_factory=list)
    excluded: list[dict] = Field(default_factory=list)
    complete: bool = False
    required_context_truncated: bool = True
    token_budget: int
    token_estimate: int = 0
    estimator: str = "ceil(UTF-8 bytes / 3), entire serialized JSON"


def packet_tokens(packet: ContextPacket) -> int:
    # Iterate until the number of digits in the estimate is itself accounted for.
    for _ in range(8):
        count = estimate_tokens(packet.model_dump_json())
        if count == packet.token_estimate:
            return count
        packet.token_estimate = count
    return estimate_tokens(packet.model_dump_json())


def export_context_packet(state: Path, target: ObjectRef, *, query: str = "", purpose: str = "CONTINUE_RESEARCH", token_budget: int = 8000, include_provisional: bool = True, max_dependency_nodes: int = 64) -> ContextPacket:
    if not 256 <= token_budget <= 200000 or not 1 <= max_dependency_nodes <= 256:
        raise ResearchError("Budget must be 256..200000 and dependency bound 1..256.")
    ledger = Ledger(state)
    version = ledger.source_version(target.problem_id)
    views = {v.object.qualified_id: v for v in list_objects(state, target.problem_id)}
    if target.qualified_id not in views:
        raise ResearchError("Context target is absent in this scope.")
    root = views[target.qualified_id]
    if not include_provisional and root.authority == "PROVISIONAL":
        raise ResearchError("Target requires include_provisional=true.")
    base = None
    if target.kind in {"claim", "gap"}:
        base = ResearchContextBuilder(state).build(ResearchTarget(kind="claim", problem_id=target.problem_id, node_id=target.object_id), purpose=purpose, token_budget=token_budget, include_provisional=include_provisional, query=query)
    required, missing, queue = set(), set(), [target.qualified_id]
    while queue and len(required) < max_dependency_nodes:
        key = queue.pop(0)
        if key in required:
            continue
        if key not in views:
            missing.add(key)
            continue
        required.add(key)
        queue.extend(d.target.qualified_id for d in views[key].object.dependencies if d.target.qualified_id not in required)
    missing.update(key for key in queue if key not in required)
    # Preserve the mature selector's required proof/context decisions.
    priorities = {}
    for item in base.items if base else []:
        matches = [key for key, v in views.items() if v.object.ref.object_id == item.object_id]
        for key in matches:
            priorities[key] = item.priority
            if item.mandatory:
                required.add(key)
    docs = [IndexDoc(artifact_id=k, artifact_type=v.object.ref.kind, title=v.object.record.get("title", v.object.record.get("term", "")), text=v.object.full_content) for k, v in views.items()]
    scores = {doc.artifact_id: score for doc, score in search_documents(docs, query or root.object.full_content[:1000], k=100)}
    candidates = required | priorities.keys() | scores.keys()
    # Failed routes explicitly attached to the target remain negative knowledge.
    for key, view in views.items():
        if view.object.ref.kind == "failed_attempt" and target.object_id in view.object.record.get("artifacts", []):
            candidates.add(key)
            priorities[key] = 50

    def shell(key):
        v = views[key]
        entry = v.object
        historical = entry.research_state in {"REVISED", "REFUTED", "SUPERSEDED", "HISTORICAL"} or entry.authority == "REJECTED/HISTORICAL"
        label = "STALE" if v.freshness != "CURRENT" else "FAILED" if entry.ref.kind == "failed_attempt" or entry.research_state == "INVALIDATED" else "HISTORICAL" if historical else "TRUSTED" if v.authority == "HUMAN_ACCEPTED" and v.verification in {"PASSED", "CHECKED", "VERIFIER_PASSED"} else "PROVISIONAL"
        return PacketItem(ref=entry.ref, version=entry.version, label=label, tier="MUST" if key in required else "MAY" if historical or entry.ref.kind in {"episode", "source"} else "SHOULD", authority=v.authority, verification=v.verification, review=entry.review, freshness=v.freshness, research_state=entry.research_state, usable_working_premise=v.usable_working_premise, trusted_formal_premise=v.trusted_formal_premise, provenance=entry.provenance, dependencies=[d.model_dump(mode="json") for d in entry.dependencies], artifact_refs=entry.artifact_refs)

    ordered = sorted(candidates, key=lambda k: (k != target.qualified_id, k not in required, -priorities.get(k, 0), -scores.get(k, 0), k))
    packet = ContextPacket(target=target, source_version=version, purpose=purpose, required_record_ids=sorted(required | missing), required_omitted_ids=sorted(missing), token_budget=token_budget)
    for key in ordered:
        if key not in required:
            continue
        item = shell(key)
        packet.items.append(item)
        if packet_tokens(packet) > token_budget:
            packet.items.pop()
            packet.required_omitted_ids.append(key)
    if packet_tokens(packet) > token_budget:
        raise ResearchError("Budget cannot fit mandatory identity/omission metadata; increase budget.")
    for key in ordered:
        v = views[key]
        if not include_provisional and v.authority == "PROVISIONAL":
            continue
        item = next((i for i in packet.items if i.ref == v.object.ref), None)
        if key in required and item is None:
            continue
        if item is None:
            item = shell(key)
            packet.items.append(item)
            if packet_tokens(packet) > token_budget:
                packet.items.pop()
                continue
        text = v.object.full_content
        # Raw episodes are navigation excerpts, never a wholesale harness transcript.
        if item.ref.kind in {"episode", "source"}:
            text = _excerpt(text, 1200, query)
        item.content, item.full_text, item.truncated = text, text == v.object.full_content, text != v.object.full_content
        if packet_tokens(packet) > token_budget:
            item.full_text, item.truncated = False, True
            item.usable_working_premise = False
            item.trusted_formal_premise = False
            low, high = 0, len(text)
            while low < high:
                middle = (low + high + 1) // 2
                item.content = _excerpt(text, middle, query)
                if packet_tokens(packet) <= token_budget:
                    low = middle
                else:
                    high = middle - 1
            item.content = _excerpt(text, low, query)
        if not item.full_text:
            item.usable_working_premise = False
            item.trusted_formal_premise = False
    packet.required_context_truncated = bool(packet.required_omitted_ids) or any(i.tier == "MUST" and i.truncated for i in packet.items)
    packet.complete = not packet.required_context_truncated
    # Final false/true metadata can cost a token more; trim text, never the labels.
    while packet_tokens(packet) > token_budget and any(i.content for i in packet.items):
        item = next(i for i in reversed(packet.items) if i.content)
        item.content = item.content[:-max(1, (packet.token_estimate - token_budget) * 3)]
        item.full_text, item.truncated = False, True
        item.usable_working_premise = item.trusted_formal_premise = False
        if item.tier == "MUST":
            packet.required_context_truncated, packet.complete = True, False
    if packet_tokens(packet) > token_budget:
        raise ResearchError("Budget cannot fit mandatory metadata.")
    if ledger.source_version(target.problem_id) != version:
        raise ResearchError("Research state changed during packet export; retry.")
    return packet
