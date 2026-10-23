"""Publication navigation, exact identity, freshness axes and bounded read guidance."""

import json
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.episodes import list_candidates
from math_research.ledger.identity import working_ref
from math_research.ledger.manifest import Ledger
from math_research.ledger.projection import list_objects
from math_research.ledger.publication import publication_navigation
from math_research.ledger.records import store
from math_research.ledger.records.models import ClaimRecord
from math_research.mcp.adapter import DESCRIPTIONS, SCHEMAS, LedgerAdapter
from math_research.retrieval.memory_policy import memory_access
from math_research.services.ingest import ingest_episode, review_proposal
from math_research.services.research import add_claim, create_problem, link_dependency, status


def publication(state, pid):
    value = ingest_episode(
        state,
        pid,
        "checkpoint.md",
        b"# Confirmed Research Increment\n\n"
        b"## RESULT-1\n\n**Statement**\nSynthetic orion increment.\n\n"
        b"## PROOF-1\n\n**Target**\nRESULT-1\n\n**Proof**\nSynthetic orion argument.\n\n"
        b"## EVIDENCE-1\n\n**Statement**\nSynthetic orion observation.\n",
        provenance="synthetic navigation regression",
    )
    eid = value["episode"]["episode_id"]
    return eid, list_candidates(state, pid, eid)


def episode_ref(pid, eid):
    return ObjectRef(problem_id=pid, kind="episode", object_id=eid)


def test_checkpoint_and_exact_episode_expose_persisted_publication(research):
    state, target = research
    eid, candidates = publication(state, target.problem_id)
    latest = status(state, target.problem_id)["continuation"]["latest_meaningful_checkpoint"]
    exact = LedgerAdapter(state).call(
        "research_get_object", {"ref": episode_ref(target.problem_id, eid).qualified_id}
    )
    assert latest["produced_objects"] == exact["produced_objects"]
    assert latest["mapping_status"] == "AVAILABLE"
    assert {r["local_id"] for r in exact["produced_objects"]} == {
        "RESULT-1",
        "PROOF-1",
        "EVIDENCE-1",
    }
    assert all(r["authority"] == "PROVISIONAL" and r["version"] for r in latest["produced_objects"])
    assert all(r["kind"] != "relation" for r in latest["produced_objects"])
    assert exact["relation_total"] == sum(c.kind == "relation" for c in candidates)
    assert not exact["relation_proposals_are_mathematical_objects"]


@pytest.mark.parametrize("decision", ["accept", "reject", "defer"])
def test_publication_retains_provenance_and_current_review_identity(research, decision):
    state, target = research
    eid, candidates = publication(state, target.problem_id)
    original = next(c for c in candidates if c.local_id == "RESULT-1" and c.kind == "claim")
    review = review_proposal(state, target.problem_id, original.candidate_id, decision)
    nav = publication_navigation(state, target.problem_id, eid, list_objects(state))
    row = next(r for r in nav["produced_objects"] if r["candidate_id"] == original.candidate_id)
    expected = (
        target.model_copy(update={"object_id": review.mapped_id})
        if decision == "accept"
        else working_ref(original)
    )
    assert row["qualified_ref"] == expected.qualified_id
    assert row["publication_ref"] == working_ref(original).qualified_id
    assert row["review_decision"] == decision
    assert (
        row["authority"]
        == {"accept": "CANONICAL", "reject": "REJECTED/HISTORICAL", "defer": "PROVISIONAL"}[
            decision
        ]
    )
    assert (
        Ledger(state).resolve("RESULT-1", problem_id=target.problem_id, episode_id=eid) == expected
    )
    if decision == "reject":
        assert row["premise_eligibility"] == "BLOCKED"


def test_publication_without_persisted_rows_is_explicitly_unavailable(research):
    state, target = research
    value = ingest_episode(
        state,
        target.problem_id,
        "legacy.md",
        b"Unstructured historical RESULT-1 text.",
        provenance="synthetic",
        archive_only=True,
    )
    nav = publication_navigation(
        state, target.problem_id, value["episode"]["episode_id"], list_objects(state)
    )
    assert nav["mapping_status"] == "UNAVAILABLE_NO_PERSISTED_MAPPING"
    assert nav["produced_objects"] == []


def test_same_local_id_in_another_episode_does_not_change_mapping(research):
    state, target = research
    eid, _ = publication(state, target.problem_id)
    before = publication_navigation(state, target.problem_id, eid, list_objects(state))
    ingest_episode(
        state,
        target.problem_id,
        "other.md",
        b"# Confirmed Research Increment\n\n## RESULT-1\n\n**Statement**\nAnother result.\n",
        provenance="synthetic",
    )
    after = publication_navigation(state, target.problem_id, eid, list_objects(state))
    assert before == after


