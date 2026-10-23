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

For project-only availability, set the plugin to `enabled = false` in user config and
`enabled = true` in the trusted research workspace's `.codex/config.toml`. Trusted project
settings override user defaults; command-line overrides have higher precedence. Installation,
marketplace discovery and enabling are separate. A `.math-research-ledger/` directory is data,
not a Codex plugin activation marker. See [configuration precedence](https://learn.chatgpt.com/docs/config-file/config-basic)
and [repo plugin enablement](https://developers.openai.com/plugins/build/plugins).

Plugin availability does not imply per-turn memory access. In research workspaces,
Ledger may be available throughout the session while retrieval remains event-triggered.
Restore once at session start; local reasoning defaults to zero calls; query on a relevant
decision event and checkpoint meaningful changes. Existing open connections may need a
reload/new session after configuration or runtime changes.

The 2026-10-22 audit found user-level Ledger enablement. It was changed, after backup and
actual inventory checks, to a disabled user default plus an enabled research project.
Both ordinary and marker-only synthetic workspaces then exposed zero Ledger tools; the
trusted research project exposed nine. UI/session persistence beyond these fresh-Host
checks remains unknown. See [continuity hardening](archive/2026-10/vertical-slice-continuity-hardening-2026-10-22.md).
This audit also observed `codex plugin add` re-enable the plugin in user config during an
update. After installing/updating, recheck the intended disabled user default and enabled
research-project override; do not assume the installer preserved project-only availability.

## Workspace binding

The recorded Codex 0.160.0 plugin behavior starts stdio in the package directory,
even when cwd is omitted, and did not advertise MCP roots. Released 1.2.0 therefore
accepted a model-supplied workspace fallback. **The 1.2.1 development source removes
that fallback:** a tool argument is not authority to access another Ledger.

Scope is captured once when the server starts: explicit `--workspace` > `MRL_WORKSPACE`
> legacy `SMR_WORKSPACE` > startup cwd ancestor discovery. A missing explicit selection
never falls through to another corpus. No later cwd/env change or tool argument rebinds
the session. MCP roots are not a scope source in this version, whether zero, one or
several are offered; operators must pin the deployment if startup cwd is not the project.
There is no root watcher, automatic multi-root selection or authorization registry.

Normally omit `workspace` in tool calls. The field remains for compatibility, accepting
only the exact pinned root after `expanduser`/filesystem `resolve` normalization.
Relative forms are anchored to the pinned root. Equivalent root symlinks/junctions and
Windows path case are allowed; a parent, child, sibling or different Ledger returns
`WORKSPACE_OUT_OF_SCOPE` before services run. This is a workflow scope, not a sandbox
against arbitrary local code or filesystem mutation. CLI workspace selection is unchanged.

The portable public `mcp.json` has no per-user pin. If the Host starts it in its install
directory without a usable scope, tools/list still works but calls return `NO_WORKSPACE`;
supplying a tool path or MCP roots does not fix that. Configure the private deployment's
startup args, for example:

```json
"args": ["-B", "${PLUGIN_ROOT}/scripts/smr_mcp.py", "--workspace", "/absolute/research-root"]
```

Alternatively set `MRL_WORKSPACE` in that private server's startup environment (preserve
any interpreter settings). Then reload/start a fresh session. Do not put the user's path
in the public package or enable that pinned deployment in ordinary projects: a deployment
pin binds every session using it, not automatically the current chat's project. Plugin
installation/update can replace local package settings, so retain the private configuration
and recheck it after updates. No automatic Codex session-root injection is claimed.

The supported stdio command/args/env/cwd configuration is documented in
[official MCP configuration](https://learn.chatgpt.com/docs/extend/mcp) and
[desktop plugin packaging](https://developers.openai.com/plugins/deploy/desktop-only).
See the [scope audit](archive/2026-10/workspace-scope-2026-10-23.md) for synthetic evidence
and current Host limitations. This source change has not refreshed the user's installed
plugin cache or real project configuration.

## Migration from a global MCP

After plugin-owned calls work, remove only the old entry:

```powershell
codex mcp remove structured-math-research
```

Do not register a second always-on server. Preserve other MCP settings. The legacy global
MCP entry is absent in the audited configuration. Current plugin availability follows the
project/user policy above; it is not globally enabled.

`scripts/codex_plugin_smoke.py` checks fresh app-server tool inventories and synthetic
calls without a model. The separate natural-language host test and cross-harness
results are recorded in [finalization report](archive/2026-10/finalization-report.md). No private
conversation or real research payload belongs in the public report.

Official schema and workflow: [Package your plugin](https://developers.openai.com/plugins/build/plugins),
[Desktop-only stdio](https://developers.openai.com/plugins/deploy/desktop-only).
