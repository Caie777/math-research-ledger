import pytest

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.manifest import Ledger
from math_research.ledger.records import store
from math_research.services.research import (
    add_claim,
    add_definition,
    create_problem,
    link_dependency,
    update_definition,
)
from math_research.services.retrieval import export_context_packet
from math_research.verification.freshness import Freshness, FreshnessResolver


def test_transitive_cross_scope_dependency_and_coherence(research):
    state, target = research
    foreign = create_problem(state, "Other synthetic scope", "Other scope")
    d = add_definition(state, foreign.id, "D", "definition version one")
    dr = ObjectRef(problem_id=foreign.id, kind="definition", object_id=d.id)
    upstream = add_claim(state, target.problem_id, "Intermediate statement")
    ur = ObjectRef(problem_id=target.problem_id, kind="claim", object_id=upstream.id)
    link_dependency(state, ur, dr, DependencyRole.DEFINITION)
    link_dependency(state, target, ur, DependencyRole.LOGICAL_PREMISE)
    before = Ledger(state).source_version(target.problem_id)
    packet = export_context_packet(state, target, token_budget=16000)
    assert any(i.ref == dr and i.tier == "MUST" for i in packet.items)
    update_definition(
        state, foreign.id, d.model_copy(update={"definition": "definition version two"})
    )
    assert Ledger(state).source_version(target.problem_id) != before
    assert FreshnessResolver(Ledger(state).objects()).resolve(target).freshness == Freshness.STALE


def test_scope_traversal_and_unresolved_dependency_fail_closed(research):
    state, ref = research
    with pytest.raises(ResearchError):
        store.dossier_dir(state, "../../outside")
    claim = store.get_claim(state, ref.problem_id, ref.object_id)
    claim.depends_on = ["CLAIM-9999"]
    store.rewrite_claims(state, ref.problem_id, [claim])
    fresh = FreshnessResolver(Ledger(state).objects()).resolve(ref)
    assert fresh.freshness == Freshness.UNKNOWN and fresh.reasons
    packet = export_context_packet(state, ref, token_budget=4000)
    assert packet.required_omitted_ids and not packet.complete


def test_cycle_and_traversal_cap_cannot_grant_currentness(research):
    state, ref = research
    other = add_claim(state, ref.problem_id, "Other synthetic claim")
    other_ref = ObjectRef(problem_id=ref.problem_id, kind="claim", object_id=other.id)
    link_dependency(state, ref, other_ref, DependencyRole.LOGICAL_PREMISE)
    assert (
        FreshnessResolver(Ledger(state).objects(), max_nodes=1).resolve(ref).freshness
        != Freshness.CURRENT
    )
    link_dependency(state, other_ref, ref, DependencyRole.LOGICAL_PREMISE)
    result = FreshnessResolver(Ledger(state).objects()).resolve(ref)
    assert result.freshness != Freshness.CURRENT and any("Cyclic" in r for r in result.reasons)
