# Harness capability matrix

## Support policy (1.3.0; established 2026-10-30)

**Protocol-neutral, DSH-first, other Harnesses on demand.** Version 1.3.0 retains
the standard eleven-tool MCP contract without Core/MCP breaking changes or
research-schema migration. The official Host UI name is **MathResearch Ledger for
DSH**. Release-specific 1.3.0 verification is to be recorded in the
[release notes](releases/v1.3.0.md); the older results below are not that gate.

Protocol-neutral does not mean equal maintenance commitments. The shared standard
MCP contract stays the same; Harness coverage is tiered:

| Tier | Harness | Release commitment |
|---|---|---|
| 1 — Official | DeepSeek Harness | Primary supported/tested/documented integration; actual DSH Host regression is release-blocking alongside Core and MCP |
| 2 — Compatibility | Codex | Retained best-effort; dedicated Harness regression is not required for every feature; Codex-only issues are normally non-blocking unless shared Core/MCP semantics are affected |
| 3 — On demand | Other Harnesses | No dedicated adapter until a real use case; standard MCP availability is not measured Harness acceptance |

Default installation follows the [DSH Agent Host plugin](../integrations/deepseek-harness/host-plugin/README.md).
The config-only Bundle is manual / single-workspace fallback only; the deployments
are mutually exclusive in one Profile. See the [adapter contract](adapter-contract.md)
and [release runner](development.md).

## Historical deployment observation (2026-10-30 audit)

At that audit the Profile had both DSH packages installed as `dependencies`, but
neither was selected in `bundles`. Package presence is not activation. This differs
from the earlier cutover state below; neither historical observation establishes
current activation or a completed 1.3.0 migration. Documentation changes do not
install, enable or upgrade packages for the user. That audit was not a Host
regression or GUI conversational acceptance.

## Historical support-policy acceptance (2026-10-30; 1.2.2 checkout)

The [DSH-first finalization report](dsh-first-finalization.md#5-dsh-acceptance-results)
records the successful required Core/MCP/actual-DSH gate at that time: 655 passed,
one Windows-inapplicable POSIX permission test skipped, and two compatibility cases
run separately and passed. Eighteen actual Host-service scenarios included the
authorized real-workspace read-only smoke; full Ledger content/mtime inventories
were unchanged, with no real-corpus mutation. The installed-wheel Host check also
passed. This is dated evidence from Windows DSH 0.2.1-rc.3 / Python 3.12.14 / MCP
1.30.0, not the new 1.3.0 release result, current Profile activation or GUI
conversational acceptance.

## Historical measured capabilities (2026-10-26)

The following evidence concerns the implementation prepared as 1.2.2, with the exact
Host versions shown. Host tests are Windows-specific. Isolated acceptance used
synthetic state and disposable Host configuration; real cutover used the user's
existing deployment with read-only Ledger calls. Neither means a Desktop GUI
conversational turn was tested. These results are not a new 2026-10-30 release run.

| Capability | DSH 0.2.1-rc.3 | Codex 0.160.0 |
|---|---|---|
| Trusted workspace source | Immutable `agent.session.header.cwd` | Host-supplied new-session MCP process cwd; measured behavior |
| Exact-root binding | Passed: Agent header root is child cwd, `--workspace .` | Passed: `--workspace .`, no configured cwd |
| Multiple workspaces concurrent | Isolated A/B; real/initialized synthetic Agents also coexist and reject cross-root assertions | Isolated A/B, eleven tools each, cross-root assertions rejected |
| Same workspace concurrent | Isolated two-Agent writes: distinct IDs, consistent counts, generation/lock checks | Isolated two-server writes: distinct IDs, consistent counts, generation/lock checks |
| Uninitialized workspace | Eleven tools; `NO_WORKSPACE`; no init; also passed in real Profile with an empty root | Eleven tools; `NO_WORKSPACE`; no init |
| Subdirectory no fallback | Passed in isolated official Host | Passed in isolated native Host |
| State-dir no fallback | Passed in isolated official Host | Passed in isolated native Host |
| First-turn tools | Factory returns with eleven tools; isolated first-request gate stops before provider I/O | Native session tool discovery before a model turn; no model call |
| Workspace immutable | Shell cd leaves existing binding unchanged, including real Profile | Shell cd leaves existing binding unchanged |
| Session/Agent resume | Disk-persisted resume restores header root, including real Profile and independent Host restart | Persisted `thread/resume` was not separately verified; fresh-session/restart passed |
| ON/OFF | New Agents eleven/zero; existing Agents retain eleven until dispose; real Profile manager applied both | Skill + tools eleven/zero; isolated reload and real cutover passed |
| Dispose | Isolated and real Agent disposal release scoped transport/process | Isolated `thread/archive` and Host closure release children; idle OFF processes may remain |
| Real workspace/Profile cutover | Official Desktop `runProfile` with real Profile passed; old config-only default deselected at that time; zero Ledger writes | Native plugin-policy/app-server acceptance passed; old direct MCP retired at that time; zero Ledger writes |

Those real cutovers tested development code before the formal version bump. They
do not establish today's Profile selection or installed implementation. Install the
matching wheel, refresh local packages and start new sessions/restart before adopting
an updated runtime. Fallback package availability is separate from its selection.

Dated source evidence: [Codex acceptance](codex-session-acceptance.md),
[DSH acceptance](dsh-agent-workspace-acceptance.md), and their later cutover sections.
Private transcripts, root paths, fingerprint inventories and configuration backups
remain local; they are not release assets.

## Unverified boundaries

Desktop GUI conversational acceptance of these deployments, macOS/Linux Host
behavior, UNC/network roots, and DSH rc.2 for the Host adapter remain unverified.
Synthetic writes do not establish acceptance for mutations of a real research corpus.
No claim is made about other Host versions or a stable Codex project-root API.
Any new release-gate result must retain its own date, versions and evidence; the
historical table cannot substitute for the current Core + MCP + actual DSH Host gate.
