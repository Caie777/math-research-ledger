"""Unified read view over typed dossiers and additive ledgers, without ID migration."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, computed_field

from math_research.core.errors import IntegrityError, ResearchError
from math_research.core.hashing import content_hash, sha256
from math_research.core.refs import ObjectRef
from math_research.ledger.archive import episode_text, source_path
from math_research.ledger.dependencies import Dependency, DependencyRole
from math_research.ledger.episodes import (
    Proposal,
    ResearchEpisode,
    ReviewDecision,
    list_candidates,
    list_episodes,
    list_reviews,
)
from math_research.ledger.identity import IdentityResolution, ScopedIdentityResolver
from math_research.ledger.persistence import records
from math_research.ledger.records import store
from math_research.ledger.records.experiments import list_experiments
from math_research.ledger.sources import source_papers
from math_research.ledger.state import KnowledgeStateResolver
from math_research.verification.formal.models import FormalBundle
from math_research.verification.models import VerificationReceipt
from math_research.verification.review import ReviewReport


def record_content_hash(data: dict, body, artifacts: list[dict]) -> str:
    # Optional new proposal metadata must not change old content versions.
    semantic = {
        k: v
        for k, v in data.items()
        if k not in {"created_at", "updated_at", "imported_at"}
        and not (k == "dependency_pins" and not v)
    }
    return content_hash({"record": semantic, "body": body, "artifacts": artifacts})


class ManifestEntry(BaseModel):
    ref: ObjectRef
    content_hash: str
    research_state: str
    authority: str
    verification: str
    review: str
    provenance: list[str] = Field(default_factory=list)
    artifact_refs: list[dict] = Field(default_factory=list)
    dependencies: list[Dependency] = Field(default_factory=list)
    record: dict
    full_content: str
    warnings: list[str] = Field(default_factory=list)
    integrity: str = "NOT_APPLICABLE"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def qualified_id(self) -> str:
        return self.ref.qualified_id

    @computed_field  # type: ignore[prop-decorator]
    @property
    def version(self) -> str:
        return content_hash(
            {
                "content": self.content_hash,
                "dependencies": sorted(
                    (d.target.qualified_id, d.role.value, d.expected_version)
                    for d in self.dependencies
                ),
            }
        )


class Ledger:
    def __init__(self, state: Path):
        self.state = state.resolve()

    def _artifact_identity(self, artifact: dict) -> dict:
        """Bind workspace artifacts by portable location; external repo identity stays exact.

        Returned artifact_refs still hold resolved operational paths for readers.
        Historical strings inside domain records/provenance are never rewritten.
        """
        path = Path(artifact["path"])
        if path.is_relative_to(self.state):
            # Frozen v1 hash token, NOT an operational path. Changing it would
            # invalidate every historical version pin during a directory rename.
            return {**artifact, "path": ".math-research/" + path.relative_to(self.state).as_posix()}
        return artifact

    def _version_record(self, entry: ManifestEntry) -> dict:
        value = entry.model_dump(mode="json")
        value["artifact_refs"] = [self._artifact_identity(a) for a in entry.artifact_refs]
        missing = {
            f"Missing artifact: {a['path']}": "Missing artifact: "
            + self._artifact_identity(a)["path"]
            for a in entry.artifact_refs
            if a["sha256"] is None
        }
        value["warnings"] = [missing.get(warning, warning) for warning in entry.warnings]
        return value

    def objects(self, problem_id: str | None = None) -> list[ManifestEntry]:
        result: dict[str, ManifestEntry] = {}
        pending: list[tuple[ObjectRef, str, DependencyRole]] = []
        input_edges: list[Dependency] = []
        candidate_inputs: list[tuple[ManifestEntry, Proposal, ResearchEpisode | None]] = []
        all_candidates: list[Proposal] = []
        all_reviews: list[ReviewDecision] = []
        contexts: dict[str, set[str]] = {}

        def add(kind, record, pid, states=None, *, ident=None, body=None, paths=()):
            data = record.model_dump(mode="json")
            version_data = data
            if kind == "problem":
                version_data = {
                    k: v
                    for k, v in data.items()
                    if k
                    not in {
                        "lifecycle_status",
                        "summary",
                        "source_refs",
                        "metadata",
                        "closure_kind",
                        "closure_reason",
                        "resolution_refs",
                        "version_title",
                        "statement_authority",
                        "primary_target",
                    }
                }
                if record.version_title is not None:
                    version_data["title"] = record.version_title
                if record.primary_target:
                    version_data["primary_target"] = record.primary_target
            if "dependency_pins" in data and not data["dependency_pins"]:
                data.pop("dependency_pins")
            if kind == "episode":
                # New optional checkpoint fields must not change legacy versions.
                for key in ("state_delta", "next_research_directions"):
                    if not data.get(key):
                        data.pop(key, None)
            ref = ObjectRef(
                problem_id=pid,
                kind=kind,
                object_id=ident
                or data.get("id")
                or data.get("experiment_id")
                or data.get("episode_id"),
            )
            state = (states or {}).get(ref.object_id)
            artifacts, warnings = [], []
            text = (
                body if body is not None else json.dumps(data, ensure_ascii=False, sort_keys=True)
            )
            for path in paths:
                try:
                    raw = path.read_bytes()
                    artifacts.append({"path": str(path), "sha256": sha256(raw)})
                except OSError:
                    artifacts.append({"path": str(path), "sha256": None})
                    warnings.append(f"Missing artifact: {path}")
            entry = ManifestEntry(
                ref=ref,
                content_hash=record_content_hash(
                    version_data, body, [self._artifact_identity(a) for a in artifacts]
                ),
                research_state=state.research_state if state else "CURRENT",
                authority=state.authority if state else "CANONICAL",
                verification=state.verification if state else "NOT_CHECKED",
                review=state.review if state else "ACCEPTED",
                provenance=list(
                    dict.fromkeys(
                        [*data.get("source_artifacts", []), *(state.provenance if state else [])]
                    )
                ),
                artifact_refs=artifacts,
                record=data,
                full_content=text,
                warnings=[*warnings, *(state.warnings if state else [])],
            )
            result[ref.qualified_id] = entry
            if kind == "problem":
                entry.provenance.extend(data["source_refs"])
                if data["primary_target"]:
                    entry.full_content += "\n\n## Primary target\n\n" + data["primary_target"]
                if data["version_title"] is not None or data["statement_authority"]:
                    metadata = {
                        k: data[k]
                        for k in (
                            "title",
                            "lifecycle_status",
                            "summary",
                            "closure_kind",
                            "closure_reason",
                            "resolution_refs",
                            "source_refs",
                            "metadata",
                        )
                    }
                    entry.full_content += (
                        "\n\n## Project metadata (not mathematical authority)\n\n"
                        + json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                    )
                if data["statement_authority"] == "PROVISIONAL":
                    entry.authority, entry.review = "PROVISIONAL", "PENDING"
            for dep in state.dependencies if state else data.get("depends_on", []):
                pending.append((ref, dep, DependencyRole.LOGICAL_PREMISE))
            for dep in data.get("source_artifacts", []):
                pending.append((ref, dep, DependencyRole.SOURCE_REFERENCE))
            for dep in data.get("claim_links", []):
                pending.append((ref, dep, DependencyRole.PROOF_TARGET))
            if kind == "evidence" and data.get("claim_id"):
                pending.append((ref, data["claim_id"], DependencyRole.EVIDENCE))
            elif kind == "evidence" and data.get("target_id"):
                pending.append((ref, data["target_id"], DependencyRole.EVIDENCE))
            if kind in {"proof", "refutation"} and data.get("target_id"):
                pending.append((ref, data["target_id"], DependencyRole.PROOF_TARGET))
            if data.get("paper_artifact"):
                pending.append((ref, data["paper_artifact"], DependencyRole.SOURCE_REFERENCE))
            return entry

        for problem in store.list_dossiers(self.state):
            pid = problem.id
            if problem_id and pid != problem_id:
                continue
            states = KnowledgeStateResolver(self.state).resolve(pid, currentness=False)
            base = store.dossier_dir(self.state, pid)
            add(
                "problem",
                problem,
                pid,
                body=store.read_statement(self.state, pid),
                paths=[base / "statement.md"],
            )
            readers = (
                ("definition", store.list_definitions),
                ("assumption", store.list_assumptions),
                ("known_result", store.list_known_results),
                ("claim", store.list_claims),
                ("proof", store.list_proof_attempts),
                ("evidence", store.list_evidence),
                ("counterexample", store.list_counterexamples),
                ("failed_attempt", store.list_failed_attempts),
                ("approach", store.list_approaches),
                ("theorem_ref", store.list_theorem_refs),
                ("related_paper", store.list_related_papers),
                ("experiment", list_experiments),
            )
            for kind, reader in readers:
                for record in reader(self.state, pid):
                    actual = "gap" if getattr(record, "type", None) == "OPEN_GAP" else kind
                    body, paths = None, []
                    body_path = getattr(record, "body_path", None)
                    if body_path:
                        path = (base / body_path).resolve()
                        if not path.is_relative_to(base.resolve()):
                            raise ResearchError("Record body escapes its Problem.")
                        paths = [path]
                        body = path.read_text("utf-8") if path.is_file() else ""
                    add(actual, record, pid, states, body=body, paths=paths)
            episodes = list_episodes(self.state, pid)
            failed_episodes: set[str] = set()
            for episode in episodes:
                path = source_path(self.state, episode.archive_path)
                error: str | None
                try:
                    source_body = episode_text(self.state, episode)
                    error = None
                except IntegrityError as exc:
                    source_body, error = "", str(exc)
                    failed_episodes.add(episode.episode_id)
                entry = add(
                    "episode",
                    episode,
                    pid,
                    body=source_body,
                    paths=[path],
                )
                entry.integrity = "FAILED" if error else "VERIFIED"
                if error:
                    entry.warnings.append(error)
                    # Raw assertions are content, not harmless navigation metadata.
                    entry.record = {
                        k: entry.record[k]
                        for k in ("episode_id", "content_sha256", "archive_path", "problem_id")
                    }
            for paper in source_papers(self.state, pid):
                from math_research.core.integrity import verified_bytes

                paths = []
                paper_body: str | None = None
                error = None
                if paper.local_path:
                    path = (self.state / paper.local_path).resolve()
                    if not path.is_relative_to(self.state):
                        raise ResearchError("Source escapes research state.")
                    paths = [path]
                    if paper.sha256:
                        try:
                            raw = verified_bytes(path, paper.sha256, label=paper.id)
                            if path.suffix.lower() in {".md", ".txt"}:
                                paper_body = raw.decode("utf-8-sig")
                        except (IntegrityError, UnicodeError) as exc:
                            error = str(exc)
                entry = add("source", paper, pid, body=paper_body, paths=paths)
                entry.integrity = (
                    "FAILED"
                    if error
                    else "VERIFIED"
                    if paper.sha256 and paths
                    else "NOT_APPLICABLE"
                )
                if error:
                    entry.full_content = ""
                    entry.warnings.append("INTEGRITY_ERROR: " + error)
                elif paper_body is None:
                    entry.warnings.append(
                        "Source text unavailable: extracted caches have no immutable digest"
                    )
            reviews = {r.candidate_id: r for r in list_reviews(self.state, pid)}
            all_reviews.extend(reviews.values())
            for candidate in list_candidates(self.state, pid):
                all_candidates.append(candidate)
                if candidate.kind == "relation":
                    continue
                state = states[candidate.candidate_id]
                # Accepted aliases retain their original provenance in canonical records.
                if state.canonical_id:
                    entry = next(
                        (
                            e
                            for e in result.values()
                            if e.ref.object_id == state.canonical_id and e.ref.problem_id == pid
                        ),
                        None,
                    )
                    if entry is None:
                        continue
                    reviewed = reviews.get(candidate.candidate_id)
                    candidate = (
                        reviewed.reviewed_candidate
                        if reviewed and reviewed.reviewed_candidate
                        else candidate
                    )
                else:
                    entry = add(
                        candidate.kind,
                        candidate,
                        pid,
                        states,
                        ident=candidate.object_id or candidate.candidate_id,
                        body=candidate.body,
                    )
                input_episode = next(
                    (e for e in episodes if e.episode_id == candidate.episode_id), None
                )
                if input_episode is None or candidate.episode_id in failed_episodes:
                    entry.integrity = "FAILED"
                    entry.full_content = ""
                    entry.record = {
                        "id": entry.ref.object_id,
                        "episode_id": candidate.episode_id,
                        "candidate_id": candidate.candidate_id,
                    }
                    entry.warnings.append("INTEGRITY_ERROR: Episode provenance failed")
                contexts.setdefault(entry.qualified_id, set()).add(candidate.episode_id)
                candidate_inputs.append((entry, candidate, input_episode))

        for bundle in records(self.state, "formal_bundles", FormalBundle):
            if problem_id and bundle.problem_id != problem_id:
                continue
            root = Path(bundle.formal_repo).resolve()
            paths = []
            names = {
                bundle.frozen.statement.path,
                *(s.path for s in bundle.frozen.local_definitions),
                *(s.path for s in bundle.frozen.dependencies),
                *bundle.proof_sources,
            }
            for parent, dirs, files in os.walk(root, followlinks=False):
                dirs[:] = [d for d in dirs if d not in {".git", ".lake"}]
                names.update(
                    (Path(parent) / name).relative_to(root).as_posix()
                    for name in files
                    if name.endswith(".lean")
                )
            for name in sorted(names):
                path = (root / name).resolve()
                if not path.is_relative_to(root):
                    raise ResearchError("Formal artifact escapes registered repository.")
                paths.append(path)
            entry = add("formal_bundle", bundle, bundle.problem_id, paths=paths)
            expected = {
                source.path: source.sha256
                for source in (
                    bundle.frozen.statement,
                    *bundle.frozen.local_definitions,
                    *bundle.frozen.dependencies,
                )
            }
            for source in entry.artifact_refs:
                relative = Path(source["path"]).relative_to(root).as_posix()
                if relative in expected and source["sha256"] != expected[relative]:
                    entry.warnings.append("Pinned source SHA-256 mismatch: " + relative)
            entry.authority, entry.review, entry.verification = (
                "PROVISIONAL",
                "PENDING",
                "CHECKED" if bundle.status.value == "checked" else "NOT_CHECKED",
            )
            if bundle.target:
                pending.append(
                    (entry.ref, bundle.target.qualified_id, DependencyRole.FORMAL_CORRESPONDENCE)
                )
        # Old verifier submissions remain readable; they do not confer new human authority.
        from math_research.ledger.assets import load_asset_manifest
        from math_research.ledger.verification.proofs import list_proofs

        for proof in list_proofs(self.state):
            if problem_id and proof.problem_id != problem_id:
                continue
            entry = add("verification_proof", proof, proof.problem_id)
            entry.authority = "NONE"
            entry.verification = (
                "PASSED" if proof.accepted else "INCONCLUSIVE" if proof.inconclusive else "FAILED"
            )
            if proof.claim_id:
                pending.append((entry.ref, proof.claim_id, DependencyRole.PROOF_TARGET))
        for path in sorted((self.state / "research_runs").glob("*/assets.json")):
            manifest = load_asset_manifest(self.state, path.parent.name)
            if manifest is None or problem_id and manifest.problem_id != problem_id:
                continue
            assets = {}
            for artifact in manifest.assets:
                if artifact.retained:
                    entry = add(
                        "artifact",
                        artifact,
                        manifest.problem_id,
                        ident=artifact.asset_id,
                        paths=[path.parent / artifact.path],
                    )
                    entry.authority = "NONE"
                    assets[artifact.path] = entry
                    if entry.artifact_refs[0]["sha256"] != artifact.sha256:
                        entry.warnings.append("Pinned source SHA-256 mismatch: retained artifact")
            for artifact in manifest.assets:
                if artifact.path in assets:
                    for upstream in [artifact.related_script, *artifact.related_input]:
                        if upstream in assets:
                            pending.append(
                                (
                                    assets[artifact.path].ref,
                                    assets[upstream].qualified_id,
                                    DependencyRole.ARTIFACT_PROVENANCE,
                                )
                            )
            for owner, artifact_ids in manifest.object_assets.items():
                owners = [
                    e
                    for e in result.values()
                    if e.ref.object_id == owner and e.ref.problem_id == manifest.problem_id
                ]
                for artifact_entry in assets.values():
                    if artifact_entry.ref.object_id in artifact_ids:
                        for owner_entry in owners:
                            pending.append(
                                (
                                    owner_entry.ref,
                                    artifact_entry.qualified_id,
                                    DependencyRole.ARTIFACT_PROVENANCE,
                                )
                            )
        for report in records(self.state, "review_reports", ReviewReport):
            if not problem_id or report.target.ref.problem_id == problem_id:
                entry = add("review_report", report, report.target.ref.problem_id)
                entry.authority, entry.review = "ADVISORY", report.verdict.value
        for receipt in records(self.state, "verifications", VerificationReceipt):
            if not problem_id or receipt.target.ref.problem_id == problem_id:
                entry = add("verification", receipt, receipt.target.ref.problem_id)
                entry.authority, entry.verification = "NONE", receipt.outcome.status

        resolver = ScopedIdentityResolver(
            (e.ref for e in result.values()), all_candidates, all_reviews
        )

        def resolve_local(source, target):
            episodes = contexts.get(source.qualified_id, set())
            resolution = resolver.resolve(
                target,
                problem_id=source.problem_id,
                episode_id=next(iter(episodes)) if len(episodes) == 1 else None,
            )
            fallback = (
                ObjectRef.parse(target)
                if ":" in target
                else ObjectRef(problem_id=source.problem_id, kind="unresolved", object_id=target)
            )
            return resolution.ref or fallback, resolution.reason

        edges = {}
        for source, target, role in pending:
            try:
                target_ref, reason = resolve_local(source, target)
                edge = Dependency(
                    dependent=source,
                    target=target_ref,
                    role=role,
                    provenance="existing_record",
                    resolution_reason=reason,
                )
                if edge.role == DependencyRole.LOGICAL_PREMISE and edge.target.kind == "definition":
                    edge = edge.model_copy(update={"role": DependencyRole.DEFINITION})
                edges[edge.key] = edge
            except ValueError:
                result[source.qualified_id].warnings.append(
                    f"Unresolved legacy reference: {target}"
                )
                edge = Dependency(
                    dependent=source,
                    target=ObjectRef(
                        problem_id=source.problem_id,
                        kind="unresolved",
                        object_id=sha256(target.encode())[:24],
                    ),
                    role=role,
                    provenance="existing_record",
                    resolution_reason="MALFORMED_REFERENCE",
                )
                edges[edge.key] = edge
        from math_research.ledger.bindings import candidate_edges

        for entry, candidate, candidate_episode in candidate_inputs:
            input_edges.extend(
                candidate_edges(
                    candidate,
                    resolver,
                    dependent=entry.ref,
                    input_pins=candidate_episode.input_versions if candidate_episode else (),
                )
            )
        for edge in [*input_edges, *records(self.state, "dependencies", Dependency)]:
            source = resolver.resolve(edge.dependent.qualified_id).ref
            target_resolution = resolver.resolve(edge.target.qualified_id)
            edge = edge.model_copy(
                update={
                    "dependent": source or edge.dependent,
                    "target": target_resolution.ref or edge.target,
                    "resolution_reason": (edge.resolution_reason or target_resolution.reason)
                    if target_resolution.ref is None
                    else None,
                }
            )
            edges[edge.key] = edge
        for edge in edges.values():
            if edge.dependent.qualified_id in result:
                result[edge.dependent.qualified_id].dependencies.append(edge)
        return sorted(result.values(), key=lambda e: e.qualified_id)

    def get(self, ref: ObjectRef) -> ManifestEntry:
        entries = self.objects()
        resolved = self._identity(entries).resolve(ref.qualified_id).require()
        match = next((e for e in entries if e.ref == resolved), None)
        if match is None:
            raise ResearchError(f"Unknown qualified object: {ref.qualified_id}")
        if match.integrity == "FAILED":
            raise IntegrityError(f"Source unavailable for {ref.qualified_id}")
        return match

    def _identity(self, entries) -> ScopedIdentityResolver:
        candidates, reviews = [], []
        for problem in store.list_dossiers(self.state):
            candidates.extend(list_candidates(self.state, problem.id))
            reviews.extend(list_reviews(self.state, problem.id))
        return ScopedIdentityResolver((e.ref for e in entries), candidates, reviews)

    def explain(self, object_id: str, *, problem_id=None, episode_id=None) -> IdentityResolution:
        return self._identity(self.objects()).resolve(
            object_id, problem_id=problem_id, episode_id=episode_id
        )

    def resolve(self, object_id: str, *, problem_id=None, kind=None, episode_id=None) -> ObjectRef:
        if ":" in object_id:
            ref = ObjectRef.parse(object_id)
            if problem_id and ref.problem_id != problem_id or kind and ref.kind != kind:
                raise ResearchError("Qualified reference conflicts with scope/kind.")
        entries = [e for e in self.objects() if kind is None or e.ref.kind == kind]
        return (
            self._identity(entries)
            .resolve(object_id, problem_id=problem_id, episode_id=episode_id)
            .require()
        )

    def source_version(self, problem_id=None) -> str:
        entries = {e.qualified_id: e for e in self.objects()}
        selected = {
            key
            for key, entry in entries.items()
            if not problem_id or entry.ref.problem_id == problem_id
        }
        pending = list(selected)
        while pending:
            entry = entries[pending.pop()]
            for edge in entry.dependencies:
                key = edge.target.qualified_id
                if key in entries and key not in selected:
                    selected.add(key)
                    pending.append(key)
        objects = [self._version_record(entries[key]) for key in sorted(selected)]
        # Human history and pinned edges are part of an exported view, not object IDs.
        history = {}
        for name in ("dependencies", "verifications", "acceptance_requests", "acceptances"):
            path = self.state / "ledger" / (name + ".jsonl")
            history[name] = sha256(path.read_bytes()) if path.is_file() else None
        return content_hash({"objects": objects, "history": history})
