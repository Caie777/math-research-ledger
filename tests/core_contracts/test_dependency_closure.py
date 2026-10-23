"""Scoped identity, authentic input pins and conservative premise projection."""

import pytest
import yaml

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.episodes import list_candidates
from math_research.ledger.manifest import Ledger
from math_research.ledger.projection import get_object
from math_research.ledger.records import store
from math_research.ledger.records.models import ClaimRecord, ProofAttempt
from math_research.ledger.state import KnowledgeStateResolver
from math_research.mcp.adapter import LedgerAdapter
from math_research.services.ingest import ingest_episode, review_proposal
from math_research.services.research import add_claim, create_problem, link_dependency
from math_research.verification.freshness import FreshnessResolver


def numbered(state, pid):
    raw = b"""# Confirmed Research Increment

## RESULT-1

**Statement**
First synthetic result.

## RESULT-2

**Statement**
Dependent synthetic result.

**Uses**
RESULT-1
"""
    ingest_episode(state, pid, "synthetic.md", raw, provenance="synthetic closure test")
    return {
        c.local_id: c for c in list_candidates(state, pid) if c.kind != "relation" and c.local_id
    }


def ref(candidate):
    return ObjectRef(
        problem_id=candidate.problem_id,
        kind=candidate.kind,
        object_id=candidate.object_id or candidate.candidate_id,
    )


def test_same_episode_uses_resolves_stable_identity_and_pins_authored_snapshot(research):
    state, target = research
    rows = numbered(state, target.problem_id)
    upstream, downstream = ref(rows["RESULT-1"]), ref(rows["RESULT-2"])
    entry = Ledger(state).get(downstream)
    assert [e.target for e in entry.dependencies] == [upstream]
    assert entry.dependencies[0].expected_version == Ledger(state).get(upstream).version
    assert get_object(state, downstream).freshness == "CURRENT"


def test_unpinned_legacy_dependency_is_unknown_without_inventing_history(research):
    state, downstream = research
    upstream = add_claim(state, downstream.problem_id, "Old upstream content")
    old = store.get_claim(state, downstream.problem_id, downstream.object_id)
    store.rewrite_claims(
        state,
        downstream.problem_id,
        [old.model_copy(update={"depends_on": [upstream.id]}), upstream],
    )
    before = (state / "problems" / downstream.problem_id / "claims.jsonl").read_bytes()
    view = get_object(state, downstream)
    assert view.freshness == "UNKNOWN"
    assert any("Unbound" in reason for reason in view.freshness_reasons)
    assert not view.object.dependencies[0].expected_version
    assert (state / "problems" / downstream.problem_id / "claims.jsonl").read_bytes() == before
    store.rewrite_claims(
        state,
        downstream.problem_id,
        [
            old.model_copy(update={"depends_on": [upstream.id]}),
            upstream.model_copy(update={"statement": "Changed upstream content"}),
        ],
    )
    assert get_object(state, downstream).freshness == "UNKNOWN"


@pytest.mark.parametrize("status", ["refuted", "rejected", "invalidated"])
def test_semantically_invalid_upstream_blocks_both_projections_even_with_current_pin(
    research, status
):
    state, downstream = research
    if status == "rejected":
        rows = numbered(state, downstream.problem_id)
        candidate = rows["RESULT-1"]
        review_proposal(state, downstream.problem_id, candidate.candidate_id, "reject")
        upstream = ref(candidate)
    elif status == "invalidated":
        record = ProofAttempt(id="PROOF-9000", problem_id=downstream.problem_id, status="blocked")
        store.append_proof_attempt(state, record)
        upstream = ObjectRef(problem_id=downstream.problem_id, kind="proof", object_id=record.id)
    else:
        record = add_claim(state, downstream.problem_id, "A refuted synthetic premise")
        claims = store.list_claims(state, downstream.problem_id)
        store.rewrite_claims(
            state,
            downstream.problem_id,
            [
                c.model_copy(update={"status": "refuted"}) if c.id == record.id else c
                for c in claims
            ],
        )
        upstream = ObjectRef(problem_id=downstream.problem_id, kind="claim", object_id=record.id)
    link_dependency(state, downstream, upstream, DependencyRole.LOGICAL_PREMISE)
    view = get_object(state, downstream)
    assert view.freshness == "CURRENT"  # semantic invalidity is not byte drift
    assert not view.usable_working_premise
    assert view.premise_eligibility == "BLOCKED"
    assert view.premise_reasons
    old = KnowledgeStateResolver(state).resolve(downstream.problem_id)[downstream.object_id]
    assert not old.usable_premise
    assert old.premise_eligibility == view.premise_eligibility
    assert old.premise_reasons == view.premise_reasons


