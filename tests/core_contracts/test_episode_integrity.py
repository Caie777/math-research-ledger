"""Episode preview and immutable-source regression contracts (synthetic only)."""

import hashlib
import json

import pytest
import yaml

from math_research.core.errors import ResearchError
from math_research.core.refs import ObjectRef
from math_research.ledger.archive import source_path
from math_research.ledger.projection import get_object
from math_research.ledger.readers import episode_source
from math_research.services.ingest import ingest_episode, preview_episode


def hashes(state):
    return {
        p.relative_to(state).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in state.rglob("*")
        if p.is_file()
    }


def publish(research, raw=None):
    state, ref = research
    return ingest_episode(
        state, ref.problem_id, "synthetic.md", raw or raw_episode(), provenance="synthetic contract"
    )


def preview(research, raw):
    state, ref = research
    return preview_episode(state, ref.problem_id, "synthetic.md", raw)


def codes(value):
    return {d["code"] for d in value["diagnostics"]}


def corrupt(research):
    result = publish(research)
    path = source_path(research[0], result["episode"]["archive_path"])
    path.write_bytes(path.read_bytes() + b"\nUNTRUSTED_TAMPER_MARKER\n")
    return result, path


def raw_episode(text="Synthetic complete statement."):
    return f"## RESULT-1\n\n**Statement**\n{text}\n".encode()


def test_generic_reader_must_detect_same_tamper_as_specialized_reader(research):
    state, ref = research
    result = ingest_episode(state, ref.problem_id, "s.md", raw_episode(), provenance="test")
    episode = result["episode"]
    path = source_path(state, episode["archive_path"])
    path.write_bytes(path.read_bytes() + b"\nUNTRUSTED_TAMPER_MARKER\n")
    with pytest.raises(ResearchError):
        episode_source(state, ref.problem_id, episode["episode_id"])
    with pytest.raises(ResearchError, match="INTEGRITY_ERROR"):
        get_object(
            state,
            ObjectRef(problem_id=ref.problem_id, kind="episode", object_id=episode["episode_id"]),
        )


def test_duplicate_id_is_structured_error(research):
    state, ref = research
    result = preview_episode(state, ref.problem_id, "s.md", raw_episode() + raw_episode("Other"))
    assert any(
        d["code"] == "DUPLICATE_LOCAL_ID" and d["severity"] == "ERROR"
        for d in result["diagnostics"]
    )


def test_distinct_targets_are_not_first_match(research):
    state, ref = research
    raw = (
        f"## PROOF-1\n\n**Target**\n{ref.object_id}, CLAIM-9999\n\n**Proof**\nArgument.\n".encode()
    )
    result = preview_episode(state, ref.problem_id, "s.md", raw)
    assert any(d["code"] == "AMBIGUOUS_TARGET" for d in result["diagnostics"])


@pytest.mark.parametrize(
    "raw,format",
    [
        (raw_episode(), "numbered"),
        ("## RESULT-1\n\n**陈述**\n完整的合成陈述。\n".encode(), "numbered"),
        (b"## Claim: Legacy\n\nA legacy synthetic statement.\n", "legacy"),
    ],
)
def test_valid_numbered_and_legacy_preserve_bytes(research, raw, format):
    value = preview(research, raw)
    assert value["can_publish"]
    assert value["detected_format"] == format
    assert not [d for d in value["diagnostics"] if d["severity"] == "ERROR"]
    result = publish(research, raw)
    assert source_path(research[0], result["episode"]["archive_path"]).read_bytes() == raw


