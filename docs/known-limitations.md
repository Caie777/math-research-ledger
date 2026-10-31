# Known limitations

Applies to MathResearch Ledger 1.3.0: **Protocol-neutral, DSH-first, other Harnesses
on demand.** The standard eleven-tool MCP surface is retained; this release adds
no Core/MCP breaking change and requires no research-schema migration. The official
Host UI name is **MathResearch Ledger for DSH**. Historical acceptance is not a new
[1.3.0 release-gate result](releases/v1.3.0.md).

- **Support is tiered, not equal across Harnesses.** DSH is Tier 1 official:
  actively developed, documented, regression-tested and release-blocking. Codex is
  Tier 2 best-effort compatibility; not every feature gets dedicated Codex regression,
  and Codex-only issues normally do not block unless shared Core/MCP semantics are
  affected. Tier 3 Harness adapters are added only for real use cases. Standard MCP
  availability does not imply dedicated Host acceptance. See the
  [support contract](adapter-contract.md) and [development gates](development.md).
- **Recommended installation is not deployment status.** The default is the
  [DSH Agent Host plugin](../integrations/deepseek-harness/host-plugin/README.md).
  The config-only Bundle is manual / single-workspace fallback only; never enable
  both in one Profile. The 2026-10-30 Profile audit found both packages in
  `dependencies` but neither selected in `bundles`; this historical snapshot and old
  cutover evidence cannot establish current enablement or a completed 1.3.0 migration.
  Documentation changes do not deploy or activate them.
- **One workspace per MCP session.** Pin it with startup `--workspace` or
  `MRL_WORKSPACE`. Tool `workspace` only asserts that same root. Multi-root selection,
  automatic project switching and MCP roots authorization are not implemented.
- **Upgrade concurrent writers together.** Read-only checkpoint consistency uses
  generation/content fencing with bounded retry. All concurrent writers should use
  1.2.1+. Interrupted checkpoint journals fail closed and require recovery.
- **Read consistency has a cost.** Content fingerprinting adds measurable latency;
  large Ledgers may need more time for status/context reads. See the recorded
  [read-consistency measurements](archive/2026-10/read-only-checkpoint-2026-10-23.md).
- **Host coverage is dated and specific.** The 2026-10-26 evidence for Windows
  DSH 0.2.1-rc.3 and Codex 0.160.0 includes isolated native Host acceptance and
  controlled real-workspace/Profile read-only cutovers. The 2026-10-30 DSH-first
  closeout added actual isolated Host and installed-wheel acceptance on the 1.2.2
  checkout. Neither is the new 1.3.0 release-gate result.
  GUI conversational acceptance, macOS/Linux Host behavior,
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

For default installation, see the [DSH Agent Host plugin](../integrations/deepseek-harness/host-plugin/README.md).
Use the [Codex compatibility guide](codex-mcp.md) only when that Harness is needed.
Version 1.3.0 retains the eleven tools, including the two
[Problem lifecycle tools](problem-lifecycle.md) introduced in 1.2.2. Mutation coverage for those tools is synthetic; real cutovers only
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