def external_episode(state, pid, upstream, *, pin=True):
    metadata = (
        {
            "input_versions": [
                {"ref": upstream.model_dump(), "version": Ledger(state).get(upstream).version}
            ]
        }
        if pin
        else {}
    )
    raw = (
        "---\n" + yaml.safe_dump(metadata) + "---\n\n## Claim: Cross episode result\n"
        f"Uses: {upstream.qualified_id}\n\nA synthetic dependent statement.\n"
    ).encode()
    value = ingest_episode(state, pid, "external.md", raw, provenance="synthetic versioned input")
    return next(
        c for c in list_candidates(state, pid) if c.episode_id == value["episode"]["episode_id"]
    )


def test_cross_episode_explicit_pin_and_review_keep_historical_version(research):
    state, target = research
    rows = numbered(state, target.problem_id)
    upstream = ref(rows["RESULT-1"])
    downstream = external_episode(state, target.problem_id, upstream)
    old_pin = Ledger(state).get(ref(downstream)).dependencies[0].expected_version
    reviewed = review_proposal(state, target.problem_id, rows["RESULT-1"].candidate_id, "accept")
    canonical = ObjectRef(problem_id=target.problem_id, kind="claim", object_id=reviewed.mapped_id)
    assert Ledger(state).resolve(upstream.qualified_id) == canonical
    edge = Ledger(state).get(ref(downstream)).dependencies[0]
    assert edge.target == canonical and edge.expected_version == old_pin
    assert get_object(state, ref(downstream)).freshness == "STALE"  # no automatic rebase
    assert (
        Ledger(state).resolve(rows["RESULT-1"].candidate_id, problem_id=target.problem_id)
        == canonical
    )


@pytest.mark.parametrize("decision", ["defer", "reject"])
def test_review_does_not_upgrade_or_orphan_dependency(research, decision):
    state, target = research
    rows = numbered(state, target.problem_id)
    candidate = rows["RESULT-1"]
    review_proposal(state, target.problem_id, candidate.candidate_id, decision)
    entry = Ledger(state).get(ref(rows["RESULT-2"]))
    assert entry.dependencies[0].target == ref(candidate)
    assert Ledger(state).get(ref(candidate)).authority == (
        "PROVISIONAL" if decision == "defer" else "REJECTED/HISTORICAL"
    )
    assert get_object(state, ref(rows["RESULT-2"])).premise_eligibility == (
        "CONDITIONAL" if decision == "defer" else "BLOCKED"
    )


def test_scope_and_episode_context_never_guess_bare_local_ids(research):
    state, target = research
    other = create_problem(state, "Other synthetic Problem", "Other synthetic scope")
    a = numbered(state, target.problem_id)
    b = numbered(state, other.id)
    assert Ledger(state).get(ref(a["RESULT-2"])).dependencies[0].target == ref(a["RESULT-1"])
    assert Ledger(state).get(ref(b["RESULT-2"])).dependencies[0].target == ref(b["RESULT-1"])
    assert Ledger(state).resolve(
        "RESULT-1", problem_id=other.id, episode_id=b["RESULT-1"].episode_id
    ) == ref(b["RESULT-1"])
    explanation = Ledger(state).explain("RESULT-1", problem_id=other.id)
    assert explanation.ref is None and explanation.reason == "EPISODE_CONTEXT_REQUIRED"
    collision = ClaimRecord(
        id=target.object_id, problem_id=other.id, type="CLAIM", statement="Other"
    )
    store.append_claim(state, collision)
    with pytest.raises(ResearchError, match="ambiguous"):
        Ledger(state).resolve(target.object_id)
    assert Ledger(state).resolve(target.object_id, problem_id=other.id).problem_id == other.id