def test_duplicate_blocks_structured_publication_but_explicit_raw_only_is_safe(research):
    state, ref = research
    raw = raw_episode() + raw_episode("Other content")
    before = hashes(state)
    with pytest.raises(ResearchError, match="DUPLICATE_LOCAL_ID"):
        publish(research, raw)
    after = hashes(state)
    # A write attempt advances its coordination epoch, even on rollback. No
    # research record changes; pure preview tests still compare every state byte.
    assert set(after) - set(before) == {".checkpoint-generation"}
    assert all(after[p] == h for p, h in before.items())
    assert len((state / ".checkpoint-generation").read_bytes()) == 32
    result = ingest_episode(
        state, ref.problem_id, "raw.md", raw, provenance="test", archive_only=True
    )
    assert not result["structured_published"]
    assert not result["candidates"]
    assert not result["episode"]["state_delta"]
    assert source_path(state, result["episode"]["archive_path"]).read_bytes() == raw


@pytest.mark.parametrize("repeated", [False, True])
def test_equivalent_target_aliases_are_normalized(research, repeated):
    _, ref = research
    label = "Target" if repeated else "目标"
    raw = (
        f"## PROOF-1\n\n**Target**\n{ref.object_id}\n\n**{label}**\n{ref.qualified_id}"
        "\n\n**Proof**\nA complete synthetic argument.\n"
    ).encode()
    value = preview(research, raw)
    assert value["can_publish"]
    assert "AMBIGUOUS_TARGET" not in codes(value)
    candidate = next(c for c in value["candidates"] if c.kind == "proof")
    assert candidate.target_id == ref.qualified_id
    publish(research, raw)


def test_unknown_uses_is_explicit_and_remains_unbound(research):
    raw = raw_episode() + b"\n**Uses**\nRESULT-999\n"
    value = preview(research, raw)
    assert value["can_publish"]
    assert "MISSING_LOCAL_OBJECT" in codes(value)
    assert value["bindings"][0]["resolved_ref"] is None
    result = publish(research, raw)
    from math_research.ledger.manifest import Ledger

    candidate = result["candidates"][0]
    entry = next(
        e for e in Ledger(research[0]).objects() if e.ref.object_id == candidate["object_id"]
    )
    assert entry.dependencies[0].resolution_reason == "MISSING_LOCAL_OBJECT"
    assert entry.dependencies[0].expected_version is None


def test_scope_ambiguity_does_not_guess_kind(research):
    from math_research.ledger.records import store
    from math_research.ledger.records.models import ProofAttempt

    state, ref = research
    store.append_proof_attempt(state, ProofAttempt(id=ref.object_id, problem_id=ref.problem_id))
    value = preview(research, raw_episode() + f"\n**Uses**\n{ref.object_id}\n".encode())
    assert not value["can_publish"]
    assert "SCOPE_AMBIGUITY" in codes(value)


def test_cross_problem_bare_reference_never_borrows_other_scope(research):
    from math_research.services.research import create_problem

    state, ref = research
    other = create_problem(state, "Other scope", "Synthetic")
    raw = raw_episode() + f"\n**Uses**\n{ref.object_id}\n".encode()
    value = preview_episode(state, other.id, "cross.md", raw)
    assert value["bindings"][0]["resolved_ref"] is None
    explicit = raw.replace(ref.object_id.encode(), ref.qualified_id.encode())
    value = preview_episode(state, other.id, "cross.md", explicit)
    assert value["bindings"][0]["resolved_ref"] == ref.qualified_id


@pytest.mark.parametrize("kind", ["REVISION", "REFUTATION", "PROOF"])
def test_required_target_is_actionable_error(research, kind):
    raw = f"## {kind}-1\n\nA complete synthetic argument.\n".encode()
    value = preview(research, raw)
    assert not value["can_publish"]
    diagnostic = next(d for d in value["diagnostics"] if d["code"] == "MISSING_TARGET")
    assert diagnostic["start_line"] == 1
    assert diagnostic["related_refs"] == []
    assert diagnostic["remediation"]


