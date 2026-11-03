# Real-use semantic convergence (2026-11-03)

See the [release notes](releases/v1.5.0.md) for the release-facing summary.

This change keeps the existing eleven MCP tools and shared deterministic services.
It does not migrate research data, move historical objects, or rewrite provenance.

* `research_update_problem.primary_claim_id` binds an exact existing Claim in the
  same Problem. Bare or qualified identities are accepted; the stored value is the
  local object ID. Provisional/unverified Claims are eligible, historical/rejected
  or invalidated Claims are not. Binding requires `revision_kind="semantic"` and
  uses the existing snapshots, semantic hashes and dependency freshness. Preview
  remains optional and zero-write; `expected_version` remains optional. The CLI
  equivalent is `ledger update-problem PROBLEM CLAIM`; the designation-only CLI
  fixes the revision kind to semantic internally. Binding alone preserves statement
  authority; only actual statement/target text changes reset it to provisional.
* Status distinguishes `primary_target_statement`, `primary_target_binding`
  (`TEXT_ONLY` or `CLAIM`), and `primary_claim_id`; bound objects retain navigation.
  Text-only targets are valid, without a missing-designation error.
* `lifecycle_status` is the authoritative project lifecycle. Active/paused/closed
  never implies mathematical verification or acceptance. Legacy `ProblemRecord.status`
  remains only for disk/hash compatibility; changing its historical hash contribution
  would invalidate existing version pins. Status output, maps and current scripts
  use lifecycle instead.
* Review packets include the Problem ref, semantic version, statement, primary
  target text and Claim binding. These inputs participate in the review version.
  Title, summary, lifecycle and closure metadata do not participate, including when
  the Problem is also a referenced dependency. Old reports must be reviewed against
  the expanded packet before a new submission; stored historical reports are retained.
  Review remains advisory, exact-target, complete-or-error and bounded to 64 KiB
  over MCP.
* Search accepts an optional strict `kind`, combinable with `problem_id`. Prefer
  both when seeking a Gap. Unknown canonical object kinds are explicit errors,
  validated by the shared finite public search kind enum before reading workspace
  state. An exact identity excluded by a valid filter yields no hit;
  it does not fall back to unrelated lexical results. Lexical ranking adds twice
  the independent title BM25 score to the existing combined title/body score.
* Stale reports expose `scope` and `counts_are_scoped=true`. Objects, verification,
  acceptance lists and their totals all refer to this scope. Freshness rules remain
  unchanged.

Historical Problem membership, IDs, source records, version snapshots and receipts
remain intact. A later human metadata/binding pass can designate current primary
Claims without relocating P1 history into newer Problems.

The pre-release closeout pins all eleven MCP input schemas, including the formerly
omitted Problem create/update schemas. The release also has additive MCP output
schema changes; see [the changelog](../CHANGELOG.md). Verification here is code-level
only. DSH live acceptance NOT performed; left for DSH.