def test_explicit_unknown_input_is_unbound_not_ingest_time_pin(research):
    state, target = research
    candidate = external_episode(state, target.problem_id, target, pin=False)
    view = get_object(state, ref(candidate))
    assert view.freshness == "UNKNOWN"
    assert view.object.dependencies[0].expected_version is None
    missing = Ledger(state).explain("CLAIM-9999", problem_id=target.problem_id)
    assert missing.ref is None and missing.reason == "MISSING_OBJECT"


@pytest.mark.parametrize("role", list(DependencyRole))
def test_role_policy_keeps_unbound_conservative_and_pinned_drift_detected(research, role):
    state, target = research
    other = add_claim(state, target.problem_id, "Role upstream")
    upstream = ObjectRef(problem_id=target.problem_id, kind="claim", object_id=other.id)
    link_dependency(state, target, upstream, role)
    claims = store.list_claims(state, target.problem_id)
    store.rewrite_claims(
        state,
        target.problem_id,
        [
            c.model_copy(update={"statement": "Revised role upstream"}) if c.id == other.id else c
            for c in claims
        ],
    )
    assert FreshnessResolver(Ledger(state).objects()).resolve(target).freshness == "STALE"


def test_mcp_get_search_context_share_conditional_eligibility_and_reasons(research):
    state, target = research
    candidate = numbered(state, target.problem_id)["RESULT-1"]
    reference = ref(candidate)
    adapter = LedgerAdapter(state)
    got = adapter.call("research_get_object", {"ref": reference.qualified_id})
    hits = adapter.call(
        "research_search", {"query": "First synthetic result", "problem_id": target.problem_id}
    )["hits"]
    hit = next(h for h in hits if h["ref"] == reference.model_dump())
    packet = adapter.call(
        "research_context_packet", {"ref": reference.qualified_id, "token_budget": 16000}
    )
    item = next(i for i in packet["items"] if i["ref"] == reference.model_dump())
    for output in (got, hit, item):
        assert output["premise_eligibility"] == "CONDITIONAL"
        assert output["conditional_premise"]
        assert not output["usable_working_premise"]
        assert output["premise_reasons"] == got["premise_reasons"]
        assert not output["trusted_formal_premise"]


def test_numbered_qualified_uses_preserves_foreign_scope_even_with_colliding_id(research):
    state, local = research
    other = create_problem(state, "Other scope", "Other scope")
    store.append_claim(
        state,
        ClaimRecord(
            id=local.object_id, problem_id=other.id, type="CLAIM", statement="Foreign original"
        ),
    )
    foreign = local.model_copy(update={"problem_id": other.id})
    pin = {"ref": foreign.model_dump(), "version": Ledger(state).get(foreign).version}
    raw = (
        "---\n" + yaml.safe_dump({"input_versions": [pin]}) + "---\n"
        "## RESULT-1\n\n**Statement**\nForeign use.\n\n**Uses**\n" + foreign.qualified_id + "\n"
    ).encode()
    ingest_episode(state, local.problem_id, "scoped.md", raw, provenance="synthetic scope")
    candidate = next(c for c in list_candidates(state, local.problem_id) if c.kind == "claim")
    edge = Ledger(state).get(ref(candidate)).dependencies[0]
    assert edge.target == foreign and edge.expected_version == pin["version"]
    assert get_object(state, ref(candidate)).freshness == "CURRENT"