@pytest.mark.parametrize("action", ["Revised", "Refuted", "Invalidated"])
def test_delta_assertions_cannot_mutate_canonical_or_receipts(research, action):
    state, ref = research
    before = {p: h for p, h in hashes(state).items() if not p.startswith("research_archive/")}
    raw = (
        "---\n"
        + yaml.safe_dump(
            {
                "state_delta": [
                    {
                        "action": action,
                        "reference": ref.qualified_id,
                        "statement": "A source assertion only",
                    }
                ]
            }
        )
        + "---\n"
    ).encode()
    value = preview(research, raw)
    assert value["can_publish"] and "MISSING_INPUT_VERSION" in codes(value)
    publish(research, raw)
    after = hashes(state)
    assert all(after[p] == h for p, h in before.items())
    assert get_object(state, ref).object.research_state == "CURRENT"
    assert not list((state / "ledger").glob("*accept*"))


def test_chinese_revision_old_object_is_a_real_target(research):
    _, ref = research
    raw = f"## REVISION-1\n\n**旧对象**\n{ref.object_id}\n\n**修正后的内容**\n合成修正。\n".encode()
    value = preview(research, raw)
    assert value["can_publish"]
    assert value["bindings"][0]["resolved_ref"] == ref.qualified_id


@pytest.mark.parametrize("header", ["Next Research Directions", "Current Research Handoff"])
def test_advisory_only_has_no_delta_or_dependencies(research, header):
    raw = f"# {header}\n\n## RESULT-1\n\nTry something later.\n\n**Uses**\nCLAIM-0001\n".encode()
    value = preview(research, raw)
    assert value["confirmed_research_increments"] == 0
    assert "ADVISORY_ONLY" in codes(value)
    assert not value["candidates"] and not value["metadata"].state_delta
    assert not value["metadata"].explicit_dependencies
    assert not publish(research, raw)["candidates"]


def test_unstructured_prose_can_be_saved_without_manufacturing_claims(research):
    raw = "# 自由探索\n\nSome tentative reasoning, with no declared object.\n".encode()
    assert preview(research, raw)["can_publish"]
    assert not publish(research, raw)["candidates"]


def test_same_episode_binding_preview_and_duplicate_ingest(research):
    from math_research.ledger.manifest import Ledger

    raw = raw_episode() + b"\n## RESULT-2\n\n**Statement**\nDependent.\n\n**Uses**\nRESULT-1\n"
    value = preview(research, raw)
    assert any(b["version_status"] == "AUTHORED_SNAPSHOT" for b in value["bindings"])
    result = publish(research, raw)
    before = hashes(research[0])
    repeated = publish(research, raw)
    assert repeated["duplicate"]
    after = hashes(research[0])
    assert after.keys() == before.keys()
    assert after[".checkpoint-generation"] != before[".checkpoint-generation"]
    assert all(after[p] == h for p, h in before.items() if p != ".checkpoint-generation")
    candidates = [c for c in result["candidates"] if c["kind"] == "claim"]
    downstream = ObjectRef(
        problem_id=research[1].problem_id, kind="claim", object_id=candidates[1]["object_id"]
    )
    assert Ledger(research[0]).get(downstream).dependencies[0].expected_version


@pytest.mark.parametrize("version_mode", ["missing", "valid", "stale"])
def test_authored_input_versions_are_diagnosed_without_fabrication(research, version_mode):
    from math_research.ledger.manifest import Ledger

    state, ref = research
    data = (
        {}
        if version_mode == "missing"
        else {
            "input_versions": [
                {
                    "ref": ref.model_dump(),
                    "version": Ledger(state).get(ref).version
                    if version_mode == "valid"
                    else "a" * 64,
                }
            ]
        }
    )
    raw = (
        ("---\n" + yaml.safe_dump(data) + "---\n").encode()
        + raw_episode()
        + f"\n**Uses**\n{ref.qualified_id}\n".encode()
    )
    before = hashes(state)
    value = preview(research, raw)
    assert hashes(state) == before
    assert value["can_publish"]
    assert (
        value["bindings"][0]["version_status"]
        == {"missing": "MISSING", "valid": "MATCHING", "stale": "STALE"}[version_mode]
    )
    assert len(value["metadata"].input_versions) == (version_mode != "missing")


