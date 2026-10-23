# DeepSeek Harness Bundle (experimental)

The primary DSH integration is a native Bundle named `dsh-math-research-ledger`,
separate from Codex's plugin.json/mcp.json. Its `dsh.bundle.patch` contributes one
Profile entry; a thin adapter delegates stdio discovery, tool registration, reconnection
and disposal to official `@deepseek-ai/dsh-mcp-client`. The existing Python Core
Services, nine research_* schemas, authority gates and ledger remain shared with Codex.

Target: official Desktop/MCP client **0.2.1-rc.2**, Node 22.15+, Python 3.11+.
Declared DSH range: `>=0.2.1-rc.2 <0.3.0`. Native installation and ON/OFF have passed
in a historical isolated Windows Host ToolRuntime. Real Windows workspace acceptance
is incomplete and troubleshooting is paused: the user reports Desktop discovery of
nine tools, followed by a denied checkpoint-lock create. macOS/Linux Host behavior
remains untested. See the [current handoff](../../docs/archive/2026-10/dsh-adaptation-handoff-2026-10-22.md)
and [historical validation](../../docs/archive/2026-10/dsh-plugin-report.md).
A valid manifest or successful pack alone does not establish Host acceptance.

The 1.2.0 package aligns release metadata with the shared Python service.
This packaging update does not renew the historical Host acceptance or change the
paused Windows status. See [release cleanup](../../docs/archive/2026-10/release-cleanup-2026-10-23.md).

## Build and install

From the source checkout, with build dependencies installed:

```sh
python -m pip install -e '.[dev,mcp]'
python scripts/build_dsh_bundle.py dist/dsh-math-research-ledger
python dist/dsh-math-research-ledger/install.py
dsh plugin --profile desktop add /absolute/path/to/dist/dsh-math-research-ledger
```

The output directory must be fresh. It contains an allowlisted Node Bundle and the
Python service wheel. Explicit `install.py` creates its private .venv and installs MCP
dependencies; it never initializes a workspace. To reuse a prepared interpreter, use
`--python /absolute/python`. Its .runtime.json pointer is private and excluded from npm
packages. Offline installation accepts `--no-index --find-links /absolute/wheelhouse`.

Use the **Desktop-installed** dsh command for the reserved desktop Profile, available
through the app's **Manage dsh Command** menu. A separate npm CLI refuses that Profile.
An ordinary Web deployment uses its own actual Profile name. No account configuration,
provider selection or login consumer needs changing.

For a distributable:

```sh
npm pack ./dist/dsh-math-research-ledger --pack-destination dist
```

Extract the .tgz into a stable writable directory, run its install.py, then install that
directory with dsh plugin. Keep linked directories in place. Direct tarball installation
also works in DSH, but requires preparing Python inside its installed package directory
and reloading afterward. The extracted-directory workflow prepares Python before DSH's
default activation. The repository root is a Python/Codex package: do not advertise
`dsh plugin add github:Caie777/math-research-ledger` as a working DSH install.
A future release can distribute the prepared tarball without registry publication.
There are no automatic install/prepare hooks and no interpreter binary in the archive.

Before modifying an existing Profile, back up package.json, cordis.patch.yml, cordis.yml,
pnpm-workspace.yaml and any pnpm-lock.yaml. Do not copy credentials or sessions.
The official installer maintains dependencies and bundle selection.

## Workspace, ON/OFF and removal

The [Bundle manual](bundle/README.md) covers private workspace/runtime configuration,
dependency installation, diagnostics and data permissions. Server precedence is
deployment --workspace > MRL_WORKSPACE > SMR_WORKSPACE > MCP roots > tool workspace >
cwd ancestor discovery. A deployment pin intentionally binds all sessions and cannot
be overridden by a model. Desktop cwd can differ from the research directory: pass
absolute workspace arguments per call, or pin workspace in the private Profile patch.
Missing state returns actionable NO_WORKSPACE; installation never initializes it.

The native **Plugins** page selects/deselects the Bundle. This is **Profile-wide**, not
a per-chat switch. HMR applies it live when enabled; otherwise restart/reload. OFF keeps
the installed dependency and data while removing Ledger tools. Home/invocation patches
can override a Profile toggle: inspect its actual application outcome. Settings'
read-only inventory is not the management page.

```sh
dsh plugin --profile desktop remove dsh-math-research-ledger
```

