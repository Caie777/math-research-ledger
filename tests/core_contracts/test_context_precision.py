"""Checkpoint-local precision, explicit evidence needs and unchanged search recall."""

import pytest
from benchmarks.precision.corpus import build
from benchmarks.precision.evaluate import evaluate

from math_research.core.refs import ObjectRef
from math_research.mcp.adapter import LedgerAdapter
from math_research.retrieval.memory_policy import memory_access
from math_research.services.ingest import ingest_episode
from math_research.services.retrieval import export_context_packet, search_research


@pytest.fixture(scope="module")
def precision(tmp_path_factory):
    return build(tmp_path_factory.mktemp("precision") / "workspace")


def packet(corpus, budget=16000):
    return export_context_packet(corpus["state"], corpus["roles"]["gap"], token_budget=budget)


@pytest.mark.parametrize("budget", [2000, 8000, 16000])
def test_precision_budget_required_recall_and_no_unrelated_history(precision, budget):
    result = evaluate(precision, budget)
    assert result["required_recall"] == 1
    assert result["required_omissions"] == []
    assert result["irrelevant_objects"] == result["irrelevant_bytes"] == 0
    assert result["duplicate_identities_in_packet"] == result["unsafe_premises"] == 0
    assert result["proof_body_bytes_in_packet"] == 0
    assert result["packet_tokens"] <= budget
    assert result["local_reasoning_calls"] == 0
    if budget >= 8000:
        assert result["should_recall"] == 1


def test_local_checkpoint_and_three_produced_objects_selected(precision):
    p = packet(precision)
    rows = {i.ref: i for i in p.items}
    for role in ("result", "proof", "evidence"):
        item = rows[precision["roles"][role]]
        assert item.tier == "SHOULD"
        assert item.selection_reason == "latest_checkpoint_produced_object"
        assert not item.full_text and not item.usable_working_premise
    checkpoint = rows[precision["roles"]["checkpoint"]]
    assert "Still Open" in checkpoint.content
    assert not checkpoint.usable_working_premise
    assert "LARGE_PROOF_MARKER" not in checkpoint.content


@pytest.mark.parametrize("role", ["main", "gap", "premise"])
def test_gap_and_deterministic_required_closure(precision, role):
    p = packet(precision)
    item = next(i for i in p.items if i.ref == precision["roles"][role])
    assert item.tier == "MUST" and item.full_text
    assert item.selection_reason == "required_closure"


@pytest.mark.parametrize("role", ["failed", "counterexample"])
def test_direct_negative_route_has_should_navigation(precision, role):
    item = next(i for i in packet(precision).items if i.ref == precision["roles"][role])
    assert item.tier == "SHOULD" and item.selection_reason == "direct_target_record"
    assert item.navigation["source_characters"] > 0


def test_budget_need_not_be_filled_and_old_advisory_not_expanded(precision):
    p = packet(precision)
    assert p.token_estimate < 12000
    assert precision["roles"]["old_advisory"] not in {i.ref for i in p.items}
    assert precision["roles"]["unrelated"] not in {i.ref for i in p.items}


def test_large_proof_is_metadata_not_duplicate_body_and_exact_get_still_works(precision):
    ref = precision["roles"]["proof"]
    item = next(i for i in packet(precision).items if i.ref == ref)
    assert not item.content
    assert item.navigation["source_characters"] > 8000
    assert (
        "exact" in item.navigation["exact_read_reason"].lower()
        or "original" in item.navigation["exact_read_reason"].lower()
    )
    page = LedgerAdapter(precision["state"]).call("research_get_object", {"ref": ref.qualified_id})
    assert "LARGE_PROOF_MARKER" in page["content"] and page["next_offset"] is not None


def test_ordinary_search_still_recalls_unrelated_route(precision):
    result = search_research(
        precision["state"], "primitive-divisor", problem_id=precision["problem_id"]
    )
    assert precision["roles"]["unrelated"] in {
        ObjectRef.model_validate(i["ref"]) for i in result["hits"]
    }


def test_no_per_turn_retrieval_added():
    for _ in range(20):
        assert memory_access("local_reasoning")["suggested_tools"] == []


def test_newer_unrelated_publication_does_not_replace_local_checkpoint(research, tmp_path):
    corpus = build(tmp_path / "local")
    ingest_episode(
        corpus["state"],
        corpus["problem_id"],
        "unrelated-newer.md",
        b"## Claim: New unrelated history\n\nSynthetic primitive-divisor three atom route.\n",
        provenance="synthetic",
    )
    selected = packet(corpus)
    assert corpus["roles"]["checkpoint"] in {i.ref for i in selected.items}
    assert all("New unrelated history" not in i.content for i in selected.items)
