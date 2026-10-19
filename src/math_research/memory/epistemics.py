"""Single source of truth for the cross-cutting epistemic invariant.

Mathematical Research has two claim/evidence views — the workspace-global research stack
(:mod:`math_research.memory.global_claims` / :mod:`math_research.research.evidence`) and the
per-problem dossier stack (:mod:`math_research.memory.records`). Their *status
ladders* differ by design, but the core rule that keeps the system honest is
shared and must never drift between them:

* Evidence (experiments, computations, sketches) **supports** a claim; it never
  promotes it to a verified status on its own.
* ``formally_verified`` requires a machine-checked proof artifact.
* The only verification-grade evidence kinds are an accepted formal proof and a
  rigorous validated-numerical (interval-arithmetic) certificate.

The shared definitions keep verification criteria consistent across record views.
"""

from __future__ import annotations

# Evidence kinds that are verification-grade; everything else is support-only.
VERIFICATION_EVIDENCE: frozenset[str] = frozenset({"FORMAL_PROOF", "VALIDATED_NUMERICAL"})

# Statuses that assert a verified result (need a verification artifact to reach).
VERIFIED_STATUSES: frozenset[str] = frozenset({"verified", "formally_verified"})

# Statuses that additionally require an accepted formal-proof artifact.
PROOF_REQUIRED_STATUSES: frozenset[str] = frozenset({"formally_verified"})


def requires_proof(status: str) -> bool:
    """True if reaching ``status`` requires an accepted formal-proof artifact."""
    return status in PROOF_REQUIRED_STATUSES


def is_verification_evidence(evidence_type: str) -> bool:
    """True if this evidence kind is verification-grade (not merely supporting)."""
    return evidence_type in VERIFICATION_EVIDENCE


def assert_proof_required(status: str, *, has_proof: bool) -> None:
    """Raise if reaching ``status`` needs an accepted proof artifact and none exists.

    The single enforcement point for the proof requirement, shared by the global
    and dossier stacks so the rule cannot diverge between them.
    """
    if requires_proof(status) and not has_proof:
        from math_research.core.errors import ResearchError

        raise ResearchError(
            f"Reaching '{status}' requires an accepted formal proof artifact. "
            "Submit a verified proof first; evidence alone never confers rigor."
        )