Reload/restart after removal; only then optionally remove the extracted directory and
its private Python runtime. Never delete research state as part of uninstallation.

## Clean-environment acceptance

1. Use a fresh DSH_HOME and a separate synthetic workspace. Explicitly initialize and
   seed only a synthetic Problem/Claim through the CLI.
2. Build/pack/extract the Bundle. Run its install.py with clean Python 3.11+ (or an
   offline dependency wheelhouse). Initialize a separate Web Profile using the official
   --from-default-profile web, then install the extracted package with dsh plugin.
3. Reload the real Host and inspect its actual tool registry: ON must expose nine
   mcp__math-research-ledger__research_* tools. Call only research_status and a bounded
   research_search. Counts and hits depend on the synthetic data.
4. Deselect/reselect through native Plugins. OFF must expose zero Ledger tools; ON
   must restore nine without changing ledger bytes or unrelated plugin behavior.
5. Uninstall; verify tools disappear and ordinary chat/research files remain intact.

host-smoke.cjs follows Desktop's exported resolved-profile lifecycle and executes the
installed **real Host ToolRuntime**, without a model. It invokes only status/search.
It is not the GUI and does not prove an already-open session refreshed. Its optional
--cycle invokes the official PluginManager, persists profile-wide OFF/ON and leaves ON.
Back up first; do not run beside another Host using that Profile. Reports contain search
excerpts: keep them private, outside packages.

```text
<Desktop Node carrier> --expose-internals host-smoke.cjs DSH_NODE_MODULES PROFILE_DIRECTORY WORKSPACE PRIVATE_REPORT_JSON [--cycle]
```

For packaged Windows Desktop the Node carrier is its executable with the documented
ELECTRON_RUN_AS_NODE environment; CLI users should prefer its installed dsh command.
If ACL/sandbox restrictions prevent profile locks, symlinks, loopback/event-loop setup
or subprocess startup, preserve the error and stop. Do not elevate, change ACLs, reset
profiles, replace authentication or infer tool discovery from a config dump.

## Windows permission boundary and tool responsibilities

Successful handshake/tools/list proves registration, not access to the research state.
The latest user-provided Desktop diagnosis reports a Low Integrity Python process and
a Low Integrity workspace root, while the existing Ledger subtree remains Medium
Integrity. Windows Mandatory Integrity Control's no-write-up rule explains the denied
`.math-research-ledger/.checkpoint.lock` create. This closing task does not inspect or
change the real directory's security attributes. An ordinary ACL grant alone is not
proof that the integrity boundary permits the operation.

`research_status` is logically read-only but takes a checkpoint lock to prevent reading
mixed index generations during publication. It needs permission to create and remove
that temporary lock; it does not initialize state or change research records. The lock
fix bounds retries and reports permission failures; it does not repair Windows security.
Preserve the exact server error, distinguish spawn failure from tools/call failure,
and have the user review process and subtree integrity levels separately. Stop on denied
access. The plugin never changes ACLs, owners or integrity labels, and never automatically
switches to Full Access. Any targeted label repair needs separate user approval; none
is performed by installation, uninstallation or this archived stage.

| Tool | Responsibility |
|---|---|
| `research_status` | Paginated workspace/Problem status and counts |
| `research_search` | Bounded relevance candidates, not verified premises |
| `research_get_object` | Exact object/version windows and provenance |
| `research_context_packet` | Budgeted context before substantial research |
| `research_review_packet` | Version-pinned material for advisory review |
| `research_stale_report` | Drift summaries without rechecking or accepting |
| `research_ingest_episode` | Explicit checkpoint capture as provisional candidates |
| `research_save_note` | Explicit single provisional capture |
| `research_request_acceptance` | Pending human request after current hard verification; cannot accept |

## Advanced legacy overlays

math-research-ledger.patch.yml remains for explicit headless --patch runs with prepared
Python. Do not combine it with the installed Bundle (duplicate server namespace).
discovery-smoke.cjs is the older **synthetic-only** continuity test: it can call context,
object and ingest tools and is not this read-only acceptance. The historical optional
desktop-account.patch.yml is not used or needed by this Bundle or a signed-in Desktop.

Official references, checked alongside the installed 0.2.1-rc.2 sources:
[Bundle packaging](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/publish),
[Profile CLI](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.md),
[Desktop command](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/desktop/README.md),
[MCP bridge](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md),
[Plugin Manager](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/boot/plugin-manager/README.md).
