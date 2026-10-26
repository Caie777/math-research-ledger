# Harness capability matrix

Evidence as of 2026-10-26 for the implementation prepared as 1.2.2. Host tests are
Windows-specific. Isolated acceptance uses synthetic state and disposable Host
configuration; real cutover uses the user's existing deployment with read-only
Ledger calls. Neither means a Desktop GUI conversational turn was tested.

| Capability | Codex 0.160.0 | DSH 0.2.1-rc.3 |
|---|---|---|
| Trusted workspace source | Host-supplied new-session MCP process cwd; measured behavior | Immutable `agent.session.header.cwd` |
| Exact-root binding | Passed: `--workspace .`, no configured cwd | Passed: Agent header root is child cwd, `--workspace .` |
| Multiple workspaces concurrent | Isolated A/B, eleven tools each, cross-root assertions rejected | Isolated A/B; real/initialized synthetic Agents also coexist and reject cross-root assertions |
| Same workspace concurrent | Isolated two-server writes: distinct IDs, consistent counts, generation/lock checks | Isolated two-Agent writes: distinct IDs, consistent counts, generation/lock checks |
| Uninitialized workspace | Eleven tools; `NO_WORKSPACE`; no init | Same; also passed in real Profile with an empty root |
| Subdirectory no fallback | Passed in isolated native Host | Passed in isolated official Host |
| State-dir no fallback | Passed in isolated native Host | Passed in isolated official Host |
| First-turn tools | Native session tool discovery before a model turn; no model call | Factory returns with eleven tools; isolated first-request gate stops before provider I/O |
| Workspace immutable | Shell cd leaves existing binding unchanged | Shell cd leaves existing binding unchanged, including real Profile |
| Session/Agent resume | Persisted `thread/resume` was not separately verified; fresh-session/restart passed | Disk-persisted resume restores header root, including real Profile and independent Host restart |
| ON/OFF | Skill + tools eleven/zero; isolated reload and real cutover passed | New Agents eleven/zero; existing Agents retain eleven until dispose; real Profile manager applied both |
| Dispose | Isolated `thread/archive` and Host closure release children; idle OFF processes may remain | Isolated and real Agent disposal release scoped transport/process |
| Real workspace/Profile cutover | Native plugin-policy/app-server acceptance passed; old direct MCP retired; zero Ledger writes | Official Desktop `runProfile` with real Profile passed; old config-only default deselected; zero Ledger writes |

The real cutovers tested development code before the formal version bump. Existing
installations are not upgraded by preparing this release. Install the 1.2.2 wheel,
refresh local packages and start new sessions/restart before adopting that identity.
The installed DSH fallback files remain available but are not selected by default.

Current evidence: [Codex acceptance](codex-session-acceptance.md),
[DSH acceptance](dsh-agent-workspace-acceptance.md), and their later cutover sections.
Private transcripts, root paths, fingerprint inventories and configuration backups
remain local; they are not release assets.

Unverified: Desktop GUI conversational acceptance of these new deployments,
macOS/Linux Host behavior, UNC/network roots, and DSH rc.2 for the Host adapter.
Synthetic writes do not establish acceptance for mutations of a real research corpus.
No claim is made about other Host versions or a stable Codex project-root API.
