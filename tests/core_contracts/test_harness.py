import yaml

from math_research.core.refs import ObjectRef
from math_research.ledger.episodes import list_candidates
from math_research.ledger.manifest import Ledger
from math_research.services.ingest import ingest_episode, ingest_source_file, review_proposal
from math_research.services.research import add_definition, get_object, update_definition


def test_harness_input_versions_survive_canonicalization_and_detect_old_work(research):
    state, target = research
    definition = add_definition(state, target.problem_id, "D", "definition v1")
    dr = ObjectRef(problem_id=target.problem_id, kind="definition", object_id=definition.id)
    metadata = {
        "target_claim_id": target.object_id,
        "input_versions": [{"ref": dr.model_dump(), "version": Ledger(state).get(dr).version}],
    }
    raw = (
        "---\n"
        + yaml.safe_dump(metadata)
        + "---\n\n## Proof: complete external argument\nTarget: "
        + target.object_id
        + "\nUses: "
        + definition.id
        + "\n\nComplete proof under the input definition.\n"
    ).encode()
    update_definition(
        state, target.problem_id, definition.model_copy(update={"definition": "definition v2"})
    )
    ingest_episode(
        state, target.problem_id, "external.md", raw, provenance="synthetic harness input packet"
    )
    proof = next(c for c in list_candidates(state, target.problem_id) if c.kind == "proof")
    provisional = ObjectRef(problem_id=target.problem_id, kind="proof", object_id=proof.object_id)
    assert get_object(state, provisional).freshness == "STALE"
    reviewed = review_proposal(state, target.problem_id, proof.candidate_id, "accept")
    canonical = ObjectRef(problem_id=target.problem_id, kind="proof", object_id=reviewed.mapped_id)
    assert get_object(state, canonical).freshness == "STALE"
    assert (
        Ledger(state)
        .get(canonical)
        .full_content.endswith("Complete proof under the input definition.\n")
    )


def test_source_ingestion_is_pinned_and_idempotent(research, tmp_path):
    state, target = research
    source = tmp_path / "synthetic-source.txt"
    source.write_text("Synthetic source content, not a theorem acceptance.", encoding="utf-8")
    first = ingest_source_file(state, target.problem_id, source)
    second = ingest_source_file(state, target.problem_id, source)
    assert first.id == second.id
    entry = Ledger(state).get(
        ObjectRef(problem_id=target.problem_id, kind="source", object_id=first.id)
    )
    assert entry.artifact_refs[0]["sha256"] == first.sha256
    assert entry.full_content == source.read_text("utf-8")
