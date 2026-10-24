import hashlib

import pytest

from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash
from math_research.core.refs import ObjectRef
from math_research.ledger.dependencies import DependencyRole
from math_research.ledger.episodes import list_reviews
from math_research.ledger.manifest import Ledger
from math_research.ledger.records import store
from math_research.ledger.records.models import ClaimRecord
from math_research.ledger.records.write_boundary import automated_scope
from math_research.services.ingest import ingest_episode, preview_episode, review_proposal
from math_research.services.research import (
    add_definition,
    create_problem,
    link_dependency,
    update_definition,
)
from math_research.verification.freshness import Freshness, FreshnessResolver


def snapshot(path):
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in path.rglob("*")
        if p.is_file()
    }


def test_typed_full_content_roundtrip_provenance(research):
    state, ref = research
    definition = add_definition(state, ref.problem_id, "Synthetic D", "full definition\n" * 100)
    reread = store.list_definitions(state, ref.problem_id)[0]
    assert reread == definition
    dref = ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=definition.id)
    assert Ledger(state).get(dref).record["definition"] == definition.definition
    assert (
        ClaimRecord.model_validate(Ledger(state).get(ref).record).statement
        == "A complete synthetic claim"
    )


def test_qualified_refs_refuse_cross_problem_collision(research):
    state, ref = research
    other = create_problem(state, "Other", "Other problem")
    collision = ClaimRecord(
        id=ref.object_id, problem_id=other.id, type="CLAIM", statement="Different content"
    )
    store.append_claim(state, collision)
    with pytest.raises(ResearchError, match="ambiguous"):
        Ledger(state).resolve(ref.object_id)
    assert Ledger(state).resolve(ref.qualified_id) == ref
    assert (
        Ledger(state)
        .get(ObjectRef(problem_id=other.id, kind="claim", object_id=ref.object_id))
        .record["statement"]
        == "Different content"
    )


def test_hash_versions_and_transitive_stale_keep_history(research):
    state, ref = research
    d = add_definition(state, ref.problem_id, "D", "original full definition")
    dref = ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=d.id)
    edge = link_dependency(state, ref, dref, DependencyRole.DEFINITION)
    before = (state / "ledger/dependencies.jsonl").read_bytes()
    assert link_dependency(state, ref, dref, DependencyRole.DEFINITION) == edge
    assert (state / "ledger/dependencies.jsonl").read_bytes() == before
    version = Ledger(state).get(dref).version
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})
    update_definition(
        state, ref.problem_id, d.model_copy(update={"definition": "changed definition"})
    )
    assert Ledger(state).get(dref).version != version
    assert FreshnessResolver(Ledger(state).objects()).resolve(ref).freshness == Freshness.STALE
    assert (state / "ledger/dependencies.jsonl").read_bytes() == before
    snapshots = list((state / "ledger/versions").rglob("*.json"))
    assert len(snapshots) == 2 and any(
        "original full definition" in p.read_text() for p in snapshots
    )


def test_dependency_roles_not_conflated(research):
    state, ref = research
    d = add_definition(state, ref.problem_id, "D", "content")
    dref = ObjectRef(problem_id=ref.problem_id, kind="definition", object_id=d.id)
    link_dependency(state, ref, dref, DependencyRole.DEFINITION)
    link_dependency(state, ref, dref, DependencyRole.SOURCE_REFERENCE)
    assert {e.role for e in Ledger(state).get(ref).dependencies} == {
        DependencyRole.DEFINITION,
        DependencyRole.SOURCE_REFERENCE,
    }


def episode(ref):
    return (
        (
            f"---\ntarget_claim_id: {ref.object_id}\n---\n\n"
            f"## Proof: full proof\nTarget: {ref.object_id}\n\n"
        ).encode()
        + ("This is full synthetic proof text.\n" * 150).encode()
        + b"\n## Failed Attempt: dead route\n\nAn explicit failed synthetic route.\n"
    )


def test_ingest_provisional_idempotent_full_body_and_negative_history(research):
    state, ref = research
    raw = episode(ref)
    before = snapshot(state)
    assert preview_episode(state, ref.problem_id, "output.md", raw)["candidates"]
    assert snapshot(state) == before
    result = ingest_episode(
        state, ref.problem_id, "output.md", raw, provenance="external harness synthetic test"
    )
    repeat = ingest_episode(
        state, ref.problem_id, "output.md", raw, provenance="external harness synthetic test"
    )
    assert repeat["duplicate"] and result["canonical_records_created"] == 0
    proofs = [e for e in Ledger(state).objects(ref.problem_id) if e.ref.kind == "proof"]
    assert len(proofs) == 1 and proofs[0].full_content.count("full synthetic proof text") == 150
    assert proofs[0].authority == "PROVISIONAL"
    candidate = next(c for c in result["candidates"] if c["kind"] == "proof")
    with automated_scope(), pytest.raises(ResearchError):
        review_proposal(state, ref.problem_id, candidate["candidate_id"], "accept")
    review_proposal(state, ref.problem_id, candidate["candidate_id"], "reject")
    assert len(list_reviews(state, ref.problem_id)) == 1
    entries = Ledger(state).objects(ref.problem_id)
    assert any(e.ref.kind == "failed_attempt" for e in entries)
    assert any(e.authority == "REJECTED/HISTORICAL" for e in entries)


def test_malformed_ingest_and_tampered_preview_do_not_write_research_records(research):
    state, ref = research
    before = snapshot(state)
    with pytest.raises(ResearchError):
        ingest_episode(state, ref.problem_id, "x.md", b"", provenance="test")
    generation = (state / ".checkpoint-generation").read_bytes()
    assert len(generation) == 32
    with pytest.raises(ResearchError):
        ingest_episode(
            state, ref.problem_id, "x.md", episode(ref), provenance="test", expected_sha256="0" * 64
        )
    after = snapshot(state)
    assert after.pop(".checkpoint-generation") != before.pop(".checkpoint-generation")
    assert after == before
    assert (state / ".checkpoint-generation").read_bytes() != generation


def test_utf8_bom_archive_preserves_exact_bytes(research):
    state, ref = research
    raw = b"\xef\xbb\xbf" + episode(ref)
    result = ingest_episode(state, ref.problem_id, "x.md", raw, provenance="test")
    from math_research.ledger.archive import source_path

    assert source_path(state, result["episode"]["archive_path"]).read_bytes() == raw