def test_mcp_preview_is_read_only_and_tool_count_stays_nine(research):
    from math_research.mcp.adapter import SCHEMAS, LedgerAdapter

    state, ref = research
    before = hashes(state)
    result = LedgerAdapter(state).call(
        "research_ingest_episode",
        {
            "problem_id": ref.problem_id,
            "markdown": raw_episode().decode(),
            "provenance": "test",
            "dry_run": True,
        },
    )
    assert result["can_publish"] and result["local_ids"] == ["RESULT-1"]
    assert hashes(state) == before
    assert len(SCHEMAS) == 9


@pytest.mark.parametrize("route", ["specialized", "span", "generic", "manifest", "extraction"])
def test_exact_content_paths_fail_closed_on_identical_tamper(research, route):
    from math_research.ledger.archive import _verified_bytes
    from math_research.ledger.episodes import extract_candidates, list_episodes
    from math_research.ledger.manifest import Ledger
    from math_research.ledger.readers import episode_span

    state, ref = research
    result, _ = corrupt(research)
    episode = list_episodes(state)[0]
    target = ObjectRef(problem_id=ref.problem_id, kind="episode", object_id=episode.episode_id)
    calls = {
        "specialized": lambda: episode_source(state, ref.problem_id, episode.episode_id),
        "span": lambda: episode_span(state, ref.problem_id, episode.episode_id, 1, 2),
        "generic": lambda: get_object(state, target),
        "manifest": lambda: Ledger(state).get(target),
        "extraction": lambda: extract_candidates(state, episode),
    }
    before = hashes(state)
    with pytest.raises(ResearchError, match="INTEGRITY_ERROR"):
        calls[route]()
    with pytest.raises(ResearchError, match="INTEGRITY_ERROR"):
        _verified_bytes(state, episode)
    assert (
        hashes(state) == before
        and result["episode"]["content_sha256"]
        != hashlib.sha256(source_path(state, episode.archive_path).read_bytes()).hexdigest()
    )


def test_navigation_search_and_context_exclude_corrupt_source_and_derived_body(research):
    from math_research.ledger.projection import list_objects
    from math_research.retrieval.index import gather_documents
    from math_research.services.retrieval import export_context_packet, search_research

    state, ref = research
    result, _ = corrupt(research)
    before = hashes(state)
    failed = [v for v in list_objects(state) if v.object.integrity == "FAILED"]
    assert len(failed) == 2  # Episode and its stored proposal snapshot.
    assert all(
        v.freshness == "STALE" and not v.usable_working_premise and not v.object.full_content
        for v in failed
    )
    docs = gather_documents(state, problem_id=ref.problem_id)
    assert any(d.integrity == "FAILED" for d in docs)
    assert "UNTRUSTED_TAMPER_MARKER" not in json.dumps([d.model_dump() for d in docs])
    hits = search_research(state, "UNTRUSTED_TAMPER_MARKER")
    assert "UNTRUSTED_TAMPER_MARKER" not in json.dumps(hits)
    episode = result["episode"]
    target = ObjectRef(problem_id=ref.problem_id, kind="episode", object_id=episode["episode_id"])
    packet = export_context_packet(state, target)
    assert not packet.complete and target.qualified_id in packet.required_omitted_ids
    assert any(e["integrity"] == "FAILED" for e in packet.excluded)
    assert not any(i.ref == target for i in packet.items)
    assert "UNTRUSTED_TAMPER_MARKER" not in packet.model_dump_json()
    assert hashes(state) == before


@pytest.mark.parametrize("damage", [b"{bad json}\n", b'{"id": 5}\n', b"\xff\n"])
def test_authoritative_jsonl_cannot_silently_skip_damage(research, damage):
    from math_research.ledger.records import store

    state, ref = research
    path = state / "problems" / ref.problem_id / "claims.jsonl"
    path.write_bytes(path.read_bytes() + damage)
    before = hashes(state)
    with pytest.raises(ResearchError, match="INTEGRITY_ERROR"):
        store.list_claims(state, ref.problem_id)
    assert hashes(state) == before


