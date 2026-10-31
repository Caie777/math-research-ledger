# DeepSeek Harness

The **only recommended / default installation** in **1.3.0** is the official
[Agent Host plugin](host-plugin/README.md), displayed as **MathResearch Ledger for
DSH**, for **DSH 0.2.1-rc.3**. Product policy is **Protocol-neutral, DSH-first, other
Harnesses on demand**: standard MCP is retained, Codex is best-effort compatibility,
and the config-only Bundle is manual / single-workspace fallback only. There is no
Core/MCP breaking change or research-schema migration.

It uses the same Python MCP server, but binds each Agent to its Host-provided
immutable `agent.session.header.cwd`. A serial `agent/created` listener
awaits the scoped official MCP client before Agent creation returns. No workspace
is selected at installation and no model argument can select another Ledger.

Prepare a new local package with an existing persistent runtime:

```powershell
python scripts/prepare_dsh_host_plugin.py --out '<new-plugin-directory>' --python '<persistent-python>'
# In ordinary PowerShell, if the old fallback is installed in this Profile:
dsh plugin --profile '<profile>' remove dsh-math-research-ledger
# For an existing Host installation upgrade only, remove it before re-adding:
# dsh plugin --profile '<profile>' remove dsh-math-research-ledger-host
dsh plugin --profile '<profile>' add '<new-plugin-directory>'
```

The helper prepares **only Host**, never both packages. Run installation/removal
with the normal Desktop-installed `dsh` command (Manage dsh Command), not in a
sandboxed DSH shell. Use the same target Profile for every command. If neither
package is installed, skip removal; if upgrading Host, remove its existing package
before adding the newly rendered local directory.

### Why two installation candidates can appear

DSH can list both installed package dependencies as candidates even when both
Bundles are OFF or neither is selected. OFF is not uninstall, and a candidate is
not proof of active tools. To migrate, remove the old `dsh-math-research-ledger`
through the normal DSH command above, then add the Host package; do not edit Profile
files or install both alternatives. This also removes the obsolete fallback
candidate rather than merely deselecting it.

The **2026-10-30** disk inspection found **both dependencies at 1.2.1, neither
selected as a Bundle**. This is a historical deployment snapshot, not a 1.3.0 upgrade
or activation result. The commands here are operator instructions: this documentation
change has not upgraded, enabled or removed anything in the real Profile.

Install the matching 1.3.0 wheel+[mcp] for eleven tools. Refresh local packages and
start new sessions/restart after updates; existing runtimes are not upgraded automatically.
Preparation only renders the Python path, never installs/changes the runtime or
initializes research data. Rendered packages contain a private runtime path. The
public unrendered package uses `__MRL_PYTHON__`, which must be configured before
activation. Do not install this plugin and the config-only fallback Bundle in one Profile.

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
No research data is deleted. **Historical acceptance (2026-10-26, 1.2.2 development),
not current deployment state:** the recorded Windows rc.3 real Profile cutover
passed through the official Desktop
Host entry: eleven tools, real-workspace status/search, empty and synthetic isolation,
disposal, persisted resume, independent Host restart and new-Agent OFF/ON. In that
recorded run the Ledger remained byte-for-byte unchanged and the old default was
deselected. This does not establish today's installed version or active selection.
No GUI conversational turn or real-corpus mutation was tested.
See the [capability matrix](../../docs/harness-capability-matrix.md).
rc.2, macOS/Linux and UNC acceptance of the new Host adapter are unverified.

<a id="fallback"></a>

## Fallback / manual single-workspace integration (not the default)

Use this retained alternative only when deliberately choosing one installation-time
workspace instead of per-Agent Host scoping. **Remove the Host plugin first** using
normal DSH commands; OFF alone is insufficient to remove its installation candidate.
The fallback remains configuration-only: no JavaScript adapter or custom lifecycle
manager is added, and its stable package ID and MCP `serverName` are unchanged.

The retained **configuration-only Bundle** uses DSH's built-in
`@deepseek-ai/dsh-mcp-client`. It launches an external, persistent Python runtime with
`--workspace <research-workspace>` and retains the same eleven-tool standard MCP
surface in 1.3.0. Python **3.12** is recommended. DSH manages the process lifecycle and native Plugins OFF/ON.

The fallback retains its fixed startup workspace and official MCP client behavior.
Its earlier nine-tool deployment is a historical record, not acceptance of the
current Host adapter or a claim about rc.2 compatibility. The current eleven-tool
Host adapter was tested on rc.3. Real-corpus mutations and macOS/Linux are untested.
See the [Problem lifecycle contract](../../docs/problem-lifecycle.md) and the [acceptance record](../../docs/archive/2026-10/dsh-host-acceptance-2026-10-23.md).

### Prepare and install fallback

Use the matching 1.3.0 wheel or build it with `python -m build --wheel`.
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
# Replace desktop with the target Profile. If installed, remove Host first:
dsh plugin --profile desktop remove dsh-math-research-ledger-host
# Fallback upgrade only: remove an existing fallback installation first.
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

## Retained compatibility and test-only files

These files remain for compatibility and reproducibility, not as additional default
installation steps; do not combine their overlays with a Host installation:

- `math-research-ledger.patch.yml`: legacy opt-in headless/cwd-discovery MCP overlay;
  not the recommended Host entry or the rendered pinned fallback Bundle.
- `desktop-account.patch.yml`: optional legacy headless Desktop-account overlay;
  not required for Ledger plugin installation and not an authentication migration.
- `discovery-smoke.cjs` and `host-smoke.cjs`: test-only historical discovery / pinned
  Bundle acceptance probes, not installation helpers. The latter can persist Bundle
  ON/OFF with `--cycle`; do not run it against a real Profile as an installation step.
- `agent-host-smoke.cjs`: test-only official Agent Host acceptance with isolated
  synthetic fixtures; not proof that the user's current real Profile is enabled.

Keep all compatibility files and existing behavior. Installation and preparation
must not rewrite real research data or historical provenance.

Official references: [Bundle packaging](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/publish)
and [MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md).
