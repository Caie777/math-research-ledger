# MathResearch Ledger

Persistent research memory, context, dependency tracking and verification for
long-horizon mathematical research agents.

MathResearch Ledger is not another research-agent runtime.
External agents do the research; Ledger preserves durable research state.
Use Codex or another harness for reasoning, reading and experiments, then carry the
same research workspace into the next session without reconstructing it from chat.

[中文说明](README.zh-CN.md) · [1.2.0 changelog](CHANGELOG.md)

## Why keep a research ledger?

A long proof may span many sessions. Chat summaries can lose assumptions, repeat
failed routes or cite a claim whose dependencies have changed. Ledger keeps Problems,
Claims, Gaps, proofs, counterexamples and failed attempts as structured records, along
with their sources, versions and checkpoint history.

- **Resume deliberately:** restore an explicit Problem, its primary target, open gaps
  and latest meaningful checkpoint.
- **Retrieve selectively:** use exact identifiers, bounded context and paginated originals;
  preserve full research history without loading it all into every conversation.
- **Track what a result relies on:** qualified identities and pinned dependency versions
  distinguish current, stale and unknown premises.
- **Checkpoint meaningful progress:** preview a Research Episode, retain its exact source
  and publish provisional records while keeping next directions advisory.
- **Keep evidence separate from authority:** verification, review, canonicalization and
  human acceptance have distinct roles.

```text
External research agent (Codex / other harness)
                       │ nine MCP tools
               MathResearch Ledger
             state · context · evidence
                       │
             .math-research-ledger/
```

## Five-minute quickstart

Requires **Python 3.11+**. From a cloned repository:

```powershell
git clone https://github.com/Caie777/math-research-ledger.git
cd math-research-ledger
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e '.[mcp]'
math-research-ledger --workspace 'C:\Research\MyProject' init
math-research-ledger --workspace 'C:\Research\MyProject' ledger create-problem 'My question' 'State the question and assumptions here.'
math-research-ledger --workspace 'C:\Research\MyProject' status
```

On macOS/Linux, activate with `source .venv/bin/activate` and use your own workspace
path. Initialization is explicit: choose a research directory outside the tool checkout.
It creates empty state, `workspace.yaml` and research `AGENTS.md`, preserves existing
instructions and ordinary files, and creates no demonstration research objects.
The `create-problem` command above creates the Problem you explicitly request.

For a downloaded wheel, use `python -m pip install './math_research_ledger-1.2.0-py3-none-any.whl[mcp]'`
instead of the editable install. See [GitHub Releases](https://github.com/Caie777/math-research-ledger/releases).
Then follow [Codex plugin setup](docs/codex-mcp.md), enable the plugin for your research
project and start a fresh session. Installation and enablement are separate; ordinary
projects can leave it disabled. A standalone MCP client can launch
`math-research-ledger-mcp --workspace '<research-workspace>'` over stdio.
MCP never initializes missing state. CLI aliases `smr`, `math-research` and `smr-mcp`
remain available; the Python import namespace is `math_research`.

## A minimal continuation workflow

**Free research by default; memory intervention by exception.**

1. Select the existing Problem explicitly with `research_status(problem_id="PROBLEM-0001")`;
   the development MCP server must already be pinned at startup. Inspect the primary target,
   gaps, risks, latest checkpoint and advisory handoff.
2. Read the exact target with `research_get_object`; restore context once with
   `research_context_packet(ref="<qualified target>", purpose="CONTINUE_RESEARCH", token_budget=8000)`.
   Check omissions, truncation, freshness and premise eligibility.
3. Research freely. Retrieve again when switching a major route, reusing a key premise,
   suspecting an old failed attempt or resolving a conflict with history.
4. At meaningful progress, prepare a [Research Episode](docs/research-episode.md).
   Separate **Confirmed Research Increment** from advisory **Next Research Directions**.
   Preview with `research_ingest_episode(dry_run=true)`, resolve ERRORs, understand WARNINGs,
   then ingest once when authorized. The next session restores from the Ledger.

These IDs illustrate the call pattern: use your actual Problem and qualified refs.
Search hits are candidates, not trusted premises. Inspect exact objects, input versions,
provenance and evidence before relying on them. Preserve failed routes and full proofs;
do not persist every chat turn or rebuild context after every local deduction.

## Nine MCP tools

| Tool | Use |
|---|---|
| `research_status` | Restore Problem state, continuation navigation and counts |
| `research_search` | Find bounded relevance candidates or an exact identity |
| `research_get_object` | Read exact objects, provenance and paginated originals |
| `research_context_packet` | Restore budgeted context for a target |
| `research_review_packet` | Prepare version-pinned material for advisory review |
| `research_stale_report` | Inspect dependency/version drift |
| `research_ingest_episode` | Preview or ingest a provisional research checkpoint |
| `research_save_note` | Capture an important isolated provisional increment |
| `research_request_acceptance` | Request human acceptance; never perform it |

Episode Markdown is limited to **128,000 characters** per MCP call. The lower-level
file ingestion ceiling and bounded responses are described in the
[Episode contract](docs/research-episode.md). No shell, arbitrary file-write, compiler
execution or human-accept operation is exposed by these tools.

## Trust and workspace ownership

`checked != accepted`; `canonical != verified`. Soft review is advisory. Freshness is
derived current state; historical verification and acceptance receipts remain historical.
Ingested output stays provisional, and source-reported revisions do not automatically
revise, refute or invalidate canonical objects.

Human acceptance is not exposed through the model-callable MCP surface and is enforced
as a **workflow boundary**. It is not an authentication or sandbox boundary against
arbitrary local code or filesystem access. The human CLI is a trusted channel; see
[architecture and authority](docs/architecture.md) and [verification](docs/formalization-v0.md).

The harness owns the workspace; the user owns ordinary files. Ledger owns only
`.math-research-ledger/`. Keep that directory, `workspace.yaml` and research `AGENTS.md`
local-only. Ledger never stages, commits, pushes or chooses research for publication.
An optional notes repository contains only work the user chooses to publish.
[Workspace format and migration](docs/research-workspaces.md) explains ownership and
Git-local exclusions. Historical provenance is not rewritten by tool upgrades.

## Integrations and limitations

- **Core Ledger, CLI, nine-tool MCP and Codex:** covered by automated tests and recorded
  integration checks. [Codex installation](docs/codex-mcp.md) includes native opt-in and
  project scoping. GitHub publication does not imply a public Plugin Directory listing.
- **DeepSeek Harness: experimental.** Its [native Bundle](integrations/deepseek-harness/README.md)
  shares the Python services and workspace. Historical isolated Host checks passed;
  real Windows existing-workspace acceptance remains incomplete at the reported
  Low/Medium Integrity boundary. macOS/Linux DSH Host acceptance is untested.
  The plugin never changes ACLs, integrity labels, authentication or Full Access settings.

[Known limitations and deferred 1.2.1 review](docs/known-limitations.md) distinguishes
current support from planned investigation. This release adds no agent loop, model
router or separate research database.

## Development

Use separate synthetic temporary workspaces; do not initialize research state here.

```powershell
python -m pip install -e '.[dev,mcp]'
python -m pytest
ruff check src tests scripts benchmarks
ruff format --check src tests scripts benchmarks
python -m mypy
python -m build
git diff --check
```

[Architecture](docs/architecture.md) · [Research assets](docs/research-assets.md) ·
[Historical engineering reports](docs/archive/2026-10/README.md)
