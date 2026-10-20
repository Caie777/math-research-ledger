# Research workflow

- When continuing long-running research, call `research_status` first.
- Before substantial work on an existing Problem/Claim/Gap, load `research_context_packet`.
  Respect provenance, trust/freshness labels and missing or truncated mandatory material.
- Return a completed research run through `research_ingest_episode` as a complete Research
  Episode with provenance. Preserve a single useful result, Gap or failed route with
  `research_save_note` when a full Episode is not appropriate.
- Use these services rather than directly editing `.math-research`.
- Soft review is advisory. Checked != accepted. Acceptance is human-only; MCP can only
  create a pending request. Server-side authority gates remain the enforcement boundary.
