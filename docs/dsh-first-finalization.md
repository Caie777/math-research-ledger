# DSH-first finalization — historical record, 2026-10-30

> Public, redacted historical report. All observations, versions, test counts and
> working-tree descriptions below refer to **2026-10-30**, before the 1.3.0 release
> preparation. At that closeout the changes were **31 tracked modifications + 5 new
> files**, uncommitted and unstaged. This is not today's Git/deployment status, the
> 1.3.0 gate result or a claim that a release was published. See the
> [1.3.0 release notes](releases/v1.3.0.md) for the subsequent release work.
>
> Exact private-corpus inventories, process identifiers and local diagnostic/evidence
> locations are intentionally omitted. The dated engineering results and generalized
> read-only zero-write conclusion are retained; private evidence is not a public asset.

## 1. State Audit at Historical Closeout

Policy: **Protocol-neutral, DSH-first, other Harnesses on demand.**
MathResearch Ledger remains the product name, not a DSH-specific Core product.
The initial tracked working tree was clean at `2ff536482da36edffd7926a320eac26e609832e2`.
Audit preceded source changes; no research Ledger was initialized at the checkout root.

### Actual DSH loading paths

- **Official / production:** the [Host manifest](../integrations/deepseek-harness/host-plugin/package.json)
  declares [its bundle patch](../integrations/deepseek-harness/host-plugin/cordis.patch.yml),
  which inserts only `dsh-math-research-ledger-host` with runtime-only configuration.
  Its [runtime entry](../integrations/deepseek-harness/host-plugin/index.cjs) registers
  the awaited `agent/created` listener and mounts the official MCP client inside each
  Agent's own scope. Child cwd is `agent.session.header.cwd`; arguments are exactly
  `-B -m math_research.mcp.server --workspace .`. The installed rc.3 factory actually
  serially awaits that event before publishing the Agent, and the official MCP client
  owns discovery, tool registration and scope teardown.
- **Fallback / manual single-workspace integration:** the separate
  [fallback manifest](../integrations/deepseek-harness/config-bundle/package.json)
  declares a [configuration-only patch](../integrations/deepseek-harness/config-bundle/cordis.patch.yml)
  inserting the global official MCP client with an installation-time absolute workspace.
  It has no JavaScript adapter. It is not a second equivalent official installation.
- Both use the same MCP `serverName`. Simultaneous activation is unsupported and can
  conflict in the native server/tool namespace; it is not a supported 22-tool mode.

### Why two “mathematics research plugins” appeared

The disk Profile audit found **two installed dependencies**: old config-only
`dsh-math-research-ledger` and `dsh-math-research-ledger-host`, each linked to a local
1.2.1 package. Neither was in the disk `dsh.profile.bundles` selection at that audit, and
neither was inserted by the Profile patch. The installed rc.3 PluginManager's
`listBundles()` merges selected bundles, installed dependencies and offered packages;
therefore an installed-but-OFF dependency can remain visible as a candidate.
The old fallback's locale title was simply “MathResearch Ledger”. This explains
similar UI candidates without assuming both were currently active.

The disk observation is not an inspection of the running GUI's state. Historical
2026-10-26 cutover results do not establish current activation or runtime versions.
The **2026-10-30 task did not rewrite, upgrade, enable or remove packages in the
real Profile**. Normal migration removes the old fallback dependency before adding Host;
merely switching it OFF need not remove the candidate. Updated fallback locale titles
explicitly say **Fallback / 备用**. See the [installation and migration guide](../integrations/deepseek-harness/README.md).

### DSH file-by-file classification

