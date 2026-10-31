# Research workspace

- At a new session on long-running research, restore MathResearch Ledger state once.
  Call `research_status` first with an explicitly selected Problem.
  The MCP server pins its authorized workspace root at startup, selected by the host
  or explicit deployment configuration. Omit `workspace` in normal tool calls: if supplied,
  it only asserts the same pinned root and cannot select or expand session scope.
  If startup selected the wrong root, ask the host/user to restart with the correct root;
  tool arguments cannot repair an unbound or incorrectly bound session.
- At session start, load the exact target / `research_context_packet` before substantial work.
  Respect provenance, trust/freshness labels and missing or truncated mandatory material.
- Select the Problem explicitly; `.current` is not a safe substitute for user intent.
  Restore its designated primary target once at session start. A packet's complete /
  required_set_complete only covers its computed required set, not all mathematical state.
- Default to free research. Query Ledger when memory is likely to materially affect
  the next decision. Do not search the Ledger every reasoning turn.
  During continuous local reasoning, use the restored context without repeated calls.
  Retrieve narrowly on route changes, duplicate-route risk, premise reuse, conflicts,
  before expensive branches, requested failure history or checkpoint preparation.
- Return a completed run through `research_ingest_episode` as a complete Research Episode
  with provenance. Preserve a single useful result, Gap or failed route with `research_save_note`.
- Use the services rather than directly editing `.math-research-ledger`.
- Soft review is advisory. Checked != accepted. Acceptance is human-only; MCP can only
  create a pending request. Server-side authority gates enforce these boundaries.

- Separate Confirmed Research Increment (source-reported state_delta) from advisory
  Next Research Directions. An Episode is a state increment, not merely a summary.
- Keep research hot paths light; consolidate meaningful checkpoints. Use save_note
  sparingly for one important isolated result/gap/failure, never every chat turn.
- Preview a complete Episode, correct ERRORs, consider WARNINGs, then ingest once
  after meaningful state changes, route switches or session end. No mandatory N-turn
  saving rule. After roughly 4–6 substantive turns, an advisory check for meaningful
  changes is reasonable; no change means no Episode. Handoffs are operational
  ADVISORY memory, never mathematical premises; recheck referenced objects today.
- Store broadly, retrieve selectively. Preserve raw Episodes, full proofs, failures,
  counterexamples, deferred routes, provenance, revisions and historical receipts.
- The harness owns the workspace; the user owns ordinary files. Ledger owns only
  `.math-research-ledger/`. Do not move, rename or organize user files. `papers/` and
  `notes/` are optional conventions. Canonical != verified; search relevance != evidence.
- Never stage, commit, push or select publication automatically. Private state,
  workspace.yaml and this AGENTS.md stay local-only. A separate notes repository
  contains only mature work selected by the user. Ledger never manages its Git index.
