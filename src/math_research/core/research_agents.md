# Research workspace

- Prefer MathResearch Ledger MCP when starting or continuing long-running research.
  Call `research_status` first.
  Include `workspace` with the current harness absolute workspace root in tool calls
  when available; some plugin hosts start stdio in the installation directory.
- Before substantial work on an existing Problem/Claim/Gap, call `research_context_packet`.
  Respect provenance, trust/freshness labels and missing or truncated mandatory material.
- Return a completed run through `research_ingest_episode` as a complete Research Episode
  with provenance. Preserve a single useful result, Gap or failed route with `research_save_note`.
- Use the services rather than directly editing `.math-research-ledger`.
- Soft review is advisory. Checked != accepted. Acceptance is human-only; MCP can only
  create a pending request. Server-side authority gates enforce these boundaries.

- Separate Confirmed Research Increment (source-reported state_delta) from advisory
  Next Research Directions. An Episode is a state increment, not merely a summary.
- Keep research hot paths light; consolidate meaningful checkpoints. Use save_note
  sparingly for one important isolated result/gap/failure, never every chat turn.
- Store broadly, retrieve selectively. Preserve raw Episodes, full proofs, failures,
  counterexamples, deferred routes, provenance, revisions and historical receipts.
- The harness owns the workspace; the user owns ordinary files. Ledger owns only
  `.math-research-ledger/`. Do not move, rename or organize user files. `papers/` and
  `notes/` are optional conventions. Canonical != verified; search relevance != evidence.
- Never stage, commit, push or select publication automatically. Private state,
  workspace.yaml and this AGENTS.md stay local-only. A separate notes repository
  contains only mature work selected by the user. Ledger never manages its Git index.
