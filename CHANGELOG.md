# Changelog

## [1.3.0] - 2026-10-31

**Protocol-neutral, DSH-first, other Harnesses on demand.** This release consolidates
the support-policy work recorded on 2026-10-30; those test results remain historical.
The 2026-10-31 release verification passed: full suite 657 passed / 1 skipped;
required Core/MCP/DSH gate 655 passed / 1 skipped / 2 deselected, plus two passing
Codex packaging compatibility cases and 17 passing actual DSH Host scenarios.
See the [release notes](docs/releases/v1.3.0.md) for checks and unverified boundaries;
commit-specific hosted CI and publication results belong to the GitHub Release.

### Changed

- Clarify the protocol-neutral, DSH-first product: Tier 1 official DeepSeek Harness
  is actively developed, documented, regression-tested and release-blocking; Tier 2
  Codex is retained best-effort compatibility; Tier 3 adapters are added on demand
  only after a real use case. Shared Core/MCP semantics remain Harness-independent.
- Make the official DSH Agent Host plugin, displayed as **MathResearch Ledger for
  DSH**, the default installation path. Add English/Chinese Host locales: the public
  npm package intentionally grows from the historical five-file layout to seven
  files. Stable package IDs, MCP server name and runtime behavior are retained.
- Keep the config-only Bundle as manual / single-workspace fallback only and mutually
  exclusive with Host. Installation guidance is not a claim that a user's Profile
  has been activated.
- Retain the standard eleven-tool MCP server and existing research data semantics.
  No Core/MCP breaking change or research-schema migration is introduced.
- Define the release gate as Core + MCP + actual DSH Host acceptance. Dedicated
  Codex regression is optional; Codex-only issues normally do not block a release
  unless they reveal a shared Core/MCP semantic failure.
- Add development/release-runner instructions and separate historical acceptance
  from current deployment observations. The 2026-10-30 audit found both DSH packages
  registered as dependencies but neither selected in bundles. No historical test
  count or GUI acceptance is claimed as a new result by this documentation update.

## [1.2.2] - 2026-10-26

### Added

- Problem lifecycle MCP tools: `research_create_problem` and `research_update_problem`,
  with preview and explicit metadata/lifecycle versus semantic revision boundaries.
- Codex session-workspace bundled MCP and DSH per-Agent Host plugin integration.
- Shared adapter contract and measured Harness capability matrix.

### Changed

- Codex's normal deployment bundles Skill and MCP; project-level direct MCP is fallback.
- DSH Host plugin is recommended; config-only Bundle is manual / single-workspace fallback.
- Explicit MCP workspace binding enforces the supplied exact root.

### Fixed

- Explicit state-directory compatibility aliases can no longer bind a parent Ledger
  through MCP. Shared human path-helper compatibility remains available.
- Runtime/deployment documentation clarifies installation, refresh and restart requirements.

## 1.2.1 — 2026-10-23

### Added / Changed

- Pure MCP reads no longer need a writable state-directory lock. Optimistic checkpoint
  consistency uses generation/content fencing and bounded replay; interrupted journals fail closed.
- MCP sessions pin one workspace at startup. Tool-level `workspace` asserts that pin,
  rather than selecting another workspace.
- DSH uses a configuration-only Bundle with its native MCP client and an external
  persistent Python runtime. Python 3.12 is the recommended deployment path.

### Compatibility

- Deployments relying on arbitrary tool-provided workspace paths must use startup
  `--workspace` / `MRL_WORKSPACE`; MCP roots do not grant scope.
- All concurrent Ledger writers should run the 1.2.1+ generation protocol.

### Validation

- Windows Codex and DSH real Host read-only acceptance passed; DSH synthetic write passed.

## 1.2.0

### Research state safety

- Resolve Episode-local, candidate and qualified identities through one scoped contract.
  Preserve authored dependency versions; missing historical pins remain UNKNOWN.
- Separate UNKNOWN from STALE and expose conditional or blocked premise eligibility
  consistently. Current or canonical state does not imply verified truth.
- Bound Windows lock contention and transient access retries, surface permission failures,
  and run synchronous MCP services off the event loop.

### Episode integrity

- Preview structured increments with `research_ingest_episode(dry_run=true)` before
  publication; retain explicit archive-only capture and provisional authority gates.
- Validate archived source digests and authoritative JSONL reads. Damaged content fails
  closed instead of silently becoming a positive premise.

### Continuation and context

- Restore an explicitly chosen Problem, its primary target, risks and latest meaningful
  checkpoint; navigate checkpoint outputs through persisted publication mappings.
- Resolve exact identifiers before lexical search and provide bounded pagination guidance.
- Select continuation context from the target's recorded checkpoint relationships.
  Optional proofs provide navigation before full-text reading; spare budget need not be filled.
- Document free research with event-triggered memory. Plugin availability does not require
  retrieval every turn. Synthetic continuity and precision benchmarks are reproducible;
  they do not establish long-term mathematical research reliability.

### Harness integration

- Document Codex project-scoped enablement and installer behavior, preserving all nine MCP
  tools, existing CLI aliases and the `math_research` import namespace.
- Include a native DeepSeek Harness Bundle and explicit Python installer. Historical
  isolated Host checks passed; real Windows workspace acceptance remains incomplete at
  the reported integrity boundary. Windows DSH troubleshooting is paused. The plugin
  does not change ACLs, integrity labels, authentication or Full Access settings.

### Distribution and documentation

- Test Python 3.11 and 3.12 on Linux and Windows CI; align the build backend minimum
  with PEP 639 license metadata and the package author with the plugin identity.
- Include the build backend in development dependencies for non-isolated packaging
  tests, and retain subprocess diagnostics when a Bundle build fails.
- Add a user-first quickstart, clarify the MCP acceptance workflow boundary and input
  limits, and move historical engineering reports into a dated archive.
- Keep DSH experimental and record deferred compatibility work separately from this release.

Checked is not accepted; canonical is not verified. Historical verification and acceptance
receipts remain historical evidence. No automatic acceptance or canonicalization is added.

## 1.1.0 — repository baseline

Established the MathResearch Ledger identity, separate research workspaces, typed Research
Episodes, nine direct MCP tools and local Codex integration. This entry describes the
repository baseline and does not assert a package-registry release or a Git tag.
