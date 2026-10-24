# Changelog

## 1.2.2 development — unreleased

- Add explicit Problem create/update MCP tools (eleven total); retain the original
  nine schemas. Preview without writes; allocate IDs under the checkpoint writer.
- Separate active/paused/closed project lifecycle and metadata from explicit semantic
  statement/target revision. Preserve legacy mathematical pins during metadata edits.
- Reuse existing version history and dependency freshness; closure never grants
  verification or human acceptance. Package/plugin metadata remains 1.2.1 for now.

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
