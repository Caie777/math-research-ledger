# DeepSeek Harness configuration-only Bundle

The 1.2.1 local candidate targets DSH **0.2.1-rc.2**. Real Desktop installation,
Profile reload and Host acceptance are pending; this is not a released compatibility claim.

```text
DSH Host -> built-in @deepseek-ai/dsh-mcp-client
         -> external Python 3.12 runtime
         -> math_research.mcp.server --workspace <root>
         -> shared Core Services and Ledger
```

The static configuration-only Bundle has no JS entry point, dependencies, peer glue,
private venv, embedded wheel or `.runtime.json`. DSH owns MCP lifecycle and ON/OFF.
The 1.2.1 design removes the previous JS transport wrapper and private runtime pointer.
All nine tools and the existing Codex integration still use the same Python services.

## Prepare locally, then install in ordinary PowerShell

Use an existing initialized workspace and a matching local wheel. Python 3.12 is
recommended. Without `--python`, preparation asks `py -3.12`; it never downloads Python
or falls back to 3.14. Explicit interpreters must be 3.11–3.13. The package's general
Python metadata remains unchanged; 3.14 is not validated as this DSH runtime.

```powershell
python scripts/prepare_dsh_config_bundle.py --workspace '<existing-research-root>' --wheel '<local-wheel>'
```

On Windows, defaults are `%LOCALAPPDATA%/MathResearchLedger/bundle` and the external
`%LOCALAPPDATA%/MathResearchLedger/runtime`. The script creates/reuses a dedicated venv,
installs `<wheel>[mcp]` non-editably, checks imports/version, and validates rendered YAML
using the runtime's PyYAML. The seven-file output includes the root Apache-2.0 LICENSE.
No DSH command, Profile edit, workspace initialization or permission change is performed.
Keep runtime separate from workspace and Bundle, and outside repo `dist/`.

Options: `--out`, `--runtime`, `--python`, `--force`, `--no-install`, `--no-index`,
`--find-links`. For offline install add `--no-index --find-links '<wheelhouse>'`.
`--no-install --python '<prepared-python>'` skips venv/pip but still checks imports and
matching version. This advanced mode may reuse a development interpreter for tests;
normal deployment should use the noneditable installed runtime. Mismatched wheel,
runtime and Bundle versions fail explicitly. Existing output is refused unless `--force`;
force only replaces an exact managed Bundle, with no unrelated files or implicit merge.

Preparation prints the next commands, but does not execute them:

```powershell
dsh plugin --profile desktop remove dsh-math-research-ledger
dsh plugin --profile desktop add '<rendered-bundle-path>'
```

Run these later in **ordinary PowerShell**, using the Desktop-installed dsh command
(Manage dsh Command). Do not run DSH plugin installation from a sandboxed DSH shell.
The remove step is for an existing installation. Do not change authentication or create
API keys. Keep the rendered directory and runtime at stable paths; the rendered patch
contains private absolute deployment paths and is not a public distribution template.
The public `config-bundle/` template contains placeholders only.

## Scope, ON/OFF and removal

Preparation fixes the canonical existing root in startup `--workspace`. Neither MCP
roots, incidental Desktop cwd nor tool `workspace` can switch Ledgers. The optional
tool field only asserts the same resolved root; other paths fail WORKSPACE_OUT_OF_SCOPE.
Missing state requires explicit human initialization. Preparation never initializes it.

The native Plugins page enables/disables the Bundle at Profile scope. OFF removes tools
after the Host applies the configuration and does not clear data. Uninstall with the
ordinary-terminal remove command, reload the Host, then optionally remove only the
Bundle/runtime. Never remove research state as an uninstall step.

## Handoff acceptance — not executed by the preparation script

1. Install the prepared local Bundle into the intended real Profile from ordinary terminal.
2. Reload/restart Desktop and use a fresh session. Verify exactly nine Ledger tools.
3. Call read-only status/search/context on an authorized synthetic workspace first.
4. Verify pinned-root rejection, native OFF/ON and unchanged state. Only then arrange
   separately authorized real-workspace acceptance.

The read-only checkpoint fix no longer creates `.checkpoint.lock` for pure MCP reads.
Observed interrupted journals still fail closed. Writes still need real write access;
no process or subtree security attributes are changed automatically. Historical Low
Integrity sandbox shell results are not proof of the real MCP Host execution path.
Actual DSH read/write and post-restart user-session acceptance remain unverified.

`host-smoke.cjs` remains an independent real Host ToolRuntime diagnostic; its optional
cycle changes Profile ON/OFF and must not be run alongside another Host. It is not GUI
acceptance. `discovery-smoke.cjs` remains synthetic-only and can write provisional data.
The standalone `math-research-ledger.patch.yml` remains for explicit headless diagnostics
with prepared Python; do not combine it with the Bundle (duplicate tool namespace).
No such Host/Profile commands are part of this candidate's repository-side validation.

The nine tools are status, search, object windows, context/review packets, stale reports,
Episode/note capture and pending acceptance requests. Captures stay provisional;
human acceptance is absent. No new agent loop or research database is introduced.

Official [Bundle packaging](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/publish)
and [MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md).
Historical evidence remains unchanged in docs/archive; it does not renew this candidate's Host acceptance.