| Category | Files / role |
|---|---|
| production | [Integration guide](../integrations/deepseek-harness/README.md); Host [entry](../integrations/deepseek-harness/host-plugin/index.cjs), [manifest](../integrations/deepseek-harness/host-plugin/package.json), [patch](../integrations/deepseek-harness/host-plugin/cordis.patch.yml), [README](../integrations/deepseek-harness/host-plugin/README.md); [Host preparation](../scripts/prepare_dsh_host_plugin.py) |
| fallback | Config Bundle [README](../integrations/deepseek-harness/config-bundle/README.md), [manifest](../integrations/deepseek-harness/config-bundle/package.json), [patch](../integrations/deepseek-harness/config-bundle/cordis.patch.yml), [icon](../integrations/deepseek-harness/config-bundle/icon.svg), [English locale](../integrations/deepseek-harness/config-bundle/locale/en.json), [Chinese locale](../integrations/deepseek-harness/config-bundle/locale/zh.json); [fallback preparation](../scripts/prepare_dsh_config_bundle.py) |
| test-only | [Agent Host smoke](../integrations/deepseek-harness/agent-host-smoke.cjs), [Host package tests](../tests/core_contracts/test_dsh_host_plugin.py), [fallback tests](../tests/core_contracts/test_dsh_config_bundle.py); old [global Host smoke](../integrations/deepseek-harness/host-smoke.cjs) and [discovery smoke](../integrations/deepseek-harness/discovery-smoke.cjs) remain historical synthetic/global-path probes |
| legacy | [Headless cwd-discovery overlay](../integrations/deepseek-harness/math-research-ledger.patch.yml), [optional headless account overlay](../integrations/deepseek-harness/desktop-account.patch.yml); the old global/discovery probes also have legacy engineering-fixture status, not per-Agent acceptance status |
| obsolete | No tracked file proved safe to delete under all stated criteria |

Old prototype transports/installers mentioned in archived reports are already absent
from tracked source; they are history, not additional current entry points. The
[source distribution manifest](../MANIFEST.in) deliberately retains compatibility
patches and probes. **At the 2026-10-30 / 1.2.2 stage**, public Host npm packaging
contained five files; fallback packaging contained seven rendered files. Local
runtimes, state and private evidence were excluded. The later 1.3.0 Host package
adds two locale files for **MathResearch Ledger for DSH** and therefore has seven
files; that is an intentional new package layout, not a rewrite of this old result.

### Codex A/B/C classification and neutral boundaries

- **A — required shared functionality:** Core/MCP implementation, the shared
  [research Skill](../skills/continue-research/SKILL.md), the shared
  [checkout launcher](../scripts/smr_mcp.py), standard exact-root and real-stdio MCP
  tests, and ordinary-file/Git ownership enforcement. Two tests formerly named
  “Codex” only exercised standard module-entry/`--workspace .` semantics; they are
  renamed neutrally and remain release-blocking.
- **B — retained best-effort compatibility:** [native metadata](../.codex-plugin/plugin.json),
  [bundled MCP config](../.mcp.json), [portable metadata](../plugin.json),
  [portable MCP config](../mcp.json), [preparation](../scripts/prepare_local_plugin.py),
  [native Codex smoke](../scripts/codex_plugin_smoke.py), the first two packaging
  cases in [plugin tests](../tests/core_contracts/test_plugin.py),
  [Codex installation](codex-mcp.md) and [dated Codex acceptance](codex-session-acceptance.md).
  Portable assets still have manifest/test/docs consumers and are not obsolete.
- **C — removable:** none confirmed. Old nine-tool/rc.2 continuity evidence is
  historical evidence, not a new support claim or current release gate.

The source audit found no DSH/Codex private API, environment variable or Host branch
inside Core storage, schema, dependencies/stale propagation, retrieval/context,
Episodes, problem lifecycle, MCP schemas or startup scope binding. Shared runtime
code is unchanged. The strengthened [AST boundary tests](../tests/core_contracts/test_interfaces.py)
cover both import forms, relative/parent imports and deferred imports. The only
changed Core resource is the generic [research instructions template](../src/math_research/core/research_agents.md):
normal tool calls omit `workspace`; it is assertion-only and cannot repair wrong
startup binding. Existing real research instructions were not rewritten.

## 2. Final Architecture

```text
Core
  ↓
Standard MCP Server
  ↓
DSH Host Plugin   ← official / Tier 1
Codex Adapter     ← compatibility / Tier 2
Other Harnesses   ← on demand / Tier 3
```

