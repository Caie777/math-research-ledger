# Codex integration — Tier 2 compatibility

DSH is the [Tier 1 official integration](../integrations/deepseek-harness/host-plugin/README.md)
and the default installation path. Codex is retained as **Tier 2 compatibility**,
best-effort rather than an equal release target. Not every feature receives a
dedicated Codex Harness regression; Codex-only issues do not normally block releases
unless they expose a shared Core/MCP semantic failure. Other Harness adapters are
added on demand, not preemptively. See the [support contract](adapter-contract.md).

The observations below are from Windows Codex **0.160.0** acceptance on
**2026-10-26**, not a new run or a claim about the current user's installation.

Version **1.3.0** retains the standard eleven-tool MCP contract with no Core/MCP
breaking change or research-schema migration. The DSH Host UI name **MathResearch
Ledger for DSH** does not rename the product or this compatibility package.

If you need Codex, use the **Codex-native plugin package** prepared below: one plugin
contains the shared Ledger skill and a bundled stdio MCP server. Plugin ON exposes
eleven tools; OFF removes its skill and tools. Keep the Python runtime outside both
the plugin cache and research data. Updating source or package metadata does not
update an installed runtime: install the 1.3.0 wheel with MCP dependencies, refresh the
prepared native package and start fresh sessions/restart. Verify the installed
implementation and eleven-tool discovery before adopting it.

## Prepare and install

Install Python 3.12 (3.11+ supported by the package). Use the 1.3.0 wheel or build
one from the matching checkout. Run these commands from the tool checkout:

```powershell
python -m build --wheel
py -3.12 -m venv '<persistent-runtime>'
& '<persistent-runtime>/Scripts/python.exe' -m pip install '<local-wheel>[mcp]'
python scripts/prepare_local_plugin.py '<marketplace-root>/plugins/math-research-ledger' --python '<persistent-runtime>/Scripts/python.exe'
```

Replace angle-bracket placeholders with your own absolute paths. On macOS/Linux use
`python3 -m venv` and `<persistent-runtime>/bin/python`; that Host platform is untested.
Preparation requires a **new** package directory and an existing interpreter. It does
not install dependencies, bind research paths, initialize state or change Codex settings.
The generated interpreter path is local configuration; do not publish the prepared
package. The source templates contain no personal paths.

The installed package has just these resources:

```text
math-research-ledger/
  .codex-plugin/plugin.json
  .mcp.json
  skills/continue-research/SKILL.md
  LICENSE
```

The manifest references `./skills/` and `./.mcp.json`. Generated `.mcp.json` is:

```json
{
  "mcpServers": {
    "math-research-ledger": {
      "command": "<persistent-runtime>/Scripts/python.exe",
      "args": ["-B", "-m", "math_research.mcp.server", "--workspace", "."]
    }
  }
}
```

There is **no `cwd` or workspace environment setting**. The same installed Python
module serves Codex, other clients and CLI services; no second Ledger implementation
is packaged. The runtime must contain the desired wheel with its MCP dependencies.

The preparation helper deliberately excludes root `plugin.json` and portable
`mcp.json`. Codex 0.160.0 uses a different loader for Agent Plugins 1.0: absent `cwd`
there defaults to the plugin directory, and absolute executable commands are rejected.
Do **not** install the raw checkout as the Codex package or add the portable root
manifest to the prepared package. This distinction is covered by packaging tests and
[the versioned upstream loader](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/codex-mcp/src/agent_plugin_config.rs).

Create `<marketplace-root>/.agents/plugins/marketplace.json`:

```json
{
  "name": "math-research-ledger-local",
  "interface": {"displayName": "MathResearch Ledger Local"},
  "plugins": [{
    "name": "math-research-ledger",
    "source": {"source": "local", "path": "./plugins/math-research-ledger"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Developer Tools"
  }]
}
```

```powershell
codex plugin marketplace add '<absolute-marketplace-root>'
codex plugin add math-research-ledger@math-research-ledger-local
```

For an upgrade, prepare a new directory, update the local marketplace source, and use
Codex's normal remove/add or reinstall flow; never edit installed cache files. Recheck
that the cached native manifest/config match the prepared package and start a fresh
session. Updating runtime files in place while sessions run is not recommended.

## Workspace binding and first use

**Installation does not select a research directory.** In Windows Codex 0.160.0,
plugin-bundled native MCP without `cwd` inherits each new session's cwd. The server
resolves explicit `--workspace .` once against that process cwd and fixes the root
for its lifetime. This is measured Host behavior, **not** an official stable
`${PROJECT_ROOT}` API. Pin/update Codex deliberately and rerun acceptance on upgrades.

