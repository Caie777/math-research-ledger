"""Fixed graph roles and unrelated lexical distractors, not real mathematics."""

from pathlib import Path

import yaml

from math_research.core.refs import ObjectRef
from math_research.core.workspace import init_workspace, workspace_dir
from math_research.ledger.episodes import list_candidates
from math_research.ledger.identity import working_ref
from math_research.ledger.manifest import Ledger
from math_research.ledger.records import claims, store
from math_research.ledger.records.counterexamples import add_counterexample
from math_research.services.ingest import ingest_episode
from math_research.services.research import add_claim, create_problem


def build(root: Path) -> dict:
    init_workspace(root)
    state = workspace_dir(root)
    p = create_problem(state, "Synthetic local trade", "Synthetic precision only")
    main = add_claim(state, p.id, "Synthetic main local trade objective")
    premise = add_claim(state, p.id, "Synthetic current input")
    gap = claims.add_claim(
        state,
        p.id,
        claim_type="OPEN_GAP",
        statement="Synthetic three atom local trade gap",
        depends_on=[main.id, premise.id],
    )
    store.save_dossier(state, p.model_copy(update={"primary_claim_id": main.id}))
    roles = {
        "main": ObjectRef(problem_id=p.id, kind="claim", object_id=main.id),
        "premise": ObjectRef(problem_id=p.id, kind="claim", object_id=premise.id),
        "gap": ObjectRef(problem_id=p.id, kind="gap", object_id=gap.id),
    }
    unrelated = add_claim(
        state,
        p.id,
        (
            "Synthetic three atom local trade gap boundary "
            "prime L2 primitive-divisor unrelated route. " * 8
        ),
    )
    roles["unrelated"] = ObjectRef(problem_id=p.id, kind="claim", object_id=unrelated.id)
    advisory = ingest_episode(
        state,
        p.id,
        "old-advisory.md",
        b"# Next Research Directions\n\nSynthetic three atom local trade gap "
        b"primitive-divisor old unrelated plan.\n",
        provenance="synthetic",
        archive_only=True,
    )
    roles["old_advisory"] = ObjectRef(
        problem_id=p.id, kind="episode", object_id=advisory["episode"]["episode_id"]
    )
    failed = store.add_failed_attempt(
        state,
        p.id,
        attempted_method="Synthetic local trade dead route",
        summary="Direct failed route",
        reason_failed="Synthetic obstruction",
        artifacts=[gap.id],
    )
    roles["failed"] = ObjectRef(problem_id=p.id, kind="failed_attempt", object_id=failed.id)
    counter = add_counterexample(
        state,
        p.id,
        target_id=gap.id,
        construction="Synthetic witness",
        verification="Unverified fixture narrative only",
        scope="Synthetic local trade",
        title="Direct local witness",
    )
    roles["counterexample"] = ObjectRef(
        problem_id=p.id, kind="counterexample", object_id=counter.id
    )
    meta = {
        "state_delta": [
            {
                "action": "Still Open",
                "reference": roles["gap"].qualified_id,
                "statement": "Synthetic remaining local obstruction.",
            }
        ],
        "input_versions": [
            {"ref": roles["main"].model_dump(), "version": Ledger(state).get(roles["main"]).version}
        ],
    }
    raw = "---\n" + yaml.safe_dump(meta) + "---\n\n# Confirmed Research Increment\n\n"
    raw += (
        f"## RESULT-1\n\n**Statement**\nSynthetic local increment.\n\n**Target**\n{gap.id}\n\n"
        f"**Uses**\n{roles['main'].qualified_id}\n\n"
    )
    raw += (
        "## PROOF-1\n\n**Target**\nRESULT-1\n\n**Proof**\n"
        + ("LARGE_PROOF_MARKER synthetic argument step. " * 400)
        + "\n\n"
    )
    raw += (
        "## EVIDENCE-1\n\n**Statement**\nSynthetic local observation.\n\n**Target**\nRESULT-1\n\n"
        "# Next Research Directions\n\nAdvisory only.\n"
    )
    value = ingest_episode(
        state, p.id, "checkpoint.md", raw.encode(), provenance="synthetic precision"
    )
    eid = value["episode"]["episode_id"]
    roles["checkpoint"] = ObjectRef(problem_id=p.id, kind="episode", object_id=eid)
    for c in list_candidates(state, p.id, eid):
        if c.kind != "relation" and c.local_id:
            roles[
                {"RESULT-1": "result", "PROOF-1": "proof", "EVIDENCE-1": "evidence"}[c.local_id]
            ] = working_ref(c)
    return {"state": state, "problem_id": p.id, "roles": roles}
