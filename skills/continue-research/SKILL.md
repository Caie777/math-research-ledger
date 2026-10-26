---
name: continue-research
description: Continue an existing long-horizon mathematical research problem using persistent MathResearch Ledger state, or checkpoint a meaningful research increment.
---

Inspect `research_status` when continuing research. Obtain `research_context_packet`
before substantial work on an existing Problem, Claim or Gap. Inspect exact objects
when required context is missing; search relevance is not evidence or a trusted premise.

For an explicitly requested new research line, preview `research_create_problem` with
title, statement and primary_target text, then create when authorized. Never invent an
unknown Problem ID in an Episode. Use `research_update_problem` to pause, close or
reopen an explicit Problem. Changes to statement/primary_target require
`revision_kind="semantic"`; preview first. Closed/resolved is project lifecycle,
not verification or acceptance. Do not turn lifecycle changes into Claim authority.

Omit `workspace` normally: the server session is pinned at startup. The optional
compatibility field can only assert the same resolved root; it cannot select another
Ledger. On NO_WORKSPACE, explain that the startup root has no initialized Ledger;
ask whether to initialize there, or restart in the intended workspace. Never initialize
without explicit authorization, try other roots or fall back to a parent directory.
MCP roots alone do not grant scope.

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
