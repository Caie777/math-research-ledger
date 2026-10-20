"""Fixed verifier services; harnesses supply outputs, never authority flags."""

import os
from pathlib import Path
from typing import Protocol

from math_research.core.errors import ResearchError
from math_research.core.hashing import content_hash, sha256
from math_research.core.refs import ObjectRef
from math_research.ledger.manifest import Ledger
from math_research.ledger.dependencies import Dependency, DependencyRole
from math_research.ledger.persistence import append_once, records
from math_research.verification.formal import FormalBundle, LeanChecker, freeze
from math_research.verification.formal.freeze import source_path
from math_research.verification.freshness import Freshness, FreshnessResolver
from math_research.verification.models import ArtifactRef, CheckOutcome, ExactCertificate, ValidatedComputation, VerificationKind, VerificationReceipt, VersionPin


class ExactChecker(Protocol):
    """Registered local implementation. No arbitrary code/import/shell from certificates."""

    def check(self, certificate: ExactCertificate) -> CheckOutcome: ...


def get_receipt(state: Path, ident: str) -> VerificationReceipt:
    receipt = next((r for r in records(state, "verifications", VerificationReceipt) if r.id == ident), None)
    if receipt is None:
        raise ResearchError("Verification receipt not found.")
    return receipt


def run_formal_check(state: Path, ref: ObjectRef, *, lake: Path, elan_home: Path):
    return check_formalization(state, ref, LeanChecker(lake, elan_home=elan_home))


def _artifacts_current(artifacts: tuple[ArtifactRef, ...]) -> bool:
    try:
        return all(sha256(Path(a.path).read_bytes()) == a.sha256 for a in artifacts)
    except OSError:
        return False


def receipt_current(state: Path, receipt: VerificationReceipt, entries=None) -> bool:
    resolver = FreshnessResolver(entries if entries is not None else Ledger(state).objects())
    return resolver.check_pins((receipt.target, *receipt.dependencies)).freshness == Freshness.CURRENT and _artifacts_current(receipt.artifacts)


def _record(state, target, kind, checker, outcome, artifacts=()):
    ledger = Ledger(state)
    resolver = FreshnessResolver(ledger.objects())
    pins = resolver.pins(target)
    pin = next(p for p in pins if p.ref == target)
    identity = content_hash({"pins": [p.model_dump(mode="json") for p in pins], "kind": kind, "checker": checker, "outcome": outcome.model_dump(mode="json"), "artifacts": [a.model_dump(mode="json") for a in artifacts]})
    ident = "VERIFY-" + identity[:24]
    old = next((r for r in records(state, "verifications", VerificationReceipt) if r.id == ident), None)
    if old:
        return old
    receipt = VerificationReceipt(id=ident, kind=kind, target=pin, checker=checker, outcome=outcome, dependencies=tuple(p for p in pins if p.ref != target), artifacts=tuple(artifacts))
    return append_once(state, "verifications", receipt, key="id")


class ExactVerificationService:
    def __init__(self, checkers: dict[str, ExactChecker]):
        self.checkers = dict(checkers)

    def verify(self, state: Path, target: ObjectRef, certificate: ExactCertificate) -> VerificationReceipt:
        checker = self.checkers.get(certificate.checker)
        if checker is None:
            raise ResearchError("Exact checker is not registered locally.")
        ledger = Ledger(state)
        before = ledger.source_version(target.problem_id)
        artifacts = (*certificate.scripts, *certificate.outputs)
        if not _artifacts_current(artifacts):
            raise ResearchError("Certificate artifact changed or unavailable.")
        outcome = checker.check(certificate)
        if ledger.source_version(target.problem_id) != before or not _artifacts_current(artifacts):
            raise ResearchError("Verification input changed during checking.")
        outcome = outcome.model_copy(update={"details": {**outcome.details, "certificate": certificate.model_dump(mode="json")}})
        kind = VerificationKind.VALIDATED_COMPUTATION if isinstance(certificate, ValidatedComputation) else VerificationKind.EXACT
        return _record(state, target, kind, certificate.checker, outcome, artifacts)