The diagram denotes clients of the same standard server, not Core dependencies on
Host code. No private MCP semantics, new Agent loop or new Harness adapter was added.
DSH is actively developed, documented, regression-tested and release-blocking.
Codex remains best-effort; Codex-only issues normally do not block unless they affect
shared Core/MCP semantics. New adapters require a real use case.

## 3. Files Changed

- Product/support documentation: [English README](../README.md), [Chinese README](../README.zh-CN.md),
  [adapter contract](adapter-contract.md), [architecture](architecture.md),
  [capability matrix](harness-capability-matrix.md), [limitations](known-limitations.md),
  [Codex guide](codex-mcp.md), [Codex acceptance policy note](codex-session-acceptance.md),
  [1.2.2 support-policy clarification](releases/v1.2.2.md), [Changelog](../CHANGELOG.md),
  and new [development/release guide](development.md). Historical dates/results stay dated.
- DSH installation/metadata: the integration and both package READMEs, both package
  manifest descriptions, both fallback locale files, and both preparation helpers,
  linked in the classification above. Stable package IDs, MCP name, config-only
  behavior and Host runtime implementation are preserved.
- Release strategy: [hosted CI](../.github/workflows/ci.yml), new
  [actual DSH release workflow](../.github/workflows/dsh-release.yml), new
  [release runner](../scripts/release_gate.py), [pytest markers](../pyproject.toml),
  [inventory](../scripts/workspace_inventory.py), new [gate tests](../tests/core_contracts/test_release_gate.py).
  Required is Core + standard MCP + actual DSH; only two Codex packaging cases are advisory.
- Regression contracts: [Agent smoke](../integrations/deepseek-harness/agent-host-smoke.cjs),
  [Host tests](../tests/core_contracts/test_dsh_host_plugin.py),
  [fallback tests](../tests/core_contracts/test_dsh_config_bundle.py),
  [import boundaries](../tests/core_contracts/test_interfaces.py),
  [MCP scope](../tests/core_contracts/test_mcp_scope.py),
  [MCP transport](../tests/core_contracts/test_mcp_transport.py),
  [plugin compatibility markers](../tests/core_contracts/test_plugin.py), and the
  generic instructions template above. The drive-root test now uses a synthetic
  ordinary root instead of inspecting a real machine drive.
- Repository hygiene: [.gitignore](../.gitignore) excludes interrupted pip scratch
  directories, like other generated caches; no source or compatibility file is hidden.
- This audit/acceptance report is new. No real research data or real Profile is part
  of the changed-file set.

## 4. Files Removed

**None.** Compatibility and legacy engineering fixtures remain because existing
manifest/test/docs consumers and fallback behavior still justify them. No file was
removed merely to make the directory look cleaner.

## 5. DSH Acceptance Results

The **2026-10-30** required gate used Windows, installed **DSH 0.2.1-rc.3**, Python
**3.12.14**, MCP SDK **1.30.0**, and the **1.2.2 checkout at that time**. The official Cordis services,
Agent factory/loop, disk session persistence, tools and scoped MCP client ran with
an isolated home and no provider/model call. This is actual Host-service acceptance,
not a mock MCP client, GUI conversational acceptance or a real Profile cutover.

The historical **2026-10-30 unfiltered full pytest** run completed with **657
passed, 1 skipped, 0 failed** in **929.09 seconds**, with actual DSH integration
required and enabled. All **658 collected cases** were accounted for. The only skip
was the POSIX directory-permission test that does not apply on Windows; no DSH Host
test was skipped. Private JUnit evidence is retained locally, not linked or published.

Required pytest that day: **655 passed, 1 skipped, 2 compatibility cases deselected**
in **759.74 seconds**. The two compatibility cases then ran separately: **2 passed**.
Ruff lint/format, mypy (96 source files), wheel/sdist build and Git diff check passed.
The dated gate recorded required success, a zero compatibility return code, unchanged
read-only inventories and **18 successful actual Host scenarios**. These are not
1.3.0 test results; private logs and reports are not public release assets.