@pytest.mark.parametrize("form", ["episode", "candidate", "qualified", "stable", "canonical"])
def test_identifier_search_resolves_exact_before_lexical(research, form):
    state, target = research
    eid, candidates = publication(state, target.problem_id)
    result = next(c for c in candidates if c.kind == "claim")
    query = {
        "episode": eid,
        "candidate": result.candidate_id,
        "qualified": working_ref(result).qualified_id,
        "stable": working_ref(result).object_id,
        "canonical": target.object_id,
    }[form]
    expected = (
        episode_ref(target.problem_id, eid)
        if form == "episode"
        else target
        if form == "canonical"
        else working_ref(result)
    )
    adapter = LedgerAdapter(state)
    with patch(
        "math_research.services.retrieval.search_documents",
        side_effect=AssertionError("exact lookup must bypass lexical"),
    ):
        found = adapter.call("research_search", {"problem_id": target.problem_id, "query": query})
    assert found["retrieval_mode"] == "EXACT_IDENTITY"
    assert len(found["hits"]) == 1
    assert ObjectRef.model_validate(found["hits"][0]["ref"]) == expected
    assert found["hits"][0]["reasons"] == ["EXACT_IDENTITY"]


def test_candidate_search_follows_review_to_canonical(research):
    state, target = research
    _, rows = publication(state, target.problem_id)
    candidate = next(c for c in rows if c.kind == "claim")
    decision = review_proposal(state, target.problem_id, candidate.candidate_id, "accept")
    hit = LedgerAdapter(state).call(
        "research_search", {"query": candidate.candidate_id, "problem_id": target.problem_id}
    )["hits"][0]
    assert hit["ref"]["object_id"] == decision.mapped_id
    assert hit["authority"] == "CANONICAL"


def test_missing_identifier_falls_back_and_ambiguous_id_never_guesses(research):
    state, target = research
    add_claim(
        state, target.problem_id, "A reference to EPISODE-ABCDEF00 without a persisted Episode."
    )
    adapter = LedgerAdapter(state)
    missed = adapter.call(
        "research_search", {"query": "EPISODE-ABCDEF00", "problem_id": target.problem_id}
    )
    assert missed["retrieval_mode"] == "LEXICAL_RECALL" and missed["hits"]
    other = create_problem(state, "Other", "Other scope")
    store.append_claim(
        state,
        ClaimRecord(
            id=target.object_id,
            problem_id=other.id,
            type="CLAIM",
            statement="Other synthetic claim",
        ),
    )
    ambiguous = adapter.call("research_search", {"query": target.object_id})
    assert ambiguous["retrieval_mode"] == "LEXICAL_RECALL"
    scoped = adapter.call(
        "research_search",
        {"query": f"{other.id}:claim:{target.object_id}", "problem_id": target.problem_id},
    )
    assert scoped["retrieval_mode"] == "LEXICAL_RECALL"
    assert all(h["ref"]["problem_id"] == target.problem_id for h in scoped["hits"])


@pytest.mark.parametrize("mode", ["unknown", "stale", "refuted"])
def test_state_axes_agree_across_read_surfaces(research, mode):
    state, target = research
    upstream = add_claim(state, target.problem_id, "Upstream synthetic statement")
    ref = target.model_copy(update={"object_id": upstream.id})
    if mode == "unknown":
        claims = store.list_claims(state, target.problem_id)
        store.rewrite_claims(
            state,
            target.problem_id,
            [
                c.model_copy(update={"depends_on": [upstream.id]})
                if c.id == target.object_id
                else c
                for c in claims
            ],
        )
    elif mode == "stale":
        link_dependency(state, target, ref, DependencyRole.LOGICAL_PREMISE)
        claims = store.list_claims(state, target.problem_id)
        store.rewrite_claims(
            state,
            target.problem_id,
            [
                c.model_copy(update={"statement": "Changed upstream"}) if c.id == upstream.id else c
                for c in claims
            ],
        )
    else:
        claims = store.list_claims(state, target.problem_id)
        store.rewrite_claims(
            state,
            target.problem_id,
            [
                c.model_copy(update={"status": "refuted"}) if c.id == target.object_id else c
                for c in claims
            ],
        )
    adapter = LedgerAdapter(state)
    exact = adapter.call("research_get_object", {"ref": target.qualified_id})
    search = adapter.call("research_search", {"query": target.qualified_id})["hits"][0]
    packet = adapter.call(
        "research_context_packet", {"ref": target.qualified_id, "token_budget": 8000}
    )
    item = next(r for r in packet["items"] if ObjectRef.model_validate(r["ref"]) == target)
    for field in (
        "freshness",
        "research_state",
        "authority",
        "premise_eligibility",
        "usable_working_premise",
    ):
        assert exact[field] == search[field] == item[field]
    assert exact["premise_eligibility"] == "BLOCKED"
    fresh = {"unknown": "UNKNOWN", "stale": "STALE", "refuted": "CURRENT"}[mode]
    assert exact["freshness"] == fresh
    assert item["label"] == {"unknown": "UNKNOWN", "stale": "STALE", "refuted": "HISTORICAL"}[mode]
    report = adapter.call("research_stale_report", {"problem_id": target.problem_id})
    risk = next(
        (r for r in report["objects"] if ObjectRef.model_validate(r["ref"]) == target), None
    )
    assert risk["freshness"] == fresh if mode != "refuted" else risk is None
    assert "unknown" in report["object_scope"]
    orientation = adapter.call("research_status", {"problem_id": target.problem_id})
    summary = next(r for r in orientation["object_summaries"] if r["ref"] == target.qualified_id)
    assert summary["freshness"] == fresh