def freeze_statement(state: Path, target: ObjectRef, *, ident: str, repo: Path, statement: str, module: str, declaration: str, expected_type: str, local_definitions: tuple[str, ...] = (), version: int = 1, reason: str | None = None) -> FormalBundle:
    from math_research.verification.formal.checker import validate_name

    ref = ObjectRef(problem_id=target.problem_id, kind="formal_bundle", object_id=ident)
    ledger = Ledger(state)
    if target.kind not in {"claim", "gap"}:
        raise ResearchError("Formalization must target a qualified Claim/Gap.")
    ledger.get(target)
    validate_name(module)
    validate_name(declaration)
    base = state.resolve() / "ledger" / "formal" / ref.object_id
    if base.resolve() != base:
        raise ResearchError("Formal storage must not redirect.")
    frozen = freeze(repo, statement, local_definitions, base / "freezes", version=version, reason=reason)
    bundle = FormalBundle(id=ident, problem_id=target.problem_id, target=target, formal_repo=str(repo.resolve()), formal_repo_commit=_git_head(repo), module=module, declaration=declaration, expected_type=expected_type, frozen=frozen)
    append_once(state, "formal_bundles", bundle)
    # Working output can be produced by a harness; only the pinned link is recorded here.
    edge = Dependency(dependent=ref, target=target, role=DependencyRole.FORMAL_CORRESPONDENCE, expected_version=ledger.get(target).version)
    append_once(state, "dependencies", edge)
    return bundle


def _git_head(repo: Path) -> str:
    from math_research.core.process import run_process, hidden_process_kwargs

    result = run_process(["git", "--no-optional-locks", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=5, **hidden_process_kwargs())
    if result.returncode != 0:
        raise ResearchError("Formal repository requires a readable committed HEAD.")
    return result.stdout.strip()


def _proof_hashes(repo: Path) -> dict[str, str]:
    result = {}
    root = repo.resolve()
    for parent, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in {".git", ".lake"}]
        for name in sorted(files):
            if name.endswith(".lean"):
                path = Path(parent) / name
                relative = path.relative_to(root).as_posix()
                result[relative] = sha256(source_path(root, relative).read_bytes())
    return result


def check_formalization(state: Path, ref: ObjectRef, checker: LeanChecker) -> VerificationReceipt:
    from uuid import uuid4

    ledger = Ledger(state)
    entry = ledger.get(ref)
    if ref.kind != "formal_bundle":
        raise ResearchError("Expected formal_bundle reference.")
    bundle = FormalBundle.model_validate(entry.record)
    for old in reversed(records(state, "verifications", VerificationReceipt)):
        if old.target.ref == ref and old.outcome.status == "PASSED" and receipt_current(state, old):
            return old
    if not bundle.module or not bundle.expected_type:
        raise ResearchError("Exact module/declaration/type contract is required.")
    before = ledger.source_version(ref.problem_id)
    repo = Path(bundle.formal_repo)
    proof_hashes = _proof_hashes(repo)
    log = state.resolve() / "ledger" / "formal" / bundle.id / "checks" / (uuid4().hex + ".log")
    result = checker.check(repo, bundle.module, bundle.declaration, bundle.frozen, log, expected_type=bundle.expected_type)
    if proof_hashes != _proof_hashes(repo) or ledger.source_version(ref.problem_id) != before:
        raise ResearchError("Formal inputs changed during checking; result is not linked.")
    checked = bundle.model_copy(update={"check": result, "proof_sources": proof_hashes})
    append_once(state, "formal_bundles", checked)
    outcome = CheckOutcome(status="PASSED" if result.status.value == "checked" else "FAILED", summary="Fixed Lean build and exact declaration/type/axiom probe", details=result.model_dump(mode="json"))
    return _record(state, ref, VerificationKind.FORMAL, "lean", outcome, (ArtifactRef(path=str(log), sha256=sha256(log.read_bytes()), role="checker_log"),))
