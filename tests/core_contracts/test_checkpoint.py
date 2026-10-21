import hashlib

import pytest

from math_research.core.errors import ResearchError
from math_research.ledger.archive import source_path
from math_research.ledger.episodes import list_candidates, list_episodes
from math_research.services.ingest import ingest_episode


@pytest.mark.parametrize("numbered", [False, True])
def test_next_directions_cannot_become_candidates_delta_or_dependencies(research, numbered):
    state, ref = research
    heading = (
        "## RESULT-1\n\n**Statement**\nactual fixture change"
        if numbered
        else "## Claim: actual\n\nactual fixture change"
    )
    planning = (
        "## RESULT-2\n\n**Statement**\nplanned only"
        if numbered
        else "## Claim: planned\n\nplanned only"
    )
    raw = (
        "# Confirmed Research Increment\n\n"
        + heading
        + "\n\n# Next Research Directions\n\n"
        + planning
        + "\n- RESULT-1 uses RESULT-2\n"
    ).encode()
    result = ingest_episode(state, ref.problem_id, "checkpoint.md", raw, provenance="synthetic")
    episode = list_episodes(state)[0]
    candidates = list_candidates(state, ref.problem_id)
    assert len(candidates) == 1
    assert "planned only" not in candidates[0].body
    assert len(episode.state_delta) == 1
    assert episode.state_delta[0].action == "Added"
    assert "planned only" not in episode.state_delta[0].statement
    assert episode.state_delta[0].source_sha256 == hashlib.sha256(raw).hexdigest()
    assert "planned only" in episode.next_research_directions
    assert not episode.explicit_dependencies
    assert source_path(state, episode.archive_path).read_bytes() == raw
    assert result["canonical_records_created"] == 0


def test_explicit_changes_are_source_assertions_and_cannot_grant_authority(research):
    state, ref = research
    raw = (
        b"---\nstate_delta:\n- action: Invalidated\n  reference: CLAIM-0001\n"
        b"  statement: Synthetic reported invalidation only\n---\n"
        b"# Next Research Directions\n\nInspect later.\n"
    )
    ingest_episode(state, ref.problem_id, "delta.md", raw, provenance="synthetic")
    from math_research.services.research import get_object

    assert get_object(state, ref).object.research_state == "CURRENT"
    assert list_episodes(state)[0].state_delta[0].action == "Invalidated"
    with pytest.raises(ResearchError, match="only action"):
        ingest_episode(
            state,
            ref.problem_id,
            "invalid.md",
            raw.replace(b"- action:", b"- authority: ACCEPTED\n  action:"),
            provenance="synthetic",
        )


def test_planning_only_checkpoint_retained_without_candidates(research):
    state, ref = research
    raw = b"# Next Research Directions\n\n## Claim: planned, not achieved\n\nTry later.\n"
    result = ingest_episode(state, ref.problem_id, "planning.md", raw, provenance="synthetic")
    assert not result["candidates"]
    assert not list_episodes(state)[0].state_delta
    assert "Try later" in list_episodes(state)[0].next_research_directions


def test_failed_publication_rolls_back_both_indexes_and_retains_raw_source(research, monkeypatch):
    state, ref = research
    from math_research.ledger.manifest import Ledger

    before = Ledger(state).source_version()
    from math_research.ledger.episodes import extract_candidates

    def fail(*args):
        extract_candidates(*args)
        raise OSError("synthetic staged-index failure")

    monkeypatch.setattr("math_research.services.ingest.extract_candidates", fail)
    with pytest.raises(OSError, match="staged-index"):
        ingest_episode(
            state,
            ref.problem_id,
            "rollback.md",
            b"## Claim: synthetic\n\nRetain raw.\n",
            provenance="synthetic",
        )
    assert not list_episodes(state)
    assert not list_candidates(state, ref.problem_id)
    assert Ledger(state).source_version() == before
    assert len(list((state / "research_archive").rglob("*.md"))) == 1
    assert not (state / ".checkpoint-pending.json").exists()


def test_crashed_checkpoint_fails_closed_and_recovery_is_human_only(research):
    import json

    from math_research.ledger.checkpoint import JOURNAL, recover_checkpoint
    from math_research.ledger.records.write_boundary import automated_scope

    state, ref = research
    journal = state / JOURNAL
    journal.write_text(json.dumps({"files": {"research_archive/index.jsonl": None}}), "utf-8")
    with pytest.raises(ResearchError, match="recover"):
        list_episodes(state)
    with automated_scope(), pytest.raises(ResearchError):
        recover_checkpoint(state)
    assert journal.exists()
    assert recover_checkpoint(state)["recovered"]
    assert not list_episodes(state)


@pytest.mark.parametrize("action", ["Added", "Revised", "Invalidated", "Refuted", "Still Open"])
def test_all_explicit_delta_actions_retain_source_scope(research, action):
    import yaml

    state, ref = research
    raw = (
        "---\n"
        + yaml.safe_dump(
            {
                "state_delta": [
                    {
                        "action": action,
                        "reference": ref.qualified_id,
                        "statement": "Synthetic source assertion only",
                    }
                ]
            }
        )
        + "---\n"
    ).encode()
    ingest_episode(state, ref.problem_id, "action.md", raw, provenance="synthetic")
    delta = list_episodes(state)[0].state_delta[0]
    assert delta.action == action and delta.reference == ref.qualified_id
    assert delta.source_sha256 == hashlib.sha256(raw).hexdigest()


def test_explicit_delta_cannot_promote_planning_local_objects(research):
    state, ref = research
    raw = (
        b"---\nstate_delta:\n- action: Added\n  reference: RESULT-2\n"
        b"  statement: planned\n---\n# Next Research Directions\n\n"
        b"## RESULT-2\n\n**Statement**\nplanned\n"
    )
    with pytest.raises(ResearchError, match="advisory"):
        ingest_episode(state, ref.problem_id, "planning.md", raw, provenance="synthetic")