Start a session in the initialized research workspace root. `research_status` should
report that exact root; `research_search` should see only its records. Each session
may have its own server, including multiple sessions sharing one Ledger. Tool
`workspace` is assertion-only; another root returns `WORKSPACE_OUT_OF_SCOPE`.
Shell `cd`, MCP roots and model choices do not rebind the running server.

A session started in a subdirectory without its own Ledger returns `NO_WORKSPACE`,
even if its parent has one. An ordinary uninitialized root still starts the server
and registers tools, but calls return `NO_WORKSPACE`; activation never initializes
anything. The Agent should explain this and ask whether the user wants explicit
initialization there, or a new session in the intended root. Do not search parents,
copy state, repair permissions or initialize silently.

Explicit `--workspace`, `MRL_WORKSPACE` and legacy `SMR_WORKSPACE` all name an exact
workspace root. Passing the state directory itself (including startup cwd at
`.math-research-ledger` with `--workspace .`) returns `NO_WORKSPACE`; it cannot use
the shared path helper's legacy state-directory alias to bind a parent. Implicit
CLI/human cwd discovery remains available when no explicit source is supplied.

Restore an explicit Problem at session start. Research freely, retrieve at decision
events, and checkpoint meaningful increments. Available tools do not require per-turn
memory calls. See the [minimal workflow](../README.md#a-minimal-continuation-workflow).

## ON/OFF, reload and removal

Use Codex's plugin switch for `math-research-ledger@math-research-ledger-local`.
Its native setting is:

```toml
[plugins."math-research-ledger@math-research-ledger-local"]
enabled = true
```

Set `false` to disable the plugin as a whole. Trusted project settings can override
user defaults; remove stale per-server disabled overrides when adopting this deployment.
There must be no additional project direct MCP for Ledger, otherwise disabling the
plugin cannot disable that independent server. Verify exactly eleven tools ON and
zero OFF.

Native config change plus `config/mcpServer/reload` removed skill/tools in an existing
isolated session and restored them on ON. The existing idle Python processes remained
and were reused. No-change reload kept PID/root. Actual `thread/archive` released that
thread's processes; transport/app-server closure released all observed children.
Unsubscribe alone did not. Thus OFF is tool/skill deactivation, **not guaranteed
immediate OS process termination**. Close/archive sessions or restart the Host when
process disposal matters. This adapter adds no process manager or rebind mechanism.

After runtime/configuration upgrades, use a fresh session or restart Desktop. A
controlled interpreter replacement was picked up by new sessions; the existing
session kept its old interpreter until an explicit reload rebuilt its server.
Reload is not a promise of workspace switching or automatic file watching.

Uninstall through `codex plugin remove math-research-ledger@math-research-ledger-local`
and remove the local marketplace only if no other plugins use it. Remove a dedicated
runtime only after its sessions stop and if nothing else uses it. Research state is
never deleted by plugin removal.

## Direct MCP fallback and migration

Project-level direct MCP is a **legacy/fallback deployment**, not the normal setup.
If a Host version cannot preserve native session cwd, configure one direct stdio
server with an explicit absolute `--workspace` and disable bundled MCP to avoid
cross-binding or duplicates. Plugin OFF cannot control a separate direct server.
See [Codex MCP configuration](https://learn.chatgpt.com/docs/extend/mcp).

Before switching an existing project: back up local config, install the prepared
native package, stop old sessions, remove only the Ledger direct-server entry and
its bundled-server disabled override, enable the plugin, then create a session at
the exact research root. Check tool count, reported root and a scoped read before
using writes; test OFF too. Keep the backup for rollback. A controlled Windows
0.160.0 real-workspace cutover passed using native policy/app-server APIs and
zero-write reads; its old direct MCP was retired. This is not GUI conversational
acceptance. See the [capability matrix](harness-capability-matrix.md).

## Reproduce isolated acceptance

From the tool checkout, with Codex 0.160.0 available and a wheel+[mcp] runtime:

```powershell
python scripts/codex_plugin_smoke.py --python '<persistent-runtime>/Scripts/python.exe' --output 'dist/_run/codex-acceptance-new'
```

The output directory must not exist. The script creates its own `CODEX_HOME`, local
marketplace, synthetic Git/workspace fixtures and TMP/TEMP; it never copies login
state. It exercises native app-server APIs without a model turn. Windows process
checks inspect PID/parent/executable names only. Evidence stays under ignored `dist/`.
See the [acceptance matrix and limitations](codex-session-acceptance.md). Actual
Desktop GUI conversational acceptance remains unverified; the controlled real-workspace
switch is recorded separately from isolated acceptance.
