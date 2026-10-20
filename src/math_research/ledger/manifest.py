"""Unified read view over typed dossiers and additive ledgers, without ID migration."""

import json
from pathlib import Path

from pydantic import BaseModel, Field, computed_field

from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash, sha256
from math_research.core.refs import ObjectRef
from math_research.ledger.archive import source_path
from math_research.ledger.dependencies import Dependency, DependencyRole
from math_research.ledger.episodes import list_candidates, list_episodes
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

    @computed_field
    @property
    def qualified_id(self) -> str:
        return self.ref.qualified_id

    @computed_field
    @property
    def version(self) -> str:
        return content_hash({"content": self.content_hash, "dependencies": sorted((d.target.qualified_id, d.role.value, d.expected_version) for d in self.dependencies)})


class Ledger:
    def __init__(self, state: Path):
        self.state = state.resolve()

    def objects(self, problem_id: str | None = None) -> list[ManifestEntry]:
        result: dict[str, ManifestEntry] = {}
        pending: list[tuple[ObjectRef, str, DependencyRole]] = []

        def add(kind, record, pid, states=None, *, ident=None, body=None, paths=()):
            data = record.model_dump(mode="json")
            ref = ObjectRef(problem_id=pid, kind=kind, object_id=ident or data.get("id") or data.get("experiment_id") or data.get("episode_id"))
            state = (states or {}).get(ref.object_id)
            artifacts, warnings = [], []
            text = body if body is not None else json.dumps(data, ensure_ascii=False, sort_keys=True)
            for path in paths:
                try:
                    raw = path.read_bytes()
                    artifacts.append({"path": str(path), "sha256": sha256(raw)})
                except OSError:
                    artifacts.append({"path": str(path), "sha256": None})
                    warnings.append(f"Missing artifact: {path}")
            semantic = {k: v for k, v in data.items() if k not in {"created_at", "updated_at", "imported_at"}}
            entry = ManifestEntry(
                ref=ref,
                content_hash=content_hash({"record": semantic, "body": body, "artifacts": artifacts}),
                research_state=state.research_state if state else "CURRENT",
                authority=state.authority if state else "CANONICAL",
                verification=state.verification if state else "NOT_CHECKED",
                review=state.review if state else "ACCEPTED",
                provenance=list(dict.fromkeys([*data.get("source_artifacts", []), *(state.provenance if state else [])])),
                artifact_refs=artifacts, record=data, full_content=text,
                warnings=[*warnings, *(state.warnings if state else [])],
            )
            result[ref.qualified_id] = entry
            for dep in state.dependencies if state else data.get("depends_on", []):
                pending.append((ref, dep, DependencyRole.LOGICAL_PREMISE))
            for dep in data.get("source_artifacts", []):
                pending.append((ref, dep, DependencyRole.SOURCE_REFERENCE))
            for dep in data.get("claim_links", []):
                pending.append((ref, dep, DependencyRole.PROOF_TARGET))
            if kind == "evidence":
                pending.append((ref, data["claim_id"], DependencyRole.EVIDENCE))
            return entry

        for problem in store.list_dossiers(self.state):
            pid = problem.id
            if problem_id and pid != problem_id:
                continue
            states = KnowledgeStateResolver(self.state).resolve(pid)
            base = store.dossier_dir(self.state, pid)
            add("problem", problem, pid, body=store.read_statement(self.state, pid), paths=[base / "statement.md"])
            readers = (
                ("definition", store.list_definitions), ("assumption", store.list_assumptions),
                ("known_result", store.list_known_results), ("claim", store.list_claims),
                ("proof", store.list_proof_attempts), ("evidence", store.list_evidence),
                ("counterexample", store.list_counterexamples), ("failed_attempt", store.list_failed_attempts),
                ("approach", store.list_approaches), ("theorem_ref", store.list_theorem_refs),
                ("experiment", list_experiments),
            )
            for kind, reader in readers:
                for record in reader(self.state, pid):
                    actual = "gap" if getattr(record, "type", None) == "OPEN_GAP" else kind
                    body, paths = None, []
                    if getattr(record, "body_path", None):
                        path = (base / record.body_path).resolve()
                        if not path.is_relative_to(base.resolve()):
                            raise ResearchError("Record body escapes its Problem.")
                        paths = [path]
                        body = path.read_text("utf-8") if path.is_file() else ""
                    add(actual, record, pid, states, body=body, paths=paths)
            for episode in list_episodes(self.state, pid):
                path = source_path(self.state, episode.archive_path)
                add("episode", episode, pid, body=path.read_text("utf-8") if path.is_file() else "", paths=[path])
            for paper in source_papers(self.state, pid):
                paths = []
                if paper.local_path:
                    path = (self.state / paper.local_path).resolve()
                    if not path.is_relative_to(self.state):
                        raise ResearchError("Source escapes research state.")
                    paths = [path]
                entry = add("source", paper, pid, paths=paths)
                if paths and entry.artifact_refs[0]["sha256"] != paper.sha256:
                    entry.warnings.append("Pinned source SHA-256 mismatch")
            for candidate in list_candidates(self.state, pid):
                if candidate.kind == "relation":
                    continue
                state = states[candidate.candidate_id]
                # Accepted aliases retain their original provenance in canonical records.
                if state.canonical_id:
                    continue
                add(candidate.kind, candidate, pid, states, ident=candidate.object_id or candidate.candidate_id, body=candidate.body)

        for bundle in records(self.state, "formal_bundles", FormalBundle):
            if problem_id and bundle.problem_id != problem_id:
                continue
            root = Path(bundle.formal_repo).resolve()
            paths = []
            for name in [bundle.frozen.statement.path, *(s.path for s in bundle.frozen.local_definitions), *(s.path for s in bundle.frozen.dependencies), *bundle.proof_sources]:
                path = (root / name).resolve()
                if not path.is_relative_to(root):
                    raise ResearchError("Formal artifact escapes registered repository.")
                paths.append(path)
            entry = add("formal_bundle", bundle, bundle.problem_id, paths=paths)
            entry.authority, entry.review, entry.verification = "PROVISIONAL", "PENDING", "CHECKED" if bundle.status.value == "checked" else "NOT_CHECKED"
            if bundle.target:
                pending.append((entry.ref, bundle.target.qualified_id, DependencyRole.FORMAL_CORRESPONDENCE))
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
            matches = [e.ref for e in result.values() if e.ref.object_id == target and e.ref.problem_id == source.problem_id]
            return matches[0] if len(matches) == 1 else ObjectRef(problem_id=source.problem_id, kind="unresolved", object_id=target)

        edges = {}
        for source, target, role in pending:
            try:
                edge = Dependency(dependent=source, target=resolve_local(source, target), role=role, provenance="existing_record")
                edges[edge.key] = edge
            except ValueError:
                result[source.qualified_id].warnings.append(f"Unresolved legacy reference: {target}")
        for edge in records(self.state, "dependencies", Dependency):
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
        found = [e.ref for e in self.objects(problem_id) if e.ref.object_id == object_id and (kind is None or e.ref.kind == kind)]
        if len(found) != 1:
            raise ResearchError("Bare ID is absent or ambiguous; supply problem_id and kind.")
        return found[0]

    def source_version(self, problem_id=None) -> str:
        objects = [e.model_dump(mode="json") for e in self.objects(problem_id)]
        # Human history and pinned edges are part of an exported view, not object IDs.
        history = {}
        for name in ("dependencies", "verifications", "acceptance_requests", "acceptances"):
            path = self.state / "ledger" / (name + ".jsonl")
            history[name] = sha256(path.read_bytes()) if path.is_file() else None
        return content_hash({"objects": objects, "history": history})
