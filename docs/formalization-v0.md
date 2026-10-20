# Reusable formal verification

Primitives now live in math_research.verification.formal. The internal agent/benchmark product path is removed. Tests use synthetic targets and fake compiler output.

FrozenSource, FrozenManifest, freeze/load_freeze/verify_frozen, LeanChecker, FormalCheckResult and FormalBundle are retained. Changed statements require a new version/reason; existing snapshots cannot be rebound.

LeanChecker.check uses fixed Lake commands, validates frozen hashes before/after, builds, probes exact declaration/expected type, parses the axiom report and rejects sorry/custom axioms/forbidden declarations. native_decide is reported. Full logs cannot overwrite sources, repository files or previous logs.

freeze_statement/check_formalization services bind evidence to a qualified Claim/Gap and additive bundle. Module, declaration and expected type contract are required. Services snapshot project Lean sources and emit a general VerificationReceipt. A clean check is only checked; model/checker data cannot request accepted status.

Human acceptance requires a current passed receipt and correspondence rationale. Drift disables current trusted use without rewriting receipts. See smr formal freeze --help, formal check --help and acceptance accept --help.

Compiler execution writes build artifacts in the explicitly selected repository. The caller must authorize that repository and trusted installation. This package does not search for proofs, install toolchains or execute arbitrary bundle commands.