| Requirement | Observed result on 2026-10-30 |
|---|---|
| Fresh Agent | All 11 tools registered before factory create returned; first-request gate saw them before provider I/O |
| Workspace binding | Agent A read only initialized `workspace-A`; B read only initialized `workspace-B`; distinct active MCP child processes served them; both cross-root assertions rejected |
| Exact root / no init | Ordinary subdirectory, Ledger state directory and empty root each returned `NO_WORKSPACE`, with no nested/automatic initialization; missing Host cwd spawned no MCP process |
| Shell `cd` | Actual Agent-local shell changed to B and Host process cwd also changed; existing Agent A remained bound to A |
| Plugin OFF | Underlying real Cordis plugin-entry unload: new Agent had 0 Ledger tools; existing Agent retained 11 until disposal |
| Plugin ON | New Agent again had exactly the expected 11 tools |
| Resume | Official disk persistence restored A while ambient Host cwd was B; a new transport/process was correctly bound |
| Host Context restart | Full isolated Context disposal/recreation followed by disk resume retained A and all 11 tools; this case is distinct from fresh-Agent restart |
| Exact tool set | Names matched the reviewed eleven-tool set, not only a count; every observed MCP launch used exact `-B -m math_research.mcp.server --workspace .` |
| No default fallback duplicate | Host-only manifest installs one entry; isolated global Ledger tool count was 0 and each Agent had exactly one expected tool set; deliberate simultaneous fallback activation is unsupported, not claimed tested/supported |
| Dispose | Agent scope disposal closed the active MCP child; final teardown waited for every observed Ledger process to exit |
| Same-workspace concurrency | Two Agents/processes created distinct synthetic Problems, agreed on status/search, advanced generation and released the lock |
| Real workspace read-only | A separate Agent bound to the authorized real root; only `research_status` and `research_search` were called; both succeeded |

A separate **installed-wheel Host acceptance** also passed on **2026-10-30**:
**1 pytest case / 17 Host scenarios**, **53.88 seconds**, using the just-built 1.2.2
wheel in a new synthetic venv. `-I` import checks confirmed Ledger came from that
venv's installed wheel, not editable source. Existing dev-environment dependencies
(including Windows pywin32 bootstrap paths) were reused read-only; this was not a
fresh dependency-download claim. This artifact check made no real-workspace calls.
Its private report is retained locally and is not a public release asset.

### Real research Ledger zero-write conclusion (2026-10-30)

The authorized inventory scope was the **entire Ledger state tree**, not unrelated
papers in the research root. Before/after contents, timestamps and derived versions
were unchanged. The final inventory after the unfiltered full suite and separate
installed-wheel acceptance was unchanged as well. Only the authorized read calls
were made; no mutation tool, migration, initialization or research-instruction
rewrite ran against the real workspace.

Exact corpus counts, byte totals, timestamps, generation values, hashes, object
inventories and private evidence locations are intentionally excluded from this
public report. The generalized, dated **read-only zero-write** conclusion is
preserved; it does not establish acceptance for real-corpus mutations or a fresh
1.3.0 run.

## 6. Compatibility Status

Codex native metadata, bundled MCP, shared Skill, preparation and native smoke are
retained unchanged in behavior. The portable metadata/config remain as legacy
compatibility with existing manifest/test/docs consumers. Both dedicated packaging
cases passed in this run. The native Codex app-server smoke was **not rerun** for this
support-policy change; its older dated evidence is not represented as a new result.
Only Codex-specific cases are advisory. Shared Core/MCP tests, including exact-root,
real stdio and ordinary-file/Git protection, remain required.

## 7. Documentation Status

Both READMEs, installation guides, adapter contract, capability matrix, development
and release notes consistently use the three support tiers and Host-only default.
The fallback is labeled **Fallback / manual single-workspace integration**, with
normal uninstall/migration instructions rather than two equivalent recommended
packages. The measured matrix keeps historical 2026-10-26 evidence separate from
2026-10-30 Profile observations. The old research/history records are unchanged.

