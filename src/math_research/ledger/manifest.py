"""Unified read view over typed dossiers and additive ledgers, without ID migration."""

import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, computed_field

from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash, sha256
from math_research.core.refs import ObjectRef
from math_research.ledger.archive import source_path
from math_research.ledger.dependencies import Dependency, DependencyRole
from math_research.ledger.episodes import list_candidates, list_episodes, list_reviews
from math_research.ledger.persistence import records
from math_research.ledger.records import store
from math_research.ledger.records.experiments import list_experiments
from math_research.ledger.sources import source_papers
from math_research.ledger.state import KnowledgeStateResolver
from math_research.verification.formal.models import FormalBundle
from math_research.verification.models import VerificationReceipt
from math_research.verification.review import ReviewReport


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

    def objects(self, problem_id: str | None = None) -> list[ManifestEntry]:
        result: dict[str, ManifestEntry] = {}
        pending: list[tuple[ObjectRef, str, DependencyRole]] = []
        input_edges: list[Dependency] = []

        def add(kind, record, pid, states=None, *, ident=None, body=None, paths=()):
            data = record.model_dump(mode="json")
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
            semantic = {
                k: v
                for k, v in data.items()
                if k not in {"created_at", "updated_at", "imported_at"}
            }
            entry = ManifestEntry(
                ref=ref,
                content_hash=content_hash(
                    {"record": semantic, "body": body, "artifacts": artifacts}
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
            states = KnowledgeStateResolver(self.state).resolve(pid)
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
            for episode in episodes:
                path = source_path(self.state, episode.archive_path)
                add(
                    "episode",
                    episode,
                    pid,
                    body=path.read_text("utf-8") if path.is_file() else "",
                    paths=[path],
                )
            for paper in source_papers(self.state, pid):
                paths = []
                source_body = None
                if paper.local_path:
                    path = (self.state / paper.local_path).resolve()
                    if not path.is_relative_to(self.state):
                        raise ResearchError("Source escapes research state.")
                    paths = [path]
                    if path.is_file() and path.suffix.lower() in {".md", ".txt"}:
                        source_body = path.read_text("utf-8-sig")
                if paper.text_path:
                    text_path = (self.state / paper.text_path).resolve()
                    if not text_path.is_relative_to(self.state):
                        raise ResearchError("Extracted source text escapes research state.")
                    paths.append(text_path)
                    if text_path.is_file():
                        source_body = text_path.read_text("utf-8-sig")
                entry = add("source", paper, pid, body=source_body, paths=paths)
                if source_body is None:
                    entry.warnings.append(
                        "Source text is unavailable; inspect the original artifact"
                    )
                if paths and entry.artifact_refs[0]["sha256"] != paper.sha256:
                    entry.warnings.append("Pinned source SHA-256 mismatch")
            reviews = {r.candidate_id: r for r in list_reviews(self.state, pid)}
            for candidate in list_candidates(self.state, pid):
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
                if input_episode:
                    for pin in input_episode.input_versions:
                        if pin.ref.problem_id != pid:
                            continue
                        role = None
                        if (
                            pin.ref.object_id in candidate.uses
                            or pin.ref.qualified_id in candidate.uses
                        ):
                            role = (
                                DependencyRole.DEFINITION
                                if pin.ref.kind == "definition"
                                else DependencyRole.LOGICAL_PREMISE
                            )
                        if pin.ref.object_id == candidate.target_id and candidate.kind in {
                            "proof",
                            "refutation",
                        }:
                            role = DependencyRole.PROOF_TARGET
                        if role:
                            input_edges.append(
                                Dependency(
                                    dependent=entry.ref,
                                    target=pin.ref,
                                    role=role,
                                    expected_version=pin.version,
                                    provenance="episode_input",
                                )
                            )

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

        def resolve_local(source, target):
            if ":" in target:
                return ObjectRef.parse(target)
            matches = [
                e.ref
                for e in result.values()
                if e.ref.object_id == target and e.ref.problem_id == source.problem_id
            ]
            return (
                matches[0]
                if len(matches) == 1
                else ObjectRef(problem_id=source.problem_id, kind="unresolved", object_id=target)
            )

        edges = {}
        for source, target, role in pending:
            try:
                edge = Dependency(
                    dependent=source,
                    target=resolve_local(source, target),
                    role=role,
                    provenance="existing_record",
                )
                if edge.role == DependencyRole.LOGICAL_PREMISE and edge.target.kind == "definition":
                    edge = edge.model_copy(update={"role": DependencyRole.DEFINITION})
                edges[edge.key] = edge
            except ValueError:
                result[source.qualified_id].warnings.append(
                    f"Unresolved legacy reference: {target}"
                )
        for edge in [*input_edges, *records(self.state, "dependencies", Dependency)]:
            edges[edge.key] = edge
        for edge in edges.values():
            if edge.dependent.qualified_id in result:
                result[edge.dependent.qualified_id].dependencies.append(edge)
        return sorted(result.values(), key=lambda e: e.qualified_id)

    def get(self, ref: ObjectRef) -> ManifestEntry:
        match = next((e for e in self.objects(ref.problem_id) if e.ref == ref), None)
        if match is None:
            raise ResearchError(f"Unknown qualified object: {ref.qualified_id}")
        return match

    def resolve(self, object_id: str, *, problem_id=None, kind=None) -> ObjectRef:
        if ":" in object_id:
            ref = ObjectRef.parse(object_id)
            if problem_id and ref.problem_id != problem_id or kind and ref.kind != kind:
                raise ResearchError("Qualified reference conflicts with scope/kind.")
            return self.get(ref).ref
        found = [
            e.ref
            for e in self.objects(problem_id)
            if e.ref.object_id == object_id and (kind is None or e.ref.kind == kind)
        ]
        if len(found) != 1:
            raise ResearchError("Bare ID is absent or ambiguous; supply problem_id and kind.")
        return found[0]

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
        objects = [entries[key].model_dump(mode="json") for key in sorted(selected)]
        # Human history and pinned edges are part of an exported view, not object IDs.
        history = {}
        for name in ("dependencies", "verifications", "acceptance_requests", "acceptances"):
            path = self.state / "ledger" / (name + ".jsonl")
            history[name] = sha256(path.read_bytes()) if path.is_file() else None
        return content_hash({"objects": objects, "history": history})