def test_duplicate_body_fields_and_empty_objects_are_errors(research):
    assert "DUPLICATE_FIELD" in codes(
        preview(research, raw_episode() + b"\n**Statement**\nOther\n")
    )
    assert "MISSING_CONTENT" in codes(preview(research, b"## RESULT-1\n"))


def test_source_tamper_and_unpinned_extracted_text_cannot_bypass_generic_reader(research):
    from math_research.ledger.manifest import Ledger
    from math_research.ledger.sources import read_source, save_source, validate_source

    state, ref = research
    paper = save_source(
        state, ref.problem_id, validate_source("fixture.md", b"Pinned source text.")
    )
    target = ObjectRef(problem_id=ref.problem_id, kind="source", object_id=paper.id)
    assert Ledger(state).get(target).full_content == "Pinned source text."
    path = state / paper.local_path
    path.write_bytes(b"UNTRUSTED_TAMPER_MARKER")
    with pytest.raises(ResearchError, match="INTEGRITY_ERROR"):
        get_object(state, target)
    with pytest.raises(ResearchError, match="INTEGRITY_ERROR"):
        read_source(state, ref.problem_id, paper.id)


def test_tamper_never_rewrites_existing_verification_or_authority_receipts(research):
    from math_research.services.acceptance import accept, request_acceptance
    from math_research.services.ingest import review_proposal
    from math_research.services.verification import ExactVerificationService
    from math_research.verification.models import CheckOutcome, ExactCertificate

    class Checker:
        def check(self, certificate):
            return CheckOutcome(status="PASSED", summary="Synthetic fixture only")

    state, ref = research
    result = publish(research)
    candidate = result["candidates"][0]
    review = review_proposal(state, ref.problem_id, candidate["candidate_id"], "accept")
    target = ObjectRef(problem_id=ref.problem_id, kind="claim", object_id=review.mapped_id)
    from math_research.ledger.dependencies import DependencyRole
    from math_research.services.research import link_dependency

    link_dependency(
        state,
        target,
        ObjectRef(
            problem_id=ref.problem_id, kind="episode", object_id=result["episode"]["episode_id"]
        ),
        DependencyRole.SOURCE_REFERENCE,
    )
    receipt = ExactVerificationService({"fixture": Checker()}).verify(
        state, target, ExactCertificate(checker="fixture", inputs={}, scope="synthetic only")
    )
    pending = request_acceptance(state, target, receipt.id)
    accept(state, pending.id, actor="synthetic human fixture", rationale="synthetic receipt test")
    history = {p: p.read_bytes() for p in (state / "ledger").glob("*.jsonl")}
    path = source_path(state, result["episode"]["archive_path"])
    path.write_bytes(path.read_bytes() + b"tampered")
    with pytest.raises(ResearchError, match="INTEGRITY_ERROR"):
        get_object(state, target)
    from math_research.ledger.projection import list_objects

    view = next(v for v in list_objects(state) if v.object.ref == target)
    assert not view.usable_working_premise and not view.trusted_formal_premise
    assert all(p.read_bytes() == data for p, data in history.items())


def test_legacy_repeated_distinct_targets_are_errors(research):
    _, ref = research
    raw = (f"## Proof: legacy\nTarget: {ref.object_id}\nTarget: CLAIM-9999\n\nArgument.\n").encode()
    assert "AMBIGUOUS_TARGET" in codes(preview(research, raw))


