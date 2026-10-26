# Known limitations

- **One workspace per MCP session.** Pin it with startup `--workspace` or
  `MRL_WORKSPACE`. Tool `workspace` only asserts that same root. Multi-root selection,
  automatic project switching and MCP roots authorization are not implemented.
- **Upgrade concurrent writers together.** Read-only checkpoint consistency uses
  generation/content fencing with bounded retry. All concurrent writers should use
  1.2.1+. Interrupted checkpoint journals fail closed and require recovery.
- **Read consistency has a cost.** Content fingerprinting adds measurable latency;
  large Ledgers may need more time for status/context reads. See the recorded
  [read-consistency measurements](archive/2026-10/read-only-checkpoint-2026-10-23.md).
- **Host coverage is specific.** Windows Codex 0.160.0 and DSH 0.2.1-rc.3 have
  isolated native Host acceptance and controlled real-workspace/Profile read-only
  cutover evidence. GUI conversational acceptance, macOS/Linux Host behavior,
  UNC/network roots and real-corpus mutations remain unverified. DSH rc.2 is
  unverified for the current Host adapter. See the [capability matrix](harness-capability-matrix.md).
- **Permissions remain the operator's responsibility.** Pure reads do not create a
  state-directory lock; writes still need write permission. The plugin never changes
  ACLs, integrity labels, ownership, authentication or Full Access. For startup errors,
  distinguish process launch, MCP handshake and tool-call failures; see the
  [DSH guide](../integrations/deepseek-harness/README.md).
- **Research authority is a workflow boundary.** Search relevance is not proof;
  authority, verification and human acceptance remain separate. These gates are not
  authentication against arbitrary local code or filesystem access. Tests do not
  establish mathematical truth or general long-term research reliability.

For installation, see [Codex](codex-mcp.md) or
[DeepSeek Harness](../integrations/deepseek-harness/README.md).
Version 1.2.2 adds two [Problem lifecycle tools](problem-lifecycle.md), for eleven
in total. Mutation coverage for those tools is synthetic; real cutovers only
registered them and used read operations.

Codex binding relies on measured inherited session cwd in 0.160.0, not an official
stable project-root variable. Install the prepared Codex-native package; the portable
Agent Plugins layout has different cwd defaults. OFF removes Skill/tools, while
idle processes may remain until thread archive or Host closure. Persisted Codex
thread resume was not separately verified. DSH OFF affects new Agents; existing
Agents retain clients until disposal. Neither adapter hot-rebinds an existing root.

Updating source or plugin metadata does not upgrade an installed persistent Python
runtime. Explicitly install the matching wheel, refresh local packages and start new
sessions/restart. Read the [adapter contract](adapter-contract.md) before extending
Host-specific behavior; Core, schemas, authority and checkpoint semantics are shared.