@pytest.mark.parametrize("role", list(DependencyRole))
def test_unpinned_role_is_unknown_even_when_target_exists(research, role):
    from math_research.ledger.dependencies import Dependency
    from math_research.ledger.manifest import ManifestEntry

    _, target = research
    upstream = target.model_copy(update={"object_id": "CLAIM-9000"})

    def entry(reference, deps=()):
        return ManifestEntry(
            ref=reference,
            content_hash="a" * 64,
            research_state="CURRENT",
            authority="CANONICAL",
            verification="NOT_CHECKED",
            review="ACCEPTED",
            record={},
            full_content="Synthetic",
            dependencies=list(deps),
        )

    rows = [
        entry(target, [Dependency(dependent=target, target=upstream, role=role)]),
        entry(upstream),
    ]
    result = FreshnessResolver(rows).resolve(target)
    assert result.freshness == "UNKNOWN" and any("Unbound" in r for r in result.reasons)


def test_explicit_pin_revision_transitive_stale_and_receipt_history_is_immutable(research):
    from test_authority import checked

    from math_research.services.acceptance import accept, request_acceptance

    state, downstream = research
    middle = add_claim(state, downstream.problem_id, "Middle")
    top = add_claim(state, downstream.problem_id, "Top")
    mr = downstream.model_copy(update={"object_id": middle.id})
    tr = downstream.model_copy(update={"object_id": top.id})
    link_dependency(state, downstream, mr, DependencyRole.LOGICAL_PREMISE)
    link_dependency(state, mr, tr, DependencyRole.LOGICAL_PREMISE)
    # Pin downstream after its upstream's dependency contract is finalized.
    link_dependency(state, downstream, mr, DependencyRole.LOGICAL_PREMISE)
    receipt = checked(state, downstream)
    request = request_acceptance(state, downstream, receipt.id)
    accept(state, request.id, actor="synthetic human", rationale="synthetic test only")
    history = {
        name: (state / "ledger" / name).read_bytes()
        for name in ("verifications.jsonl", "acceptances.jsonl")
    }
    rows = store.list_claims(state, downstream.problem_id)
    store.rewrite_claims(
        state,
        downstream.problem_id,
        [c.model_copy(update={"statement": "Revised top"}) if c.id == top.id else c for c in rows],
    )
    view = get_object(state, downstream)
    assert view.freshness == "STALE" and view.authority == "HUMAN_ACCEPTED"
    assert not view.usable_working_premise and not view.trusted_formal_premise
    for name, raw in history.items():
        assert (state / "ledger" / name).read_bytes() == raw


def test_same_episode_cycle_stays_unknown_and_bounded(research):
    state, target = research
    raw = (
        b"## RESULT-1\n\n**Statement**\nOne.\n\n**Uses**\nRESULT-2\n\n"
        b"## RESULT-2\n\n**Statement**\nTwo.\n\n**Uses**\nRESULT-1\n"
    )
    ingest_episode(state, target.problem_id, "cycle.md", raw, provenance="synthetic cycle")
    candidate = next(c for c in list_candidates(state, target.problem_id) if c.kind == "claim")
    result = FreshnessResolver(Ledger(state).objects()).resolve(ref(candidate))
    assert result.freshness != "CURRENT" and any("Cyclic" in r for r in result.reasons)


def test_missing_ref_has_reason_and_cannot_become_a_premise(research):
    state, target = research
    old = store.get_claim(state, target.problem_id, target.object_id)
    store.rewrite_claims(
        state, target.problem_id, [old.model_copy(update={"depends_on": ["CLAIM-9999"]})]
    )
    view = get_object(state, target)
    assert view.object.dependencies[0].resolution_reason == "MISSING_OBJECT"
    assert view.freshness == "UNKNOWN" and view.premise_eligibility == "BLOCKED"
    bad_kind = ObjectRef(problem_id=target.problem_id, kind="proof", object_id=target.object_id)
    assert Ledger(state).explain(bad_kind.qualified_id).ref is None