def test_read_pagination_is_bounded_and_navigation_offsets_are_separate(research):
    state, target = research
    claims = store.list_claims(state, target.problem_id)
    store.rewrite_claims(
        state, target.problem_id, [c.model_copy(update={"statement": "x" * 9500}) for c in claims]
    )
    adapter = LedgerAdapter(state)
    page = adapter.call("research_get_object", {"ref": target.qualified_id})
    assert len(page["content"]) == 4000 and page["max_window"] == 8000
    assert page["next_offset"] == 4000 and page["remaining"] == page["total_characters"] - 4000
    tail = adapter.call(
        "research_get_object",
        {"ref": target.qualified_id, "offset": page["next_offset"], "length": 8000},
    )
    assert tail["next_offset"] is None and tail["remaining"] == 0
    beyond = adapter.call("research_get_object", {"ref": target.qualified_id, "offset": 1000000})
    assert beyond["content"] == "" and beyond["next_offset"] is None and beyond["remaining"] == 0
    eid, _ = publication(state, target.problem_id)
    nav = publication_navigation(state, target.problem_id, eid, list_objects(state), limit=1)
    second = publication_navigation(
        state,
        target.problem_id,
        eid,
        list_objects(state),
        offset=nav["next_produced_offset"],
        limit=1,
    )
    assert nav["produced_objects"][0] != second["produced_objects"][0]


def test_schema_limits_and_prose_are_actionable_without_expanding_envelope():
    read = SCHEMAS["research_get_object"].model_json_schema()["properties"]
    packet = SCHEMAS["research_context_packet"].model_json_schema()["properties"]
    assert read["length"]["maximum"] == 8000 and read["length"]["default"] == 4000
    assert packet["token_budget"]["maximum"] == 16000 and packet["token_budget"]["default"] == 8000
    assert "8000" in DESCRIPTIONS["research_get_object"]
    assert "16000" in DESCRIPTIONS["research_context_packet"]
    with pytest.raises(ValidationError):
        SCHEMAS["research_get_object"](ref="P:claim:X", length=8001)
    with pytest.raises(ValidationError):
        SCHEMAS["research_context_packet"](ref="P:claim:X", token_budget=16001)


def test_local_reasoning_remains_zero_calls_and_mapping_contains_no_body(research):
    state, target = research
    eid, _ = publication(state, target.problem_id)
    nav = publication_navigation(state, target.problem_id, eid, list_objects(state))
    assert "Synthetic orion argument" not in json.dumps(nav)
    assert all(memory_access("local_reasoning")["suggested_tools"] == [] for _ in range(20))


def test_synthetic_equivalent_replay_uses_direct_mapping_and_no_error_retries(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    output = tmp_path / "replay"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "scripts/replay_continuation_navigation.py",
            "--output",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads((output / "replay.json").read_text("utf-8"))
    assert report["produced_refs_found"] == 3 and report["direct_mapping"]
    assert report["exact_episode_first"] and report["unknown_rendered_stale"] == 0
    assert report["tool_errors"] == 0 and report["local_reasoning_tool_calls"] == 0
    assert "navigation_workaround" not in report["calls_by_category"]
    assert "state_ambiguity_check" not in report["calls_by_category"]
