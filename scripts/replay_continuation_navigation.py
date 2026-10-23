"""Synthetic continuation replay; optional old runtime for an explicit before/after run.

The legacy driver follows prose-only limits and reproduces representative over-limit
requests. This is a friction replay, not a model benchmark or the missing Run 2 trace.
Never reads a real research workspace. Never changes gold or ranking fixtures.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--runtime-source", type=Path)
args = parser.parse_args()
sys.path.insert(0, str(args.runtime_source or Path(__file__).resolve().parents[1] / "src"))

from math_research.core.workspace import init_workspace, workspace_dir  # noqa: E402
from math_research.ledger.records import store  # noqa: E402
from math_research.mcp.adapter import DESCRIPTIONS, LedgerAdapter  # noqa: E402
from math_research.services.ingest import ingest_episode  # noqa: E402
from math_research.services.research import add_claim, create_problem  # noqa: E402

output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
workspace = output / "synthetic-workspace"
init_workspace(workspace)
state = workspace_dir(workspace)
problem = create_problem(state, "Synthetic continuity", "Synthetic navigation only")
main = add_claim(state, problem.id, "Synthetic orion target")
upstream = add_claim(state, problem.id, "Synthetic input")
store.save_dossier(state, problem.model_copy(update={"primary_claim_id": main.id}))
store.rewrite_claims(
    state,
    problem.id,
    [
        c.model_copy(update={"depends_on": [upstream.id]}) if c.id == main.id else c
        for c in store.list_claims(state, problem.id)
    ],
)
episode = ingest_episode(
    state,
    problem.id,
    "synthetic.md",
    b"# Confirmed Research Increment\n\n"
    b"## RESULT-1\n\n**Statement**\nSynthetic orion result.\n\n"
    b"## PROOF-1\n\n**Target**\nRESULT-1\n\n**Proof**\nSynthetic orion proof.\n\n"
    b"## EVIDENCE-1\n\n**Statement**\nSynthetic orion evidence.\n",
    provenance="Synthetic equivalent navigation replay, no mathematics",
)
eid = episode["episode"]["episode_id"]
eref = f"{problem.id}:episode:{eid}"
adapter, calls = LedgerAdapter(state), []


def call(name, arguments, category):
    try:
        result = adapter.call(name, arguments)
        error = None
    except Exception as exc:
        result, error = {}, type(exc).__name__
    calls.append(
        {
            "tool": name,
            "arguments": arguments,
            "category": category,
            "error": error,
            "bytes": len(json.dumps(result).encode()),
        }
    )
    return result


orientation = call("research_status", {"problem_id": problem.id, "limit": 1}, "state_restore")
prose_guided = "8000" in DESCRIPTIONS["research_get_object"]
if not prose_guided:
    call("research_get_object", {"ref": eref, "length": 8001}, "parameter_error")
exact = call("research_get_object", {"ref": eref}, "state_restore")
mapping = orientation["continuation"]["latest_meaningful_checkpoint"].get("produced_objects")
if mapping:
    refs = [row["qualified_ref"] for row in mapping]
else:
    hits = call(
        "research_search",
        {"problem_id": problem.id, "query": "Synthetic orion", "limit": 50},
        "navigation_workaround",
    )["hits"]
    refs = [
        f"{h['ref']['problem_id']}:{h['ref']['kind']}:{h['ref']['object_id']}"
        for h in hits
        if h["ref"]["kind"] in {"claim", "proof", "evidence"} and h["authority"] == "PROVISIONAL"
    ]
lookup = call("research_search", {"problem_id": problem.id, "query": eid}, "validation_only")
for index, ref in enumerate(sorted(refs)):
    if not prose_guided and index == 0:
        call("research_get_object", {"ref": ref, "length": 8001}, "parameter_error")
    page = call("research_get_object", {"ref": ref}, "exact_content")
    while page.get("next_offset") is not None:
        page = call(
            "research_get_object", {"ref": ref, "offset": page["next_offset"]}, "pagination"
        )
target = f"{problem.id}:claim:{main.id}"
if "16000" not in DESCRIPTIONS["research_context_packet"]:
    call("research_context_packet", {"ref": target, "token_budget": 16001}, "parameter_error")
packet = call("research_context_packet", {"ref": target, "token_budget": 8000}, "state_restore")
mismatches = sum(i["freshness"] == "UNKNOWN" and i["label"] == "STALE" for i in packet["items"])
if mismatches:
    call("research_stale_report", {"problem_id": problem.id}, "state_ambiguity_check")
first = lookup["hits"][0]["ref"] if lookup["hits"] else {}
report = {
    "method": "Representative friction replay, not a real model or exact Run 2 transcript",
    "calls": calls,
    "total_calls": len(calls),
    "calls_by_category": dict(Counter(c["category"] for c in calls)),
    "tool_errors": sum(c["error"] is not None for c in calls),
    "produced_refs_found": len(refs),
    "direct_mapping": bool(mapping),
    "exact_episode_first": first.get("object_id") == eid,
    "exact_episode_extra_hits": max(0, len(lookup["hits"]) - 1),
    "unknown_rendered_stale": mismatches,
    "local_reasoning_tool_calls": 0,
    "read_failures": [c for c in calls if c["error"] and c["category"] != "parameter_error"],
}
(output / "replay.json").write_text(json.dumps(report, indent=2), "utf-8")
print(json.dumps({k: v for k, v in report.items() if k != "calls"}))
if report["read_failures"]:
    raise SystemExit(1)
