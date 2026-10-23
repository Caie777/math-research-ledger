"""Frozen synthetic gold, actual adapter calls, and three finite replay strategies."""

import json

import pytest
from benchmarks.continuity.evaluate import evaluate_budget, freeze_hashes, load_tasks


@pytest.mark.parametrize("budget", [2000, 8000, 16000])
def test_frozen_continuity_benchmark(tmp_path, budget):
    report = evaluate_budget(tmp_path / "replay", budget)
    (tmp_path / "benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), "utf-8"
    )
    assert report["tasks"] == 18
    assert report["freeze_sha256"] == freeze_hashes()
    metrics = {row["metrics"]["strategy"]: row["metrics"] for row in report["results"]}
    for row in report["results"]:
        m = row["metrics"]
        assert m["selected_problem_correct"] and m["main_target_correct"]
        assert m["latest_checkpoint_correct"]
        assert m["must_ref_recall"] == 1
        assert m["max_packet_tokens"] <= budget
        assert m["cross_scope_leaks"] == 0
        assert m["tool_calls"] == len(row["replay"]["calls"])
        assert all(
            c["result"].get("required_set_complete") == c["result"].get("complete")
            for c in row["replay"]["calls"]
            if c["tool"] == "research_context_packet"
        )
        assert m["calls_per_task"]["checkpoint"] == 2
        assert row["replay"]["observations"][-1]["checkpoint"]["canonical_records_created"] == 0
    for strategy in ("A", "C"):
        assert metrics[strategy]["unsafe_positive_premises"] == 0
        assert (
            metrics[strategy]["safety_decisions_with_evidence"]
            == metrics[strategy]["safety_decisions_total"]
        )
        assert metrics[strategy]["no_match_correct"] == 1
    drift_row = next(row for row in report["results"] if row["metrics"]["strategy"] == "C")
    observed = next(
        row for row in drift_row["replay"]["observations"] if row["id"] == "accepted-drift"
    )
    assert (
        observed["memory"][drift_row["replay"]["roles"]["accepted_drift"]]["freshness"] == "STALE"
    )
    # This tests execution of the proposed policy, not a hardcoded superiority claim.
    assert metrics["C"]["local_reasoning_calls"] == metrics["B"]["local_reasoning_calls"] == 0
    assert metrics["A"]["local_reasoning_calls"] > 0


def test_gold_and_tasks_are_frozen_separately_from_production():
    from pathlib import Path

    tasks = load_tasks()
    assert freeze_hashes() == {
        "tasks.json": "49ecc8711e0b1d60697a4f8392398412971e8d54923de2d6338f4ca9804cb8b9",
        "gold.json": "a35eeaa335f21fb23d00b47866cd6185fa3b19e355b21121ec9d4e1421e8fd60",
    }
    assert len({t["id"] for t in tasks}) == 18
    assert all("gold" not in t and "expected" not in t for t in tasks)
    for path in (Path(__file__).resolve().parents[2] / "src/math_research").rglob("*.py"):
        assert "benchmarks.continuity" not in path.read_text("utf-8")
