"""Derived currentness; never rewrite verification or human acceptance history."""

from enum import StrEnum

from pydantic import BaseModel, Field

from math_research.core.refs import ObjectRef
from math_research.ledger.manifest import ManifestEntry
from math_research.verification.models import VersionPin


class Freshness(StrEnum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class FreshnessResult(BaseModel):
    freshness: Freshness
    reasons: list[str] = Field(default_factory=list)


class FreshnessResolver:
    def __init__(self, entries: list[ManifestEntry], *, max_nodes: int = 256):
        self.entries = {e.qualified_id: e for e in entries}
        self.max_nodes = max_nodes

    def resolve(self, ref: ObjectRef) -> FreshnessResult:
        visited, visiting, reasons = set(), set(), []
        stale = False

        def walk(current):
            nonlocal stale
            key = current.qualified_id
            if key in visiting:
                reasons.append(f"Cyclic dependency: {key}")
                return
            if key in visited:
                return
            if len(visited) >= self.max_nodes:
                reasons.append("Dependency traversal limit reached")
                return
            visited.add(key)
            entry = self.entries.get(key)
            if entry is None:
                reasons.append(f"Missing dependency: {key}")
                return
            if any(a["sha256"] is None for a in entry.artifact_refs):
                stale = True
                reasons.append(f"Missing artifact: {key}")
            if any("SHA-256 mismatch" in w for w in entry.warnings):
                stale = True
                reasons.append(f"Pinned source changed: {key}")
            visiting.add(key)
            for edge in entry.dependencies:
                target = self.entries.get(edge.target.qualified_id)
                if edge.expected_version and (target is None or target.version != edge.expected_version):
                    stale = True
                    reasons.append(f"Version changed: {edge.target.qualified_id} ({edge.role.value})")
                walk(edge.target)
            visiting.remove(key)

        walk(ref)
        return FreshnessResult(freshness=Freshness.STALE if stale else Freshness.UNKNOWN if reasons else Freshness.CURRENT, reasons=list(dict.fromkeys(reasons)))

    def pins(self, ref: ObjectRef) -> tuple[VersionPin, ...]:
        """Pin the entire current closure; reject incomplete or cyclic evidence."""
        from math_research.core.errors import ResearchError

        result = self.resolve(ref)
        if result.freshness != Freshness.CURRENT:
            raise ResearchError("Cannot pin non-current closure: " + "; ".join(result.reasons))
        pending, seen, pins = [ref], set(), []
        while pending:
            current = pending.pop()
            if current.qualified_id in seen:
                continue
            seen.add(current.qualified_id)
            entry = self.entries[current.qualified_id]
            pins.append(VersionPin(ref=current, version=entry.version))
            pending.extend(e.target for e in entry.dependencies)
        return tuple(sorted(pins, key=lambda p: p.ref.qualified_id))

    def check_pins(self, pins: tuple[VersionPin, ...]) -> FreshnessResult:
        reasons = []
        unknown = False
        for pin in pins:
            entry = self.entries.get(pin.ref.qualified_id)
            if entry is None or entry.version != pin.version:
                reasons.append(f"Recorded version changed/missing: {pin.ref.qualified_id}")
            state = self.resolve(pin.ref)
            reasons.extend(state.reasons)
            unknown |= state.freshness == Freshness.UNKNOWN
        return FreshnessResult(freshness=Freshness.STALE if reasons and not unknown else Freshness.UNKNOWN if unknown else Freshness.CURRENT, reasons=list(dict.fromkeys(reasons)))
