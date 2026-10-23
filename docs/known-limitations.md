# Known limitations and candidate status

MathResearch Ledger **1.2.1 is a local candidate, not a published release**. The core,
CLI, nine MCP tools and Codex share deterministic services; tests do not establish
mathematical truth or general long-term research reliability.

## Implemented in the candidate

- Pure MCP reads and Episode preview no longer create/remove a state-directory lock.
  Generation/content fencing checks the entire operation with bounded replay; observed
  interrupted journals remain fail closed. Writes retain locks and recovery semantics.
- MCP captures one workspace at startup. Tool `workspace` only asserts that same root;
  arbitrary cross-workspace selection is refused. MCP roots do not authorize scope.
  Use explicit `--workspace` or MRL_WORKSPACE for deployment; incidental cwd is a fallback.
- DSH now uses a configuration-only Bundle referencing the Host's native MCP client,
  with an external noneditable Python runtime. Python 3.12 is recommended. JS wrapper,
  Bundle private venv, runtime pointer and peer dependency glue have been removed.

Old writers must not run concurrently with new optimistic readers: the generation
protocol assumes upgraded writers. Do not silently mix cached pre-fix installations.
See [read consistency](archive/2026-10/read-only-checkpoint-2026-10-23.md),
[scope evidence](archive/2026-10/workspace-scope-2026-10-23.md) and
[Codex configuration](codex-mcp.md). Measured read latency is recorded in that evidence;
this work adds no cache, FTS, prefetch or reranker.

## DSH acceptance remains pending

The new configuration-only candidate has not been installed or accepted in a real DSH
Desktop/Profile/user session. Rendering, packaging, Python imports and MCP stdio smoke
do not prove actual DSH discovery, ON/OFF, read/write access or post-restart continuity.
Historical Host/JS Bundle evidence does not transfer automatically to this replacement.
macOS/Linux DSH Host acceptance is untested.

Historical user diagnostics described a Low Integrity process, a Low workspace root and
Medium existing private state, with a denied checkpoint-lock create. The read-path fix
removes that write requirement for pure reads; it does not repair permissions or prove
the diagnosis applies to the real current MCP Host. A sandboxed shell's integrity and
socketpair failure are not acceptance evidence for that Host path. No real ACL, owner,
integrity label or data was inspected/changed by this candidate work.

Preserve actual Host errors and distinguish spawn, handshake and tool-call failures.
The plugin never changes permissions, authentication or Full Access automatically.
Install/upgrade only from an ordinary terminal; see the [DSH guide](../integrations/deepseek-harness/README.md).

## Deferred

Real deployment needs a durable runtime, explicit startup pin and fresh Host session.
For Codex, keep project-only activation and disable bundled MCP when using the supported
project-local direct MCP deployment to avoid duplicate tools. No automatic project-root
placeholder is assumed. Multi-root selection, Host roots authorization, dynamic switching,
workspace registry, doctor/backup, caches/FTS, embeddings, legacy API removal and acceptance
authentication hardening remain separate work.

Human acceptance is a workflow boundary, not authentication against arbitrary local
code/filesystem access. Authority, verification and acceptance remain separate.
