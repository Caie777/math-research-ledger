# MathResearch Ledger

MathResearch Ledger is a structured research-memory and verification layer exposed through a standard MCP server.

DSH is the primary supported and tested Harness.
Other Harness integrations are best-effort or added on demand.

Ledger is not another research-agent runtime. External agents do the research;
Ledger preserves durable research state. Use DSH for reasoning, reading and
experiments, then carry the same research workspace into the next session without
reconstructing it from chat. Core services and the MCP contract remain Harness-neutral.

[中文说明](README.zh-CN.md) · [Changelog](CHANGELOG.md)

**1.3.0 — Protocol-neutral, DSH-first, other Harnesses on demand.**
The official Host integration is displayed as **MathResearch Ledger for DSH**;
the product remains MathResearch Ledger. The standard MCP server retains eleven
tools, including [Problem lifecycle](docs/problem-lifecycle.md), with no Core/MCP
breaking change or research-schema migration.
See the [1.3.0 release notes](docs/releases/v1.3.0.md), [adapter contract](docs/adapter-contract.md)
and [dated capability matrix](docs/harness-capability-matrix.md).
The [2026-10-30 DSH-first audit](docs/dsh-first-finalization.md) is historical evidence,
not the 1.3.0 release-gate result.

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
External research agent (DSH / other MCP clients)
                       │ eleven MCP tools
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

For a downloaded wheel, use `python -m pip install './math_research_ledger-1.3.0-py3-none-any.whl[mcp]'`
instead of the editable install. See [GitHub Releases](https://github.com/Caie777/math-research-ledger/releases).
Then follow the default [DSH Agent Host plugin setup](integrations/deepseek-harness/host-plugin/README.md),
enable it in the selected Profile, and create/resume an Agent at your research root.
Installation and enablement are separate; this recommendation does not deploy it for
you. Ordinary projects can leave it disabled. If you specifically need Codex, use its
[Tier 2 compatibility guide](docs/codex-mcp.md). A standalone MCP client can launch
`math-research-ledger-mcp --workspace '<research-workspace>'` over stdio.
MCP never initializes missing state. CLI aliases `smr`, `math-research` and `smr-mcp`
remain available; the Python import namespace is `math_research`.

## A minimal continuation workflow

**Free research by default; memory intervention by exception.**

1. Select the existing Problem explicitly with `research_status(problem_id="PROBLEM-0001")`;
   the MCP server must already be pinned at startup. Inspect the primary target,
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

## Eleven MCP tools

| Tool | Use |
|---|---|
| `research_create_problem` | Preview/register a new active Problem |
| `research_update_problem` | Preview metadata, lifecycle or explicit semantic revision |
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

| Support tier | Harness | Commitment |
|---|---|---|
| **Tier 1 — Official** | DeepSeek Harness | Primary installation path; actively developed, documented, regression-tested and release-blocking |
| **Tier 2 — Compatibility** | Codex | Retained best-effort; not every feature gets dedicated Harness regression; Codex-only issues are normally non-blocking unless shared Core/MCP semantics are affected |
| **Tier 3 — On demand** | Other Harnesses | Standard MCP is available; no dedicated adapter until there is a real use case |

- **DSH default:** the official [Agent Host plugin](integrations/deepseek-harness/host-plugin/README.md),
  displayed as **MathResearch Ledger for DSH**, binds each new Agent to its immutable
  session root through the official MCP client.
  The configuration-only Bundle is **manual / single-workspace fallback only**;
  the two deployments are mutually exclusive in one Profile.
- **Codex compatibility:** a prepared [native plugin](docs/codex-mcp.md) controls the
  shared skill and bundled MCP together. In measured Windows Codex 0.160.0 behavior,
  `--workspace .` binds to startup session cwd, without parent discovery or auto-init;
  this is not a guaranteed project-root API.

**Evidence is versioned, not deployment status.** The 2026-10-26 Windows DSH
0.2.1-rc.3 and Codex 0.160.0 Host/cutover results remain historical. The 2026-10-30
Profile audit found both DSH packages installed as dependencies but neither selected
in `bundles`; it did not establish an enabled current deployment. No GUI conversational
acceptance is claimed. See the [dated capability matrix](docs/harness-capability-matrix.md)
and [support contract](docs/adapter-contract.md).

[Known limitations](docs/known-limitations.md): DSH macOS/Linux and formal writes to a
real research corpus have not been separately validated. Each MCP session has one pinned
workspace. The plugin does not change permissions or Full Access. GitHub publication
does not imply a public Plugin Directory listing.

## Development

Use separate synthetic temporary workspaces; do not initialize research state here.
The release gate is **Core + MCP + actual DSH Host acceptance**; Codex-only regression
is optional compatibility evidence, not a substitute for DSH. See
[development and the release runner interface](docs/development.md) for the required
persistent Python/runtime and DSH prerequisites. The commands below are baseline
checks, not a complete release gate.

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
