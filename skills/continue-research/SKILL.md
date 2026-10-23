---
name: continue-research
description: Continue an existing long-horizon mathematical research problem using persistent MathResearch Ledger state, or checkpoint a meaningful research increment.
---

Inspect `research_status` when continuing research. Obtain `research_context_packet`
before substantial work on an existing Problem, Claim or Gap. Inspect exact objects
when required context is missing; search relevance is not evidence or a trusted premise.

Omit `workspace` normally: the server session is pinned at startup. The optional
compatibility field can only assert the same resolved root; it cannot select another
Ledger. On NO_WORKSPACE, ask the operator to configure startup `--workspace` or
`MRL_WORKSPACE` and restart; do not try other paths. MCP roots alone do not grant scope.

Keep research hot paths light. At meaningful checkpoints, submit complete Markdown
through `research_ingest_episode`: separate Confirmed Research Increment from advisory
Next Research Directions. Use `research_save_note` sparingly for one important result,
gap, failure or evidence. Never record every chat turn automatically.

Preserve full proofs, failures, provenance and history; store broadly, retrieve selectively.
Checked != accepted; canonical != verified. Soft review is advisory, and only humans
can grant acceptance. A reported delta never grants authority or changes a target by itself.

The harness owns the workspace and the user owns ordinary files. Ledger owns only
`.math-research-ledger/`; never edit that state directly or reorganize ordinary files.
Missing state requires explicit initialization. Never stage, commit, push or choose
publication of research on the user's behalf. A separate notes repository contains only
the mature work the user deliberately selects for publication.
