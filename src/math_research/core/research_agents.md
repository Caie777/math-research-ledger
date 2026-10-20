# Research workspace

- Prefer structured-math-research MCP when starting or continuing long-running research.
  Call `research_status` first.
- Before substantial work on an existing Problem/Claim/Gap, call `research_context_packet`.
  Respect provenance, trust/freshness labels and missing or truncated mandatory material.
- Return a completed run through `research_ingest_episode` as a complete Research Episode
  with provenance. Preserve a single useful result, Gap or failed route with `research_save_note`.
- Use the services rather than directly editing `.math-research`.
- Soft review is advisory. Checked != accepted. Acceptance is human-only; MCP can only
  create a pending request. Server-side authority gates enforce these boundaries.