def test_read_review_and_duplicate_ingest_never_repin_external_history(research):
    state, target = research
    candidate = external_episode(state, target.problem_id, target)
    original = Ledger(state).get(ref(candidate)).dependencies[0].expected_version
    rows = store.list_claims(state, target.problem_id)
    store.rewrite_claims(
        state,
        target.problem_id,
        [c.model_copy(update={"statement": "Now different"}) for c in rows],
    )
    for _ in range(2):
        view = get_object(state, ref(candidate))
        assert view.freshness == "STALE"
        assert view.object.dependencies[0].expected_version == original
    reviewed = review_proposal(state, target.problem_id, candidate.candidate_id, "accept")
    canonical = target.model_copy(update={"object_id": reviewed.mapped_id})
    assert Ledger(state).get(canonical).dependencies[0].expected_version == original


def test_mcp_blocked_eligibility_reasons_match_for_refuted_upstream(research):
    state, target = research
    other = add_claim(state, target.problem_id, "Refuted upstream")
    store.rewrite_claims(
        state,
        target.problem_id,
        [
            c.model_copy(update={"status": "refuted"}) if c.id == other.id else c
            for c in store.list_claims(state, target.problem_id)
        ],
    )
    link_dependency(
        state,
        target,
        target.model_copy(update={"object_id": other.id}),
        DependencyRole.LOGICAL_PREMISE,
    )
    adapter = LedgerAdapter(state)
    got = adapter.call("research_get_object", {"ref": target.qualified_id})
    hit = next(
        h
        for h in adapter.call(
            "research_search",
            {"query": "complete synthetic claim", "problem_id": target.problem_id},
        )["hits"]
        if h["ref"] == target.model_dump()
    )
    item = next(
        i
        for i in adapter.call(
            "research_context_packet", {"ref": target.qualified_id, "token_budget": 16000}
        )["items"]
        if i["ref"] == target.model_dump()
    )
    for output in (got, hit, item):
        assert output["premise_eligibility"] == "BLOCKED"
        assert output["premise_reasons"] == got["premise_reasons"]
        assert not output["usable_working_premise"]


def test_legacy_proposal_reads_do_not_backfill_ids_or_pins(research):
    import json

    state, target = research
    rows = numbered(state, target.problem_id)
    path = state / "problems" / target.problem_id / "archive/episodes/candidates.jsonl"
    values = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    for row in values:
        row.pop("dependency_pins", None)
        row.pop("object_id", None)
    path.write_text("".join(json.dumps(row) + "\n" for row in values), encoding="utf-8")
    before = path.read_bytes()
    downstream = ObjectRef(
        problem_id=target.problem_id, kind="claim", object_id=rows["RESULT-2"].candidate_id
    )
    view = get_object(state, downstream)
    assert view.freshness == "UNKNOWN"
    assert view.object.dependencies[0].target.object_id == rows["RESULT-1"].candidate_id
    assert view.object.dependencies[0].resolution_reason is None
    LedgerAdapter(state).call(
        "research_context_packet", {"ref": downstream.qualified_id, "token_budget": 16000}
    )
    assert path.read_bytes() == before


def test_explicit_proof_target_pin_is_kept_without_promoting_authority(research):
    state, target = research
    version = Ledger(state).get(target).version
    raw = (
        "---\n"
        + yaml.safe_dump({"input_versions": [{"ref": target.model_dump(), "version": version}]})
        + "---\n## Proof: Synthetic argument\nTarget: "
        + target.qualified_id
        + "\n\nA complete synthetic argument.\n"
    ).encode()
    ingest_episode(state, target.problem_id, "proof.md", raw, provenance="synthetic proof input")
    candidate = next(c for c in list_candidates(state, target.problem_id) if c.kind == "proof")
    view = get_object(state, ref(candidate))
    assert view.object.dependencies[0].role == DependencyRole.PROOF_TARGET
    assert view.object.dependencies[0].expected_version == version
    assert view.authority == "PROVISIONAL" and not view.trusted_formal_premise


