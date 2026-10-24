# DeepSeek Harness

The recommended integration is a **configuration-only Bundle** using DSH's built-in
`@deepseek-ai/dsh-mcp-client`. It launches an external, persistent Python runtime with
`--workspace <research-workspace>` and exposes the same eleven tools as Codex (development checkout). Python
**3.12** is recommended. DSH manages the process lifecycle and native Plugins OFF/ON.

Windows Desktop **DSH 0.2.1-rc.2 / Python 3.12.10** Host acceptance passed: synthetic
read/write, real-workspace zero-write reads, restart persistence, OFF/ON and
cross-workspace rejection. DSH macOS/Linux and formal real-corpus writes are untested.
That acceptance covers released 1.2.1's nine tools; the two lifecycle tools have
synthetic stdio coverage and have not been tested in a real DSH Host.
See the [Problem lifecycle contract](../../docs/problem-lifecycle.md) and the [acceptance record](../../docs/archive/2026-10/dsh-host-acceptance-2026-10-23.md).

## Prepare and install

For the unreleased lifecycle tools, build a local wheel from this checkout with
`python -m build --wheel`. Published packages are available from
[GitHub Releases](https://github.com/Caie777/math-research-ledger/releases); 1.2.1 has
nine tools. Run preparation from the matching checkout or extracted source archive
with an existing initialized research workspace:

```powershell
python scripts/prepare_dsh_config_bundle.py --workspace '<research-workspace>' --wheel '<local-wheel>'
```

On Windows, preparation uses `py -3.12` and defaults to
`%LOCALAPPDATA%/MathResearchLedger/bundle` plus a separate
`%LOCALAPPDATA%/MathResearchLedger/runtime`. It installs the wheel with MCP dependencies
non-editably, validates imports/version, and renders a seven-file Bundle. Keep both
directories at stable paths outside the research workspace and repository `dist/`.

Use `--python` for an explicit Python 3.11–3.13 interpreter; no Python is downloaded.
Use `--out` / `--runtime` for alternate paths, or `--no-index --find-links '<wheelhouse>'`
for offline dependencies. `--force` replaces only an exact managed Bundle.
`--no-install --python '<prepared-python>'` reuses a matching installed runtime.

The script prints installation commands without running them. In **ordinary PowerShell**,
use the Desktop-installed `dsh` command (Manage dsh Command):

```powershell
# Upgrade only: remove an existing installation first.
dsh plugin --profile desktop remove dsh-math-research-ledger
dsh plugin --profile desktop add '<rendered-bundle-path>'
```

Reload Desktop and start a fresh session. Verify one set of eleven Ledger tools for this checkout, then
call `research_status` and `research_search` against the pinned workspace. Initialize
missing research state explicitly with the CLI; installation never creates it.

The release `.tgz` contains the public configuration template, not a rendered local
deployment. Prepare it through the source-archive script above before installation.
Rendered patches contain private deployment paths; keep them local.

## Enable, disable and uninstall

Use DSH's native **Plugins** page. OFF removes the tools and stops the server; ON
restores them and starts the server. Disabling or removing the Bundle preserves data.
Uninstall with the `remove` command above, reload Desktop, and optionally remove only
the Bundle and its dedicated runtime.

## Scope and troubleshooting

- The startup pin selects one Ledger. Tool `workspace` can only assert the same root;
  another root returns `WORKSPACE_OUT_OF_SCOPE`. MCP roots and Desktop cwd cannot
  switch an already pinned session. Do not install duplicate MCP definitions.
- For launch/import failures, check the persistent runtime path, installed version and
  rendered command. For missing tools, check the selected Profile, Plugins state and
  a fresh session. Preserve the actual Host error when distinguishing launch,
  handshake and tool-call failures.
- Pure reads need no writable checkpoint lock. Writes need normal write access.
  A sandboxed shell's `asyncio/socketpair` error does not identify the real Host MCP
  execution path. Do not change ACLs, security labels or Full Access to mask errors.

The Bundle does not change permissions, authentication or research files during
installation. It shares the Python Core Services and Ledger with Codex; captures
remain provisional and human acceptance is not model-callable.

Official references: [Bundle packaging](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/publish)
and [MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md).
