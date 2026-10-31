# Harness adapter contract

Applies to MathResearch Ledger 1.3.0. Support policy established 2026-10-30,
release documentation updated 2026-10-31. **Protocol-neutral, DSH-first, other
Harnesses on demand.** Adapters compose the standard MCP server; business decisions
stay in deterministic services. The eleven-tool contract is retained with no
Core/MCP breaking change or research-schema migration. DSH priority does not
introduce DSH types, paths or lifecycle policy into Core or the MCP contract.

## Support tiers and release policy

| Tier | Harness | Commitment |
|---|---|---|
| 1 — Official | DeepSeek Harness | Actively developed, documented and regression-tested; actual DSH Host acceptance is release-blocking alongside Core and MCP checks |
| 2 — Compatibility | Codex | Existing integration retained best-effort; not every feature receives dedicated Codex Harness regression; Codex-only issues do not normally block a release unless shared Core/MCP semantics are affected |
| 3 — On demand | Other Harnesses | No dedicated adapter until a real use case requires one; standard MCP compatibility alone is not dedicated Harness acceptance |

See [development and release gates](development.md). Historical acceptance results
remain dated observations, not proof that a current deployment is enabled or that
the current release gate has run.

## Shared contract

> Harness determines where; Agent decides whether and when; Ledger guarantees memory semantics.

| Must agree across harnesses | Harness-specific differences allowed |
|---|---|
| Core semantics and Ledger data format | Trusted workspace source |
| Exactly eleven MCP tools, schemas and error codes | MCP/server lifecycle |
| Authority, verification and human-acceptance separation | Host plugin/package mechanism |
| Checkpoint and Research Episode semantics, provisional writes | ON/OFF lifecycle semantics |
| Shared research workflow / Skill semantics | Process retention behavior |
| Assertion-only tool `workspace`; no auto-init or model-selected arbitrary root | |

The shared workflow is free research by default, with memory retrieval at decision
events and meaningful checkpoints. Codex packages the shared Skill; DSH receives
the same workflow through MCP server instructions. Packaging does not grant
authority, make search results trusted premises, or perform human acceptance.

## Exact workspace binding

The adapter obtains an exact root from trusted Host/session context. The server
uses `--workspace .` relative to its Host-supplied process cwd, or an equivalent
explicit exact binding. That canonical root is immutable for the server lifetime.
Tool arguments can assert it, never select a new root. A different assertion returns
`WORKSPACE_OUT_OF_SCOPE`.

An uninitialized root returns `NO_WORKSPACE` while tools remain registered. Ordinary
subdirectories and the state directory itself do not bind a parent's Ledger.
There is no ancestor fallback or automatic initialization in this deployment.
An Agent may ask whether the user wants explicit initialization. Implicit human CLI
cwd/ancestor discovery and shared path-helper compatibility remain separate behavior.

## DeepSeek Harness — Tier 1 official

The default installation path is the official [Agent Host plugin](../integrations/deepseek-harness/host-plugin/README.md),
displayed as **MathResearch Ledger for DSH**. This UI title does not change the
product name, stable package ID or shared MCP server name.
Windows **0.2.1-rc.3** supplies immutable `agent.session.header.cwd`. A serially awaited
`agent/created` listener mounts `agent.ctx.plugin(dsh-mcp-client)` before creation
returns. Agent disposal releases its scoped transport/process. OFF prevents new
Agents receiving Ledger tools; existing Agents retain their clients until disposal.
ON affects new Agents and does not retrofit existing ones. rc.2 is unverified for
this adapter. The config-only Bundle is **manual / single-workspace fallback only**;
the two deployments are mutually exclusive in one Profile. Recommended installation
does not mean that a user's installed Profile already selects it.

## Codex — Tier 2 compatibility

The prepared Codex-native plugin bundles the shared Skill and MCP. With no configured
cwd, Windows Codex **0.160.0** supplies the new session's process cwd. Plugin ON/OFF
controls Skill availability and eleven/zero tools. Idle processes can be retained;
archive or Host closure disposes them. Reload does not promise workspace rebinding.
The inherited cwd is measured behavior, not an official stable `${PROJECT_ROOT}` API.
These Host-specific observations come from the dated 2026-10-26 acceptance; the
support-policy update does not claim a new test run.

See the [capability matrix](harness-capability-matrix.md),
[DSH default guide](../integrations/deepseek-harness/host-plugin/README.md),
[fallback guide](../integrations/deepseek-harness/README.md#fallback)
and [Codex compatibility guide](codex-mcp.md). Runtime or package updates
require explicit installation and new sessions/restart; this contract adds no watcher,
rebind mechanism, process manager or permission repair.
