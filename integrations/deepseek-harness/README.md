# DeepSeek Harness

The 1.2.2 default is the [Agent Host plugin](host-plugin/README.md) for
**DSH 0.2.1-rc.3**. It uses the same Python MCP server, but binds each Agent to its
Host-provided immutable `agent.session.header.cwd`. A serial `agent/created` listener
awaits the scoped official MCP client before Agent creation returns. No workspace
is selected at installation and no model argument can select another Ledger.

Prepare a new local package with an existing persistent runtime:

```powershell
python scripts/prepare_dsh_host_plugin.py --out '<new-plugin-directory>' --python '<persistent-python>'
dsh plugin --profile '<profile>' add '<new-plugin-directory>'
```

Install the matching 1.2.2 wheel+[mcp] for eleven tools. Refresh local packages and
start new sessions/restart after updates; existing runtimes are not upgraded automatically.
Preparation only renders the Python path, never installs/changes the runtime or
initializes research data. Rendered packages contain a private runtime path. The
public unrendered package uses `__MRL_PYTHON__`, which must be configured before
activation. Do not enable this plugin and the config-only Bundle in one profile.

Load the Host entry before the Agents it should serve; create/resume a new Agent
after installation or enabling. OFF unloads the creation listener, so new Agents
have no Ledger tools. Existing Agents retain their scoped client until disposal;
ON does not retrofit those already created. Agent dispose closes its own transport.
Resume uses the persisted header root, independently of ambient shell cwd.

Known roots without Ledger, ordinary subdirectories and state directories return
`NO_WORKSPACE` with eleven registered tools and no init/fallback. Missing absolute
Host cwd fails Agent setup with `NO_WORKSPACE` before spawning any MCP process.
This is a Host metadata error; restart with a Host-created workspace-bound session.
Shared workflow comes from the same MCP server instructions; no DSH policy is added
to the shared Codex skill. See [scope/lifecycle acceptance](../../docs/dsh-agent-workspace-acceptance.md).

Uninstall through `dsh plugin --profile '<profile>' remove dsh-math-research-ledger-host`.
No research data is deleted. Windows rc.3 real Profile cutover passed through the
official Desktop Host entry: eleven tools, real-workspace status/search, empty and
synthetic isolation, disposal, persisted resume, independent Host restart and
new-Agent OFF/ON. The Ledger remained byte-for-byte unchanged and the old default
was deselected. No GUI conversational turn or real-corpus mutation was tested.
See the [capability matrix](../../docs/harness-capability-matrix.md).
rc.2, macOS/Linux and UNC acceptance of the new Host adapter are unverified.

## Single-workspace/manual fallback

The retained **configuration-only Bundle** uses DSH's built-in
`@deepseek-ai/dsh-mcp-client`. It launches an external, persistent Python runtime with
`--workspace <research-workspace>` and exposes the same eleven tools as Codex in 1.2.2. Python
**3.12** is recommended. DSH manages the process lifecycle and native Plugins OFF/ON.

The fallback retains its fixed startup workspace and official MCP client behavior.
Its earlier nine-tool deployment is a historical record, not acceptance of the
current Host adapter or a claim about rc.2 compatibility. The current eleven-tool
Host adapter was tested on rc.3. Real-corpus mutations and macOS/Linux are untested.
See the [Problem lifecycle contract](../../docs/problem-lifecycle.md) and the [acceptance record](../../docs/archive/2026-10/dsh-host-acceptance-2026-10-23.md).

### Prepare and install fallback

Use the matching 1.2.2 wheel or build it with `python -m build --wheel`.
Published packages are available from
[GitHub Releases](https://github.com/Caie777/math-research-ledger/releases). Run preparation from the matching checkout or extracted source archive
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

### Enable, disable and uninstall fallback

Use DSH's native **Plugins** page. OFF removes the tools and stops the server; ON
restores them and starts the server. Disabling or removing the Bundle preserves data.
Uninstall with the `remove` command above, reload Desktop, and optionally remove only
the Bundle and its dedicated runtime.

### Scope and troubleshooting fallback

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