def test_local_scope_context_has_priority_over_bare_lookalikes(research):
    from math_research.ledger.identity import ScopedIdentityResolver

    state, target = research
    rows = numbered(state, target.problem_id)
    lookalike = target.model_copy(update={"object_id": "RESULT-1"})
    resolver = ScopedIdentityResolver([lookalike, ref(rows["RESULT-1"])], list(rows.values()))
    assert resolver.resolve(
        "RESULT-1", problem_id=target.problem_id, episode_id=rows["RESULT-1"].episode_id
    ).ref == ref(rows["RESULT-1"])
    assert resolver.resolve(lookalike.qualified_id).ref == lookalike


def test_public_knowledge_state_uses_the_same_conditional_decision(research):
    state, target = research
    rows = numbered(state, target.problem_id)
    reference = ref(rows["RESULT-2"])
    view = get_object(state, reference)
    knowledge = KnowledgeStateResolver(state).resolve(target.problem_id)[reference.object_id]
    assert view.premise_eligibility == knowledge.premise_eligibility == "CONDITIONAL"
    assert knowledge.premise_reasons == view.premise_reasons
    assert knowledge.conditional_premise and not knowledge.usable_premise


def test_explicit_missing_target_keeps_the_supplied_historical_pin(research):
    state, target = research
    missing = target.model_copy(update={"object_id": "CLAIM-9999"})
    raw = (
        "---\n"
        + yaml.safe_dump({"input_versions": [{"ref": missing.model_dump(), "version": "a" * 64}]})
        + "---\n## Claim: Missing input\nUses: "
        + missing.qualified_id
        + "\n\nA conditional synthetic result.\n"
    ).encode()
    ingest_episode(state, target.problem_id, "missing.md", raw, provenance="synthetic missing pin")
    candidate = next(c for c in list_candidates(state, target.problem_id) if c.kind == "claim")
    view = get_object(state, ref(candidate))
    assert view.object.dependencies[0].expected_version == "a" * 64
    assert view.freshness == "STALE" and not view.usable_working_premise


def test_missing_local_object_distinguishes_absent_context_from_absent_object(research):
    state, target = research
    rows = numbered(state, target.problem_id)
    result = Ledger(state).explain(
        "RESULT-999", problem_id=target.problem_id, episode_id=rows["RESULT-1"].episode_id
    )
    assert result.ref is None and result.reason == "MISSING_LOCAL_OBJECT"


def test_checked_conjecture_requires_human_acceptance_before_unconditional_working_use(research):
    from test_authority import checked

    from math_research.services.acceptance import accept, request_acceptance

    state, target = research
    rows = store.list_claims(state, target.problem_id)
    store.rewrite_claims(
        state, target.problem_id, [c.model_copy(update={"type": "CONJECTURE"}) for c in rows]
    )
    receipt = checked(state, target)
    assert get_object(state, target).premise_eligibility == "CONDITIONAL"
    request = request_acceptance(state, target, receipt.id)
    accept(state, request.id, actor="synthetic human", rationale="synthetic exact check review")
    view = get_object(state, target)
    assert view.authority == "HUMAN_ACCEPTED" and view.premise_eligibility == "ALLOWED"
    assert not view.trusted_formal_premise  # exact verification is not formal correspondence


def test_kind_filter_cannot_be_bypassed_by_a_candidate_alias(research):
    state, target = research
    candidate = numbered(state, target.problem_id)["RESULT-1"]
    with pytest.raises(ResearchError):
        Ledger(state).resolve(candidate.candidate_id, problem_id=target.problem_id, kind="proof")
    assert Ledger(state).resolve(
        candidate.candidate_id, problem_id=target.problem_id, kind="claim"
    ) == ref(candidate)


def test_malformed_legacy_reference_is_retained_as_diagnostic_not_dropped(research):
    state, target = research
    old = store.get_claim(state, target.problem_id, target.object_id)
    store.rewrite_claims(
        state, target.problem_id, [old.model_copy(update={"depends_on": ["not/an/object"]})]
    )
    view = get_object(state, target)
    assert view.freshness == "UNKNOWN" and not view.usable_working_premise
    assert view.object.dependencies[0].resolution_reason == "MALFORMED_REFERENCE"
