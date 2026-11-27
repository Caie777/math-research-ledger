# DeepSeek Harness

The recommended installation is the [Agent Host plugin](host-plugin/README.md)
(**MathResearch Ledger for DSH**, DSH 0.2.x). Product policy is **Protocol-neutral,
DSH-first, other Harnesses on demand**: standard MCP is retained, Codex is
best-effort compatibility, and the config-only Bundle is a separate manual,
single-workspace fallback. There is no Core/MCP or research-schema migration.

It uses the same Python MCP server, but binds each Agent to its Host-provided
immutable `agent.session.header.cwd`. A serial `agent/created` listener
awaits the scoped official MCP client before Agent creation returns. No workspace
is selected at installation and no model argument can select another Ledger.

Install the public Host v1.5.1 `.tgz` as-is through DSH Plugins. Install the
matching Python wheel with `[mcp]` in a separate environment. The bundle has
no machine-specific configuration; the Host discovers Python via its PATH or
an optional local Profile `python` override. See the [Host guide](host-plugin/README.md)
for setup, relocation, runtime recovery and uninstall. The already published
v1.5.0 tarball does not contain this fix.

### Why two installation candidates can appear

DSH can list both installed package dependencies as candidates even when both
Bundles are OFF or neither is selected. OFF is not uninstall, and a candidate is
not proof of active tools. To migrate, remove the old `dsh-math-research-ledger`
through normal DSH package management, not just OFF, then add Host. Do not
install both alternatives in the same Profile. DSH manages bundle and Node
package dependencies and the scoped MCP connection; it does not provision the
third-party Python environment for this plugin.

Load the Host entry before the Agents it should serve; create/resume a new Agent
after installation or enabling. OFF unloads the creation listener, so new Agents
have no Ledger tools. Existing Agents retain their scoped client until disposal;
ON does not retrofit those already created. Agent dispose closes its own transport.
Resume uses the persisted header root, independently of ambient shell cwd.

Known roots without a valid `.math-research-ledger-link` pointer expose **zero**
Ledger tools and start no Python MCP process; there is no init, scan or ancestor
fallback. A valid pointer mounts the scoped client for exactly that Ledger, and an
invalid or escaping pointer refuses Agent setup. Missing absolute Host cwd fails
Agent setup before spawning any MCP process.
Explicit activation uses the native `/math-research-ledger enable [directory]`
command, never a resident model-facing bootstrap tool.
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
surface. Python **3.12** is recommended. DSH manages the process lifecycle and native Plugins OFF/ON.

The fallback retains its fixed startup workspace and official MCP client behavior.
Its earlier nine-tool deployment is a historical record, not acceptance of the
current Host adapter or a claim about rc.2 compatibility. The current eleven-tool
Host adapter was tested on rc.3. Real-corpus mutations and macOS/Linux are untested.
See the [Problem lifecycle contract](../../docs/problem-lifecycle.md) and the [acceptance record](../../docs/archive/2026-10/dsh-host-acceptance-2026-10-23.md).

### Prepare and install fallback

Use the matching 1.5.1 wheel or build it with `python -m build --wheel`.
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

The fallback release `.tgz` is only a public template, not a rendered deployment.
Keep rendered patches private: they embed absolute workspace and runtime paths.
After moving either, recreate the venv if needed and rerender with explicit
`--workspace`, `--out` and `--runtime`. To avoid a pinned workspace and a private
package altogether, use the Host bundle instead.

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
