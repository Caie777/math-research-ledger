import pytest
from test_ledger import episode, snapshot

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.manifest import Ledger
from math_research.retrieval.context import estimate_tokens
from math_research.services.ingest import ingest_episode
from math_research.services.research import add_definition, link_dependency, update_definition
from math_research.services.retrieval import export_context_packet, search_research


def test_entire_json_budget_and_required_truncation_are_explicit(research):
    state, ref = research
    d = add_definition(state, ref.problem_id, "D", "long mathematical definition " * 3000)
    link_dependency(
        state,
        ref,
        ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=d.id),
        DependencyRole.DEFINITION,
    )
    before = snapshot(state)
    packet = export_context_packet(state, ref, token_budget=1800)
    assert estimate_tokens(packet.model_dump_json()) <= 1800
    assert packet.required_context_truncated and not packet.complete
    assert any(i.truncated for i in packet.items if i.tier == "MUST") or packet.required_omitted_ids
    assert snapshot(state) == before


def test_provisional_stale_and_failed_routes_have_labels(research):
    state, ref = research
    ingest_episode(
        state, ref.problem_id, "test.md", episode(ref), provenance="external synthetic harness"
    )
    d = add_definition(state, ref.problem_id, "D", "initial")
    link_dependency(
        state,
        ref,
        ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=d.id),
        DependencyRole.DEFINITION,
    )
    update_definition(state, ref.problem_id, d.model_copy(update={"definition": "changed"}))
    packet = export_context_packet(state, ref, query="failed synthetic route", token_budget=16000)
    assert next(i for i in packet.items if i.ref == ref).label == "STALE"
    assert any(i.label == "FAILED" for i in packet.items)
    assert any(i.label == "PROVISIONAL" for i in packet.items)
    assert search_research(state, "failed synthetic route")["hits"]


def test_source_coherence_change_detected(research, monkeypatch):
    state, ref = research
    original = Ledger.source_version
    calls = 0

    def changing(self, problem_id=None):
        nonlocal calls
        calls += 1
        value = original(self, problem_id)
        return value if calls == 1 else "changed"

    monkeypatch.setattr(Ledger, "source_version", changing)
    with pytest.raises(ResearchError, match="changed"):
        export_context_packet(state, ref)


def test_relative_workspace_packet_is_read_only(research, monkeypatch):
    from pathlib import Path

    state, ref = research
    monkeypatch.chdir(state.parent)
    before = snapshot(state)
    assert export_context_packet(Path(".math-research"), ref).target == ref
    assert snapshot(state) == before