Hosted CI is explicitly Core/MCP + DSH packaging, **not** actual Host acceptance.
The new manually dispatched DSH workflow requires a configured self-hosted Windows
runner and matching runtime paths; missing prerequisites fail. The runner also clears
ambient pytest filters and requires a fresh actual Host report, so deselecting the
Host test cannot silently satisfy the gate. Codex packaging errors/timeouts are
recorded separately without relaxing any required semantic check. The workflow has
not been run remotely or installed as repository protection by this local task.

## 8. Historical Git Status and release recommendation (2026-10-30)

- At that closeout no automatic commit or push had been created. HEAD was
  `2ff536482da36edffd7926a320eac26e609832e2` (`chore: prepare v1.2.2 release`).
- The working tree then contained **31 tracked modifications + 5 new files = 36
  files**, unstaged, uncommitted and with no deletions. Generated runtimes, reports
  and build products were ignored. This is the initial state carried into the later
  1.3.0 preparation, not an assertion of its eventual changed-file count.
- At that time no research state directory or workspace configuration existed at
  the checkout root. Git confirmed the Python runtime modules in Core/MCP/ledger/
  retrieval/services/verification and production Host JavaScript entry were unchanged;
  only the generic research-instructions resource changed under source.
- The historical recommendation was to publish a deliberately versioned follow-up
  rather than overwrite 1.2.2 assets, and to record a successful actual DSH gate for
  that identity. The subsequent authorized release is **1.3.0**; its version metadata
  and Host locale additions are expected release changes, not part of the old 31+5
  snapshot. See the [release notes](releases/v1.3.0.md). A local successful gate does
  not configure or prove remote CI infrastructure.
- No real Profile migration was performed by the 2026-10-30 closeout. Its running
  GUI plugin list was not declared fixed. Later installation/migration must follow
  its own authorization and validation after the reviewed release is completed;
  this historical report does not claim those steps have now happened.

Initial restricted attempts encountered Windows environment permissions on generated
test/cache storage. The final acceptance used the user-authorized environment.
This was an environment limitation, not a Ledger/plugin permission-repair feature
or a fix to research data. Private diagnostic and recovery records are not published
or linked from this report.

### Exact changed paths at the 2026-10-30 closeout

```text
M .github/workflows/ci.yml
M .gitignore
M CHANGELOG.md
M README.md
M README.zh-CN.md
M docs/adapter-contract.md
M docs/architecture.md
M docs/codex-mcp.md
M docs/codex-session-acceptance.md
M docs/harness-capability-matrix.md
M docs/known-limitations.md
M docs/releases/v1.2.2.md
M integrations/deepseek-harness/README.md
M integrations/deepseek-harness/agent-host-smoke.cjs
M integrations/deepseek-harness/config-bundle/README.md
M integrations/deepseek-harness/config-bundle/locale/en.json
M integrations/deepseek-harness/config-bundle/locale/zh.json
M integrations/deepseek-harness/config-bundle/package.json
M integrations/deepseek-harness/host-plugin/README.md
M integrations/deepseek-harness/host-plugin/package.json
M pyproject.toml
M scripts/prepare_dsh_config_bundle.py
M scripts/prepare_dsh_host_plugin.py
M scripts/workspace_inventory.py
M src/math_research/core/research_agents.md
M tests/core_contracts/test_dsh_config_bundle.py
M tests/core_contracts/test_dsh_host_plugin.py
M tests/core_contracts/test_interfaces.py
M tests/core_contracts/test_mcp_scope.py
M tests/core_contracts/test_mcp_transport.py
M tests/core_contracts/test_plugin.py
A .github/workflows/dsh-release.yml
A docs/development.md
A docs/dsh-first-finalization.md
A scripts/release_gate.py
A tests/core_contracts/test_release_gate.py
```

`A` denotes new working-tree files here, not staged additions or a commit.
