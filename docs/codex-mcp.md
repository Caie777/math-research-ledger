# Codex integration

Use a **project-local direct MCP server** with a persistent Python runtime and an
explicit startup workspace pin. The plugin skill can remain enabled; disable its
bundled MCP so the session exposes only one set of nine research tools.

Windows fresh-session acceptance passed with Python 3.12.10 / MathResearch Ledger
1.2.1: one tool set, real-workspace zero-write reads and cross-workspace rejection.
See the [Host record](archive/2026-10/dsh-host-acceptance-2026-10-23.md).

## Install the runtime and local plugin

Install Python 3.12, create a venv at a stable location outside the research workspace,
and install the release wheel with MCP dependencies:

```powershell
py -3.12 -m venv '<persistent-runtime>'
& '<persistent-runtime>/Scripts/python.exe' -m pip install '<local-wheel>[mcp]'
```

From a checkout or extracted source archive, prepare the plugin in a new directory:

```powershell
python scripts/prepare_local_plugin.py '<marketplace-root>/plugins/math-research-ledger'
```

The plugin includes its skill, manifests and source launcher. Preparation copies no
research state, runtime, conversation or credentials. Create
`<marketplace-root>/.agents/plugins/marketplace.json`:

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

## Enable only in the research project

Keep the user-level default disabled in `~/.codex/config.toml`:

```toml
[plugins."math-research-ledger@math-research-ledger-local"]
enabled = false
```

In the **trusted research project's** `.codex/config.toml`, enable the skill, disable
the plugin's bundled MCP, and register one direct server:

```toml
[plugins."math-research-ledger@math-research-ledger-local"]
enabled = true

[plugins."math-research-ledger@math-research-ledger-local".mcp_servers."math-research-ledger"]
enabled = false

[mcp_servers.math-research-ledger-project]
command = '<persistent-runtime>/Scripts/math-research-ledger-mcp.exe'
args = ['--workspace', '<research-workspace>']
cwd = '<research-workspace>'
enabled = true
required = true
```

Replace every angle-bracket placeholder with your own absolute path; they are not
Codex variables. On macOS/Linux use the venv's `bin/math-research-ledger-mcp`.
Keep private paths in local configuration. Trusted project settings override user
defaults; recheck both after installing/updating the plugin. Start a fresh session
after changing runtime or configuration and verify exactly nine Ledger tools.

This uses official [project MCP configuration](https://learn.chatgpt.com/docs/extend/mcp)
and [plugin MCP policy](https://learn.chatgpt.com/docs/config-file/config-reference).
No plugin-cache edits or automatic project-root placeholder are needed.

## Scope, usage and disabling

Each server captures one root at startup: `--workspace` > `MRL_WORKSPACE` > legacy
`SMR_WORKSPACE` > startup cwd ancestor discovery. Explicit pinning avoids dependence
on the Host's launch directory. Normally omit tool `workspace`: it only asserts the
same resolved root. Another root returns `WORKSPACE_OUT_OF_SCOPE`; MCP roots do not
authorize access. Missing state returns `NO_WORKSPACE` and requires explicit CLI
initialization. Scope enforcement is a workflow boundary, not an OS sandbox.

Restore an explicit Problem once at session start. Research freely; retrieve at a
decision event and checkpoint meaningful progress. Available tools do not require
per-turn memory calls. See the [minimal workflow](../README.md#a-minimal-continuation-workflow).

To turn this deployment off, set the direct server's `enabled = false` and disable
the project plugin if its skill is also unwanted; start a fresh session. Disabling
the plugin alone does not disable the separately configured direct server. Remove
only these local entries to uninstall; research data remains unchanged.
