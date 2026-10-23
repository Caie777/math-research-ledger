"""Actual adapter replay with declared content requirements; no model-call prediction."""

import json

from math_research.core.refs import ObjectRef
from math_research.mcp.adapter import LedgerAdapter


def evaluate(corpus, budget):
    adapter = LedgerAdapter(corpus["state"])
    roles = corpus["roles"]
    calls = []

    def call(tool, arguments, reason):
        result = adapter.call(tool, arguments)
        calls.append(
            {
                "tool": tool,
                "reason": reason,
                "bytes": len(json.dumps(result, ensure_ascii=False).encode()),
            }
        )
        return result

    call("research_status", {"problem_id": corpus["problem_id"], "limit": 1}, "status_navigation")
    packet = call(
        "research_context_packet",
        {"ref": roles["gap"].qualified_id, "token_budget": budget},
        "required_context",
    )
    items = {ObjectRef.model_validate(i["ref"]).qualified_id: i for i in packet["items"]}
    required = {roles[r].qualified_id for r in ("main", "gap", "premise")}
    should = {
        roles[r].qualified_id
        for r in ("result", "proof", "evidence", "checkpoint", "failed", "counterexample")
    }
    irrelevant = {roles[r].qualified_id for r in ("unrelated", "old_advisory")}
    # Fixed evidence requirements: full primary/Gap/input and proof; checkpoint delta
    # and the other produced/negative identities suffice for operational restoration.
    for role in ("main", "gap", "premise", "proof"):
        ref = roles[role].qualified_id
        if ref in items and items[ref]["full_text"]:
            continue
        offset = 0
        while True:
            page = call(
                "research_get_object",
                {"ref": ref, "offset": offset, "length": 8000},
                "proof_body" if role == "proof" else "required_content_or_pagination",
            )
            if offset + len(page["content"]) >= page["total_characters"]:
                break
            offset += len(page["content"])
    for role in ("result", "evidence", "checkpoint", "failed", "counterexample"):
        if roles[role].qualified_id not in items:
            call(
                "research_get_object",
                {"ref": roles[role].qualified_id},
                "missing_checkpoint_or_negative_navigation",
            )
    bad = [i for key, i in items.items() if key in irrelevant]
    exposed = [ObjectRef.model_validate(i["ref"]).qualified_id for i in packet["items"]]
    unsafe = sum(
        bool(i["usable_working_premise"] or i["trusted_formal_premise"])
        for i in packet["items"]
        if i["freshness"] != "CURRENT"
        or i["research_state"] in {"REFUTED", "HISTORICAL", "INVALIDATED"}
    )
    return {
        "budget": budget,
        "required_recall": len(required & items.keys()) / len(required),
        "should_recall": len(should & items.keys()) / len(should),
        "irrelevant_objects": len(bad),
        "irrelevant_bytes": sum(len(json.dumps(i, ensure_ascii=False).encode()) for i in bad),
        "irrelevant_tokens_estimated": sum(
            (len(json.dumps(i, ensure_ascii=False).encode()) + 2) // 3 for i in bad
        ),
        "duplicate_identities_in_packet": len(exposed) - len(set(exposed)),
        "proof_body_bytes_in_packet": len(
            items.get(roles["proof"].qualified_id, {}).get("content", "").encode()
        ),
        "partial_proof_bytes_reread": len(
            items.get(roles["proof"].qualified_id, {}).get("content", "").encode()
        )
        if not items.get(roles["proof"].qualified_id, {}).get("full_text", False)
        else 0,
        "exact_reads": sum(c["tool"] == "research_get_object" for c in calls),
        "restore_calls": len(calls),
        "calls": calls,
        "required_omissions": packet["required_omitted_ids"],
        "unsafe_premises": unsafe,
        "local_reasoning_calls": 0,
        "packet_tokens": packet["token_estimate"],
        "packet": packet,
    }
