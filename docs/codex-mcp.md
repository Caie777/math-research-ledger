# Local Codex MCP integration

## Install once and confirm registration

From the checkout, with Python 3.11+ (this machine uses `.venv-win`, Python 3.12.14):

```powershell
$python = (Resolve-Path .venv-win/Scripts/python.exe).Path
& $python -m pip install -e '.[mcp]'
codex mcp add structured-math-research -- $python -B (Join-Path $PWD 'scripts/smr_mcp.py')
codex mcp list
codex mcp get structured-math-research --json
```

Registration uses official Codex configuration, not a custom harness. On this machine
the user configuration is `C:\Users\84968\.codex\config.toml`. The registered command is:

```powershell
D:\Projects\structured-math-research\.venv-win\Scripts\python.exe -B D:\Projects\structured-math-research\scripts\smr_mcp.py
```

The wrapper imports this checkout's `src`, preserves cwd and requires no activation or
relative executable paths. To run a fixed workspace manually, append
`--workspace D:\Research\math-research`. Open the tool checkout only for development;
open the Research Workspace for mathematics. The tool checkout no longer hosts active data.

Resolution priority: explicit `--workspace` > `SMR_WORKSPACE` > cwd and its ancestors
containing `.math-research`. A selected missing workspace does not fall through to another
project. Missing state returns `NO_WORKSPACE` with recovery instructions; MCP never calls init.

## Normal conversation

Start a fresh Codex session in the research directory (`codex -C D:\Research\math-research` or open that folder in
the IDE/desktop). Ask: “继续 PROBLEM-0001 的研究，先了解目前做到哪里。” Replace the example ID
with an existing Problem. Codex should read status and bounded context before substantive
work, return a complete Episode at the end, or stage one useful provisional note.

The nine directly discoverable tools are:

| Tool | Purpose |
| --- | --- |
| `research_status` | Paginated Problem/object references and current state |
| `research_search` | Ranked prior work, provenance and trust labels |
| `research_get_object` | Qualified `ref: str`, bounded/paginated body |
| `research_context_packet` | Budgeted current context, explicit mandatory omissions/truncation |
| `research_review_packet` | Exact inputs for independent advisory review |
| `research_stale_report` | Paginated drift report; no rechecking |
| `research_ingest_episode` | Complete Markdown → provisional archive/Proposal Store |
| `research_save_note` | One provisional Claim/Gap/FailedAttempt/Evidence/Counterexample |
| `research_request_acceptance` | Current PASSED receipt → pending human request only |

Descriptions and strict JSON schemas are in MCP `tools/list`, with read/write annotations.
No dispatcher/capabilities call is necessary. Notes use the same Episode parser, content
identity, candidate IDs, locks and atomic writes as full Episodes. Multi-candidate note bodies
are refused; use Episode ingestion instead. Responses are capped at 64 KiB including both
SDK text and structured content, with 1 KiB reserved for a normal JSON-RPC envelope. Large
review packets fail explicitly instead of silently dropping review inputs. Use scoped object
windows or smaller context/page budgets. Errors contain a code, message and recovery action.

Soft review remains advisory. Checked != accepted. There is no MCP accept, canonicalization,
shell, filesystem, freeze or compiler tool. The trusted human CLI remains a debug/authority
fallback, not a chat UI. Server-side automated-scope gates enforce the existing boundary.

## Verified locally on 2026-10-20

- Codex CLI `0.160.0`; MCP SDK `1.30.0`. Installed the SDK plus nine missing dependencies;
  none of the 89 previously installed package versions changed.
- Refreshed this project's editable metadata with `pip install --no-deps -e .` so the
  `smr`, `math-research` and `smr-mcp` entry points match the current source.
- SDK ClientSession and raw JSON-RPC subprocess tests exercise initialize, tools/list and all
  nine tools. They cover schema/argument errors, Windows paths, CJK/math Unicode, ambiguous
  references, no workspace/no init, duplicate Episode/note ingestion, context truncation,
  raw stdout cleanliness and the escaped/duplicated transport output bound.
- A clean ephemeral Codex CLI session received only the natural-language continuation request
  above and proactively called `research_status`, then `research_context_packet` successfully.
  A second clean session called all nine tools through the registered server, including a
  provisional Episode, a provisional Gap note and a pending acceptance request. No human
  acceptance or real mathematical work occurred.
- Both sessions disabled shell tools, apps, plugins and multi-agent features for the smoke.
  They used synthetic state under `.local-eval/codex-host-smoke-01`, not the real ledger.
  Status returned that synthetic state path while the launcher had no workspace argument or
  environment override: Codex CLI passed the `-C` project cwd to the stdio child.
- Fixture target: `PROBLEM-0001:claim:CLAIM-0001`. Synthetic verification receipt:
  `VERIFY-f29f15d6d69e9ee6720bb26d`; pending request:
  `REQUEST-3eb7caed19123493f64981bd`. These are transport markers, not mathematical evidence.
- Local evidence: `.local-eval/codex-host-smoke-01/{orientation,all-tools}-events.jsonl`,
  matching command/stderr/final files and `fixture.json`. These disposable logs are not committed.
- Checks: MCP transport tests **10 passed**; complete pytest **119 passed**; Ruff lint and
  formatting **97 files**; mypy **84 source files**; `git diff --check` passed. The real
  `.math-research` remained byte-identical across all **750 files**, with none added or removed.

The [official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
states that CLI, IDE and desktop share this configuration. This task verified CLI registration,
actual host calls and cwd behavior. The currently open desktop conversation's tool catalog
was created before registration and has not been refreshed; actual desktop/IDE tool loading
and child cwd have **not** been independently observed. Start a new session/reload that surface
and confirm tools before real work. If a host starts outside the project, use an explicit
absolute `--workspace` or `SMR_WORKSPACE` for that registration instead of assuming its cwd.

The later corpus cutover, additive root metadata and post-cutover validation are documented
in [Research Workspaces](research-workspaces.md). The earlier synthetic fixture evidence
above remains a historical test snapshot.

On this Windows environment the restricted execution sandbox blocks asyncio's local socket
pair before MCP startup. Transport tests and Codex smoke ran with local IPC permitted. This
did not require a transport workaround or weaken server-side authority rules.

Reproduce a disposable fixture (refuses existing paths and paths outside `.local-eval`):

```powershell
& $python -B scripts/seed_mcp_smoke.py .local-eval/my-new-smoke
& $python -B -m pytest tests/core_contracts/test_mcp_transport.py
```

Before a first real slice, independently confirm the intended desktop/IDE surface and cwd,
then prepare that slice's trusted checker/toolchain and exact input contract through the
existing core/CLI workflow. Formal execution is intentionally outside MCP's current surface.
