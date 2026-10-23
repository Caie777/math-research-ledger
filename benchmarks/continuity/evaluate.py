"""Measured deterministic tool replay, not an evaluation of an LLM's reasoning."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from benchmarks.continuity.corpus import build_corpus, clone_corpus, drift
from math_research.core.errors import IntegrityError, ResearchError
from math_research.core.refs import ObjectRef
from math_research.mcp.adapter import LedgerAdapter
from math_research.retrieval.memory_policy import memory_access

HERE = Path(__file__).parent


def load_tasks():
    return json.loads((HERE / "tasks.json").read_text("utf-8"))["tasks"]


def freeze_hashes():
    return {
        name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
        for name in ("tasks.json", "gold.json")
    }


class CountedAdapter:
    def __init__(self, state):
        self.adapter = LedgerAdapter(state)
        self.calls = []
        self.memory = {}

    def call(self, name, arguments):
        try:
            result = self.adapter.call(name, arguments)
        except ResearchError as exc:
            result = {
                "error": {
                    "code": "INTEGRITY_ERROR"
                    if isinstance(exc, IntegrityError)
                    else "RESEARCH_ERROR"
                }
            }
            # Exact failure supersedes any old cached positive-premise label.
            if "ref" in arguments:
                self.memory[arguments["ref"]] = {
                    "ref": arguments["ref"],
                    "usable_working_premise": False,
                    "read_error": result["error"],
                }
        self.calls.append(
            {
                "tool": name,
                "arguments": arguments,
                "bytes": len(json.dumps(result, ensure_ascii=False).encode()),
                "result": result,
            }
        )
        if name == "research_get_object" and "error" not in result:
            self.memory[result["ref"]] = result
        for row in result.get("items", []) + result.get("hits", []):
            key = ObjectRef.model_validate(row["ref"]).qualified_id
            self.memory[key] = row
        return result


def replay(root: Path, budget: int, strategy: str, tasks: list[dict], *, seed=None) -> dict:
    """Only task inputs enter this function; gold is loaded after all tool observations."""
    corpus = clone_corpus(seed, root) if seed else build_corpus(root)
    roles, pid = corpus["roles"], corpus["problem_id"]
    adapter = CountedAdapter(corpus["state"])
    status = adapter.call("research_status", {"problem_id": pid, "limit": 1})
    context = adapter.call(
        "research_context_packet", {"ref": roles["main"].qualified_id, "token_budget": budget}
    )
    observations = []
    for task in tasks:
        if task.get("mutate_before") == "definition_drift":
            drift(corpus)  # External fixture event, not a tool call or model action.
        before = len(adapter.calls)
        guidance = memory_access(task["event"])
        hits = None
        if task["event"] == "checkpoint":
            arguments = {
                "problem_id": pid,
                "markdown": "## Claim: benchmark terminal checkpoint\n\n"
                "A meaningful synthetic increment.\n",
                "provenance": "synthetic continuity evaluation",
            }
            preview = adapter.call("research_ingest_episode", {**arguments, "dry_run": True})
            checkpoint = (
                adapter.call("research_ingest_episode", arguments)
                if preview.get("can_publish")
                else preview
            )
        else:
            checkpoint = None
            query_now = strategy == "A" or strategy == "C" and guidance["action"] == "RETRIEVE"
            if query_now:
                found = adapter.call(
                    "research_search", {"problem_id": pid, "query": task["query"], "limit": 10}
                )
                hits = found.get("hits", [])
            if strategy == "A":
                adapter.call(
                    "research_context_packet",
                    {
                        "ref": roles["main"].qualified_id,
                        "query": task["query"],
                        "token_budget": budget,
                    },
                )
            if task.get("read_role") and (strategy == "A" or strategy == "C"):
                adapter.call("research_get_object", {"ref": roles[task["read_role"]].qualified_id})
        observations.append(
            {
                "id": task["id"],
                "event": task["event"],
                "calls": len(adapter.calls) - before,
                "search_hits": hits,
                "memory": dict(adapter.memory),
                "checkpoint": checkpoint,
            }
        )
    return {
        "budget": budget,
        "strategy": strategy,
        "status": status,
        "initial_context": context,
        "roles": {name: ref.qualified_id for name, ref in roles.items()},
        "problem_id": pid,
        "observations": observations,
        "calls": adapter.calls,
    }


def score(replay_result: dict) -> dict:
    gold = json.loads((HERE / "gold.json").read_text("utf-8"))
    roles, observations = replay_result["roles"], replay_result["observations"]
    context, status = replay_result["initial_context"], replay_result["status"]
    continuation = status.get("continuation") or {}
    must = {
        ObjectRef.model_validate(row["ref"]).qualified_id
        for row in context.get("items", [])
        if row["tier"] == "MUST"
    }
    gold_must = {roles[name] for name in gold["required_roles"]}
    source_found = source_total = negative_found = negative_total = unsafe = safety_known = (
        safety_total
    ) = 0
    no_match = no_match_checked = cross_scope_leaks = irrelevant_hits = 0
    for row in observations:
        expected = gold["tasks"][row["id"]]
        for name in expected.get("key_roles", []):
            source_total += 1
            source_found += roles[name] in {
                ObjectRef.model_validate(h["ref"]).qualified_id for h in row["search_hits"] or []
            }
        for name in expected.get("negative_roles", []):
            negative_total += 1
            negative_found += roles[name] in row["memory"]
        if name := expected.get("forbidden_positive_role"):
            safety_total += 1
            memory = row["memory"].get(roles[name])
            safety_known += memory is not None
            unsafe += bool(
                memory
                and (memory.get("usable_working_premise") or memory.get("trusted_formal_premise"))
            )
        for name in expected.get("forbidden_roles", []):
            leaked = roles[name] in {
                ObjectRef.model_validate(h["ref"]).qualified_id for h in row["search_hits"] or []
            }
            if ObjectRef.parse(roles[name]).problem_id != replay_result["problem_id"]:
                cross_scope_leaks += leaked
            else:
                irrelevant_hits += leaked
        if expected.get("expect_no_hits") and row["search_hits"] is not None:
            no_match_checked += 1
            no_match += not row["search_hits"]
    packets = [
        c["result"] for c in replay_result["calls"] if c["tool"] == "research_context_packet"
    ]
    return {
        "budget": replay_result["budget"],
        "strategy": replay_result["strategy"],
        "selected_problem_correct": continuation.get("problem_id") == replay_result["problem_id"],
        "main_target_correct": (continuation.get("primary_target") or {}).get("ref")
        == roles["main"],
        "latest_checkpoint_correct": (continuation.get("latest_meaningful_checkpoint") or {}).get(
            "ref"
        )
        == roles["checkpoint_source"],
        "must_ref_found": len(gold_must & must),
        "must_ref_total": len(gold_must),
        "must_ref_recall": len(gold_must & must) / len(gold_must),
        "key_source_found_at10": source_found,
        "key_source_total": source_total,
        "key_source_recall_at10": source_found / source_total if source_total else None,
        "negative_memory_found": negative_found,
        "negative_memory_total": negative_total,
        "negative_memory_recall": negative_found / negative_total if negative_total else None,
        "duplicated_failed_route_risk_events": negative_total - negative_found,
        "unsafe_positive_premises": unsafe,
        "safety_decisions_with_evidence": safety_known,
        "safety_decisions_total": safety_total,
        "cross_scope_leaks": cross_scope_leaks,
        "irrelevant_historical_source_hits": irrelevant_hits,
        "no_match_correct": no_match,
        "no_match_checked": no_match_checked,
        "tool_calls": len(replay_result["calls"]),
        "calls_by_tool": dict(Counter(c["tool"] for c in replay_result["calls"])),
        "calls_per_task": {row["id"]: row["calls"] for row in observations},
        "local_reasoning_calls": sum(
            row["calls"] for row in observations if row["event"] == "local_reasoning"
        ),
        "returned_bytes": sum(c["bytes"] for c in replay_result["calls"]),
        "packet_count": len(packets),
        "retrieved_packet_objects": sum(len(p.get("items", [])) for p in packets),
        "packet_estimated_tokens_total": sum(p.get("token_estimate", 0) for p in packets),
        "max_packet_tokens": max((p.get("token_estimate", 0) for p in packets), default=0),
        "tiers": dict(Counter(i["tier"] for p in packets for i in p.get("items", []))),
        "omitted": sum(len(p.get("required_omitted_ids", [])) for p in packets),
        "truncated_items": sum(i["truncated"] for p in packets for i in p.get("items", [])),
        "tool_errors": sum("error" in c["result"] for c in replay_result["calls"]),
        "method": "Deterministic evidence exposure, not measured LLM research behavior",
    }


def evaluate_budget(root: Path, budget: int) -> dict:
    tasks = load_tasks()
    results = []
    seed = build_corpus(root / "seed")
    for strategy in ("A", "B", "C"):
        replay_result = replay(root / strategy, budget, strategy, tasks, seed=seed)
        results.append({"metrics": score(replay_result), "replay": replay_result})
    return {
        "schema_version": 1,
        "tasks": len(tasks),
        "freeze_sha256": freeze_hashes(),
        "results": results,
    }
