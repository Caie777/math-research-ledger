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
- **Host coverage is specific.** Windows Codex fresh-session and DSH Desktop
  0.2.1-rc.2 acceptance passed, including real-workspace zero-write reads, workspace
  rejection and DSH synthetic writes/OFF/ON. Formal writes to a real research corpus
  were not separately exercised. DSH macOS/Linux Host acceptance is untested.
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
[DeepSeek Harness](../integrations/deepseek-harness/README.md). The
[Host acceptance record](archive/2026-10/dsh-host-acceptance-2026-10-23.md) identifies
the tested candidate and the source of the real-session evidence.

The 1.2.2 development checkout adds two [Problem lifecycle tools](problem-lifecycle.md),
for eleven total. Formal version metadata remains 1.2.1; published 1.2.1 has nine.
These two tools have synthetic stdio coverage, without new real-workspace Desktop GUI acceptance.
The eleven-tool Codex-native plugin also has isolated Windows Codex 0.160.0
[session/ON/OFF acceptance](codex-session-acceptance.md). It relies on that version's
inherited session cwd, not an official project-root variable. Agent Plugins 1.0 has
different cwd defaults: install the prepared Codex-native package, not this checkout's
portable root manifest. OFF removes skill/tools; the Host may retain idle processes
until thread archive or app-server exit. macOS/Linux, UNC and actual Desktop GUI
switching of this new deployment have not been tested.
