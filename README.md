# MathResearch Ledger

Persistent research memory, context, dependency tracking and verification
for long-horizon mathematical research agents.

MathResearch Ledger is not another research-agent runtime. Codex, DeepSeek Harness
or another agent does the reasoning, reading and experiments. Ledger provides
structured persistent state, checkpoint history, bounded retrieval, source/version
tracking, downstream invalidation, verification evidence and human authority gates.

```text
Codex / DeepSeek Harness / other agents
                  │ MCP
          MathResearch Ledger
       ┌──────────┼───────────┐
     Ledger     Context    Verification
                  │
       .math-research-ledger/
```

The same workspace state belongs to neither a session nor a harness. Python 3.11+
is required. Distribution/plugin ID: `math-research-ledger`; Python imports remain
`math_research` to preserve integrations.

The prepared release version is **1.2.0**; see [CHANGELOG](CHANGELOG.md).
Local cache test versions are not release identities. This checkout has not been published.

## Install and opt in

```powershell
python -m pip install -e '.[mcp]'
math-research-ledger --workspace 'C:\path\to\your\research' init
```

Enable the local **MathResearch Ledger** plugin in the harness when needed and start
a fresh session. Leave it disabled for ordinary work. Use the harness's native plugin
state; no custom switch or global always-on MCP registration is required.
[Codex setup](docs/codex-mcp.md) covers portable packaging, the compatibility manifest
and local installation. [DeepSeek Harness installation](integrations/deepseek-harness/README.md)
uses a separate native DSH Bundle: build/extract it, explicitly prepare Python, then
register it with Desktop's `dsh plugin --profile desktop add PATH`. DSH's native Plugins
page controls profile-wide ON/OFF. The one-shot MCP patch remains an advanced alternative.
The Bundle has an independently installed Python environment. Historical isolated DSH
Host tests verified discovery, read-only calls and ON/OFF. Real Windows workspace
acceptance is **incomplete**: Desktop registers nine tools, but checkpoint-lock creation
is denied by the reported Low/Medium Integrity boundary. DSH Windows troubleshooting
is paused. The plugin never changes ACLs/integrity labels or switches to Full Access.
See the [current handoff](docs/dsh-adaptation-handoff-2026-10-22.md) and
[engineering evidence](docs/dsh-plugin-report.md); this is not a universal install-and-use claim.
There is no registry publication or public Plugin Directory submission in this release.

The canonical CLI is `math-research-ledger`. `smr` and `math-research` remain legacy
compatibility aliases; `smr-mcp` also remains available. Without refreshed entry points,
use `python -m math_research.cli`.

## Workspace ownership

Harness owns the workspace. User owns ordinary files. Ledger owns only
`.math-research-ledger/`. Init creates empty state, root `workspace.yaml` and a research
`AGENTS.md`, preserving existing instructions and user files. `papers/` and `notes/`
are optional conventions. Init creates no fake objects and is idempotent.
MCP never initializes a missing workspace.

Private state, `workspace.yaml` and research `AGENTS.md` stay local-only. Ledger never
stages, commits, pushes, or selects research for publication. The user's separate
notes repository contains mature work explicitly selected by the user.
[Workspace format, migration and backups](docs/research-workspaces.md).

## Checkpoints and trust

Continue existing work with `research_status`, then `research_context_packet` before
substantial research. Search returns relevance candidates; inspect exact objects,
versions, provenance, freshness, authority and verification before relying on them.

Research hot paths stay light. At a meaningful checkpoint, ingest one complete
[Research Episode](docs/research-episode.md): **Confirmed Research Increment** contains
source-reported typed state changes; **Next Research Directions** remain advisory.
Use `research_save_note` sparingly for important isolated results, gaps, failures or
evidence, never continuous recording of every chat turn.

Preview with `research_ingest_episode(dry_run=true)` before publication. Correct ERRORs,
review WARNINGs, then ingest once; `archive_only=true` explicitly preserves raw Markdown
without extraction. Exact archived-source reads fail with `INTEGRITY_ERROR` on digest mismatch.
See the [Episode preview and integrity contract](docs/p0-episode-integrity-2026-10-22.md).

Start each research session with an explicitly selected Problem in `research_status`,
then restore its exact primary target/context once. Continue local reasoning freely;
retrieve again when memory could change the next decision. See the
[continuation contract and fixed evaluation](docs/p0-continuity-evaluation-2026-10-22.md).
Plugin availability does not imply per-turn memory access. Research workspaces can enable
Ledger by project while retrieval stays event-triggered; ordinary workspaces can leave it
disabled. See [Codex scope and navigation hardening](docs/vertical-slice-continuity-hardening-2026-10-22.md).
`CONTINUE_RESEARCH` selects the target's local checkpoint closure; optional proofs supply
navigation until exact reading is needed. See [context precision](docs/context-precision-after-vertical-slice-2026-10-22.md).

Store broadly, retrieve selectively: retain raw Episodes, full proofs, failed attempts,
counterexamples, rejected/deferred routes, provenance and revision history. Optimize
retrieval and context budgets before deleting history.

- `checked != accepted`; `canonical != verified`.
- Search relevance is neither evidence nor a trusted premise.
- Models cannot grant themselves authority; human acceptance is server-enforced.
- Soft review is advisory. Staleness is derived current state; historical receipts remain.
- An Episode is a state increment, not merely a summary. Reporting a delta never
  automatically revises, refutes or invalidates a canonical object.

Nine stable direct MCP tools: `research_status`, `research_search`, `research_get_object`,
`research_context_packet`, `research_review_packet`, `research_stale_report`,
`research_ingest_episode`, `research_save_note`, `research_request_acceptance`.
They expose no shell, arbitrary file write, compiler execution or human-accept action.

## Development

Develop tooling here; use separate synthetic temporary workspaces for tests.

```powershell
python -m pip install -e '.[dev,mcp]'
python -m pytest
ruff check src tests scripts
ruff format --check src tests scripts
python -m mypy
python -m build
git diff --check
```

See [architecture](docs/architecture.md), [verification](docs/formalization-v0.md),
[release cleanup](docs/release-cleanup-2026-10-23.md) and
[historical finalization evidence](docs/finalization-report.md). The project evolved from a
standalone research-agent runtime into an agent-agnostic research ledger and tool layer.
Repository: [Caie777/math-research-ledger](https://github.com/Caie777/math-research-ledger).
