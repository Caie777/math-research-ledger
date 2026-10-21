# Codex local plugin

MathResearch Ledger is opt-in through native Codex plugin state. No global MCP
registration or custom switch UI is required. Start a fresh session after changing state.

The portable package has root plugin.json, mcp.json, skills/, scripts/ and source.
A minimal .codex-plugin/plugin.json compatibility manifest references the same identity
and MCP definition. Tests enforce consistency; there is no second server or core.

## Developer checkout vs installed package

Install Python 3.11+ and the transport dependencies first:

```powershell
python -m pip install -e '.[dev,mcp]'
python scripts/prepare_local_plugin.py '<marketplace root>/plugins/math-research-ledger'
```

The preparation script copies only runtime source, launcher, skill, manifests and
license. It does not copy any ledger, venv, conversation or credentials. Its optional
--python interpreter is recorded as MRL_PYTHON for a developer smoke. The portable
command remains the bare executable python, as required by Codex's current schema.
The launcher can re-exec that explicitly configured interpreter, preserving transport
behavior. For a normal installed package use a Python environment with .[mcp]
dependencies installed, or pass --python when staging. No runtime installation happens
inside a research call. The checkout's scripts/smr_mcp.py also works directly.

Create <marketplace root>/.agents/plugins/marketplace.json:

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
codex plugin marketplace add '<absolute marketplace root>'
codex plugin add math-research-ledger@math-research-ledger-local
codex plugin list --marketplace math-research-ledger-local --json
```

Install the local plugin, then leave it disabled until research is intended. Use native
Plugins UI or the following user/project config, without editing any other plugin:

```toml
[plugins."math-research-ledger@math-research-ledger-local"]
enabled = false
```

Set enabled = true to opt in and start a fresh session. Config policy is enforced by
Codex; disabled plugins do not expose Ledger tools. No public directory submission.

## Workspace binding

The installed Codex 0.160.0 starts plugin stdio in the package directory, even when cwd
is omitted. This client did not advertise MCP roots. Hardcoding a research directory
would break multi-workspace use. Every tool therefore accepts an optional workspace
scope; the skill, server instructions and argument schema tell the agent to supply
its current harness absolute root. A natural-language continuation smoke automatically
supplied this argument and called status/context, without the user naming the plugin.

Resolution: explicit server --workspace / MRL_WORKSPACE (legacy SMR_WORKSPACE supported),
then a single harness MCP file root when available, then request workspace, then process
cwd ancestors. Explicitly selected missing state never falls through to another corpus.
Multiple host roots fail explicitly. This scope selects an existing ledger; it never
initializes state and never permits arbitrary file writes outside its private data.

## Migration from a global MCP

After plugin-owned calls work, remove only the old entry:

```powershell
codex mcp remove structured-math-research
```

Do not register a second always-on server. Preserve other MCP settings. The current
local deployment has removed that legacy entry and leaves the plugin disabled.

`scripts/codex_plugin_smoke.py` checks fresh app-server tool inventories and synthetic
calls without a model. The separate natural-language host test and cross-harness
results are recorded in [finalization report](finalization-report.md). No private
conversation or real research payload belongs in the public report.

Official schema and workflow: [Package your plugin](https://developers.openai.com/plugins/build/plugins),
[Desktop-only stdio](https://developers.openai.com/plugins/deploy/desktop-only).
