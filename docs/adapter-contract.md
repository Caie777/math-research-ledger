# Harness adapter contract

Applies to MathResearch Ledger 1.2.2. Adapters compose the shared MCP server;
business decisions stay in deterministic services.

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

## Codex

The prepared Codex-native plugin bundles the shared Skill and MCP. With no configured
cwd, Windows Codex **0.160.0** supplies the new session's process cwd. Plugin ON/OFF
controls Skill availability and eleven/zero tools. Idle processes can be retained;
archive or Host closure disposes them. Reload does not promise workspace rebinding.
The inherited cwd is measured behavior, not an official stable `${PROJECT_ROOT}` API.

## DeepSeek Harness

Windows **0.2.1-rc.3** supplies immutable `agent.session.header.cwd`. A serially awaited
`agent/created` listener mounts `agent.ctx.plugin(dsh-mcp-client)` before creation
returns. Agent disposal releases its scoped transport/process. OFF prevents new
Agents receiving Ledger tools; existing Agents retain their clients until disposal.
ON affects new Agents and does not retrofit existing ones. rc.2 is unverified for
this adapter. The config-only Bundle is a manual / single-workspace fallback;
do not enable both deployments in one Profile.

See the [capability matrix](harness-capability-matrix.md), [Codex guide](codex-mcp.md)
and [DSH guide](../integrations/deepseek-harness/README.md). Runtime or package updates
require explicit installation and new sessions/restart; this contract adds no watcher,
rebind mechanism, process manager or permission repair.
