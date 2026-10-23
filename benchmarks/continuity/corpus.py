"""Small synthetic records. Gold lives separately; production code never imports this."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

from math_research.core.jsonl import rewrite_jsonl
from math_research.core.refs import ObjectRef
from math_research.core.workspace import init_workspace, workspace_dir
from math_research.ledger.archive import archive_index, source_path
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.episodes import list_episodes
from math_research.ledger.records import claims, store
from math_research.ledger.records.counterexamples import add_counterexample
from math_research.ledger.records.models import FailedAttempt, ProofAttempt
from math_research.services.acceptance import accept, request_acceptance
from math_research.services.ingest import ingest_episode, review_proposal
from math_research.services.research import (
    add_claim,
    add_definition,
    create_problem,
    link_dependency,
    update_definition,
)
from math_research.services.verification import ExactVerificationService
from math_research.verification.models import CheckOutcome, ExactCertificate


def build_corpus(root: Path) -> dict:
    init_workspace(root)
    state = workspace_dir(root)
    p = create_problem(state, "Synthetic chamber project", "Synthetic continuity only")
    other = create_problem(state, "Distractor chamber project", "Same vocabulary, different scope")
    roles: dict[str, ObjectRef] = {}

    def register(name, kind, row, pid=p.id):
        roles[name] = ObjectRef(problem_id=pid, kind=kind, object_id=row.id)
        return row

    main = register("main", "claim", add_claim(state, p.id, "Primary synthetic chamber objective"))
    problem = store.require_dossier(state, p.id)
    store.save_dossier(state, problem.model_copy(update={"primary_claim_id": main.id}))
    definition = register(
        "definition",
        "definition",
        add_definition(state, p.id, "Chamber", "Fixed synthetic chamber definition"),
    )
    link_dependency(state, roles["main"], roles["definition"], DependencyRole.DEFINITION)
    register(
        "gap_one",
        "gap",
        claims.add_claim(
            state, p.id, claim_type="OPEN_GAP", statement="First open synthetic obstruction"
        ),
    )
    register(
        "gap_two",
        "gap",
        claims.add_claim(
            state, p.id, claim_type="OPEN_GAP", statement="Second open synthetic obstruction"
        ),
    )
    register("current", "claim", add_claim(state, p.id, "CURRENT unverified chamber observation"))
    register(
        "unknown",
        "claim",
        claims.add_claim(
            state,
            p.id,
            claim_type="CLAIM",
            statement="Unknown historical input",
            depends_on=[definition.id],
        ),
    )
    mutable = register(
        "mutable", "definition", add_definition(state, p.id, "Mutable", "Before fixture drift")
    )
    register("stale", "claim", add_claim(state, p.id, "Stale synthetic premise"))
    link_dependency(state, roles["stale"], roles["mutable"], DependencyRole.DEFINITION)
    update_definition(state, p.id, mutable.model_copy(update={"definition": "After fixture drift"}))
    refuted = register("refuted", "claim", add_claim(state, p.id, "A refuted synthetic statement"))
    store.rewrite_claims(
        state,
        p.id,
        [
            c.model_copy(update={"status": "refuted"}) if c.id == refuted.id else c
            for c in store.list_claims(state, p.id)
        ],
    )
    dynamic = register(
        "dynamic_definition",
        "definition",
        add_definition(state, p.id, "Session assumption", "Observed at session start"),
    )
    register(
        "accepted_drift",
        "claim",
        add_claim(state, p.id, "Accepted working premise with mutable input"),
    )
    link_dependency(
        state, roles["accepted_drift"], roles["dynamic_definition"], DependencyRole.DEFINITION
    )

    class FixtureChecker:
        def check(self, certificate):
            return CheckOutcome(
                status="PASSED", summary="Synthetic fixture, no mathematics checked"
            )

    receipt = ExactVerificationService({"continuity-fixture": FixtureChecker()}).verify(
        state,
        roles["accepted_drift"],
        ExactCertificate(checker="continuity-fixture", inputs={}, scope="synthetic fixture only"),
    )
    request = request_acceptance(state, roles["accepted_drift"], receipt.id)
    accept(state, request.id, actor="synthetic fixture human", rationale="test state only")
    link_dependency(state, roles["main"], roles["accepted_drift"], DependencyRole.LOGICAL_PREMISE)

    def episode(name, markdown, pid=p.id):
        result = ingest_episode(
            state, pid, f"{name}.md", markdown.encode(), provenance="synthetic benchmark"
        )
        roles[name + "_source"] = ObjectRef(
            problem_id=pid, kind="episode", object_id=result["episode"]["episode_id"]
        )
        row = next(c for c in result["candidates"] if c["kind"] != "relation")
        roles[name] = ObjectRef(problem_id=pid, kind=row["kind"], object_id=row["object_id"])
        return result, row

    _, rejected = episode(
        "rejected", "## Claim: obsolete radial sketch\n\nRejected synthetic radial argument.\n"
    )
    review_proposal(state, p.id, rejected["candidate_id"], "reject")
    episode(
        "conditional", "## RESULT-1\n\n**Statement**\nConditional chamber working hypothesis.\n"
    )
    episode("local_p1", "## RESULT-1\n\n**Statement**\nShared chamber wording in selected scope.\n")
    episode(
        "local_p2",
        "## RESULT-1\n\n**Statement**\nShared chamber wording in unrelated scope.\n",
        other.id,
    )
    episode(
        "irrelevant",
        "## Claim: old catalog\n\nHistorical orchard catalog with no chamber connection.\n",
    )
    negative = register(
        "negative_target", "claim", add_claim(state, p.id, "Auxiliary radial exploration target")
    )
    failed = FailedAttempt(
        id="FAILED-9001",
        problem_id=p.id,
        attempted_method="radial chamber route | 径向分室路线",
        summary="Previous failed route | 已有失败路线",
        reason_failed="Boundary obstruction prevents reuse | 边界障碍，勿重复",
        artifacts=[],
    )
    store.add_failed_attempt(
        state,
        p.id,
        attempted_method=failed.attempted_method,
        summary=failed.summary,
        reason_failed=failed.reason_failed,
    )
    failed = store.list_failed_attempts(state, p.id)[-1]
    register("failed_route", "failed_attempt", failed)
    ce = add_counterexample(
        state,
        p.id,
        target_id=negative.id,
        construction="Synthetic chamber witness | 分室反例",
        verification="Synthetic narrative only, not verified mathematics",
        scope="radial boundary | 径向边界",
        title="Radial chamber counterexample",
    )
    register("counterexample", "counterexample", ce)
    proof = ProofAttempt(
        id="PROOF-9001",
        problem_id=p.id,
        title="Radial chamber refutation | 径向反驳",
        claim_links=[negative.id],
        conclusion_relation="REFUTES",
    )
    store.append_proof_attempt(state, proof)
    register("refutation", "proof", proof)
    checkpoint, _ = episode(
        "checkpoint",
        "## Claim: session increment\n\nA synthetic checkpoint increment.\n\n"
        f"## CURRENT RESEARCH HANDOFF\nTarget: {main.id}\n"
        "### Active obstacles\nRefer to the existing gaps.\n",
    )
    # A later pure plan must not replace the latest actual research increment.
    plan = ingest_episode(
        state,
        p.id,
        "plan.md",
        b"# Next Research Directions\n\nA later advisory note only.\n",
        provenance="synthetic benchmark",
    )
    roles["advisory_source"] = ObjectRef(
        problem_id=p.id, kind="episode", object_id=plan["episode"]["episode_id"]
    )
    bad, _ = episode("corrupt", "## Claim: quarantine\n\nSynthetic quarantined evidence.\n")
    records = list_episodes(state)
    order = {
        checkpoint["episode"]["episode_id"]: 20,
        plan["episode"]["episode_id"]: 21,
        bad["episode"]["episode_id"]: 22,
    }
    rewrite_jsonl(
        archive_index(state),
        [
            e.model_copy(
                update={
                    "imported_at": datetime(
                        2020, 1, 1, 0, 0, order.get(e.episode_id, 1), tzinfo=UTC
                    )
                }
            )
            for e in records
        ],
    )
    path = source_path(state, bad["episode"]["archive_path"])
    path.write_bytes(path.read_bytes() + b"\nSYNTHETIC_TAMPER_ONLY\n")
    store.set_active_problem(state, other.id)
    return {
        "state": state,
        "problem_id": p.id,
        "other_problem_id": other.id,
        "roles": roles,
        "dynamic_definition": dynamic,
    }


def drift(corpus):
    state, pid, original = corpus["state"], corpus["problem_id"], corpus["dynamic_definition"]
    update_definition(
        state, pid, original.model_copy(update={"definition": "Changed after restore"})
    )


def clone_corpus(corpus, root):
    """Every strategy starts with identical synthetic bytes, in a separate workspace."""
    shutil.copytree(corpus["state"].parent, root)
    return {**corpus, "state": workspace_dir(root)}