def test_malformed_frontmatter_can_be_archived_only_by_explicit_choice(research):
    raw = b"---\n[bad yaml\n---\n## Claim: preserve raw\n\nBody.\n"
    value = preview(research, raw)
    assert not value["can_publish"] and "INVALID_STRUCTURE" in codes(value)
    state, ref = research
    result = ingest_episode(
        state, ref.problem_id, "raw.md", raw, provenance="test", archive_only=True
    )
    assert not result["candidates"] and not result["episode"]["state_delta"]


def test_span_checks_bounds_after_verifying_whole_file(research):
    from math_research.ledger.readers import episode_span

    result = publish(research)
    state, ref = research
    eid = result["episode"]["episode_id"]
    assert episode_span(state, ref.problem_id, eid, 1, 1) == "## RESULT-1"
    with pytest.raises(ResearchError, match="span"):
        episode_span(state, ref.problem_id, eid, 0, 200)


def test_recall_original_download_is_gated_by_the_same_digest(research):
    from math_research.retrieval.recall import ResearchRecall

    state, ref = research
    result, _ = corrupt(research)
    for kind, ident in [
        ("dossier:episode", result["episode"]["episode_id"]),
        ("dossier:provisional", result["candidates"][0]["object_id"]),
    ]:
        with pytest.raises(ResearchError, match="INTEGRITY_ERROR"):
            ResearchRecall(state, ref.problem_id).read_original_file(ident, kind)


def test_unscoped_episode_search_navigation_has_integrity_status(research):
    from datetime import UTC, datetime

    from math_research.ledger.archive import archive_source
    from math_research.retrieval.index import gather_documents

    state, _ = research
    episode = archive_source(
        state,
        None,
        "global.md",
        raw_episode(),
        datetime.now(UTC),
        related_problem_ids=[],
        thread_ids=[],
        provenance="test",
        source_language=None,
    )
    path = source_path(state, episode.archive_path)
    path.write_bytes(path.read_bytes() + b"UNTRUSTED_TAMPER_MARKER")
    doc = next(d for d in gather_documents(state) if d.artifact_id == episode.episode_id)
    assert doc.integrity == "FAILED" and "UNTRUSTED_TAMPER_MARKER" not in doc.model_dump_json()


def test_corrupt_authoritative_row_blocks_read_modify_write(research):
    from math_research.core.jsonl import update_jsonl
    from math_research.ledger.records.models import ClaimRecord

    state, ref = research
    path = state / "problems" / ref.problem_id / "claims.jsonl"
    path.write_bytes(path.read_bytes() + b"broken\n")
    before = path.read_bytes()
    called = []
    with pytest.raises(ResearchError, match="INTEGRITY_ERROR"):
        update_jsonl(path, ClaimRecord, lambda rows: called.append(True))
    assert not called and path.read_bytes() == before


def test_cached_search_content_cannot_bypass_live_source_integrity(research):
    from math_research.retrieval.index import build_index, load_documents, search

    state, _ = research
    result = publish(research)
    build_index(state)
    cache = state / "index/docs.jsonl"
    rows = [json.loads(line) for line in cache.read_text("utf-8").splitlines()]
    for row in rows:
        if row["artifact_type"] in {"dossier:episode", "dossier:provisional"}:
            row["text"] = "UNTRUSTED_CACHE_MARKER"
    cache.write_text("".join(json.dumps(row) + "\n" for row in rows), "utf-8")
    path = source_path(state, result["episode"]["archive_path"])
    path.write_bytes(path.read_bytes() + b"tampered")
    docs = load_documents(state)
    assert any(d.integrity == "FAILED" for d in docs)
    assert "UNTRUSTED_CACHE_MARKER" not in json.dumps([d.model_dump() for d in docs])
    assert not search(state, "UNTRUSTED_CACHE_MARKER")


@pytest.mark.parametrize("raw", [raw_episode(), b"## Claim: legacy\n\nComplete statement.\n"])
def test_absent_uses_field_does_not_manufacture_unresolved_warning(research, raw):
    value = preview(research, raw)
    assert "UNRESOLVED_USES" not in codes(value)
    assert not value["diagnostics"]
