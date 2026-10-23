# MathResearch Ledger for DeepSeek Harness

This is a DSH Bundle, installed with `dsh plugin --profile PROFILE add PATH`.
Its `cordis.patch.yml` mounts one thin deployment adapter over the official
`@deepseek-ai/dsh-mcp-client`. The nine `research_*` tools, workspace resolver,
authority gates and data remain in the same Python MCP server used by Codex.

Requires Python 3.11+, Node 22.15+ and DSH `>=0.2.1-rc.2 <0.3.0`.
Windows Desktop 0.2.1-rc.2 is the acceptance target; macOS/Linux paths are implemented
but require host verification. No Python, DSH login credential or research data is bundled.
The package contains one wheel of the Python service; pip installs its MCP dependencies.

Windows compatibility status (2026-10-22): historical isolated Host discovery and
ON/OFF/ON passed, but real Desktop workspace acceptance is incomplete. The user reports
nine registered tools and a denied checkpoint-lock create across a Low/Medium Integrity
boundary. Windows troubleshooting is paused; this is not a universal install-and-use
release. See the source repository's `docs/archive/2026-10/dsh-adaptation-handoff-2026-10-22.md`.
The plugin never changes ACLs, integrity labels or the Host's Full Access setting.

The prepared 1.2.0 package includes the current shared Python service. Packaging checks
do not renew the historical Host acceptance or resolve the paused Windows issue.

Extract the release tarball to a stable writable directory first. Prepare Python before
registering the directory, because DSH installs enable their bundle by default:

```sh
python install.py
dsh plugin --profile desktop add /absolute/path/to/extracted/package
```

Use Desktop's own `dsh` command for `desktop`, not a separate npm CLI. The app menu
**Manage dsh Command** identifies that command. This installer only creates `.venv/`
and `.runtime.json` beside itself. With an offline dependency wheelhouse, add
`--no-index --find-links /absolute/path/to/wheels`. To deliberately reuse an existing
Python with Ledger[mcp] already installed, use `python install.py --python /absolute/python`.
It checks imports before saving the private runtime pointer. It never changes login.

Direct `.tgz` installs are also supported by DSH; their installed package directory needs
the same explicit `install.py` step after installation, followed by a reload. The extracted
directory workflow avoids this initially unprepared state. Keep linked directories in place.

Restart/reload the profile or start a fresh session. In the native **Plugins** page,
select/deselect the `dsh-math-research-ledger` bundle. This is profile-wide; other
sessions using the profile are affected. OFF retains the installed package and all data.
With HMR, the official manager applies the change live; otherwise restart is required.
The read-only Settings plugin inventory is not the management page.

The plugin discovers an existing workspace from explicit tool `workspace` arguments,
the server's environment, or its cwd ancestors. Desktop can start in another directory:
pass the actual absolute workspace with each tool call, or pin it in the profile's own
`cordis.patch.yml` (preserve other rows). An explicit deployment pin applies to all sessions:

```yaml
- id: mcp-math-research-ledger
  config:
    workspace: /absolute/path/to/your/research
```

Optional `python: /absolute/python` overrides the local runtime pointer. Environment
`MRL_PYTHON` is also supported. Neither field belongs in a public package. Server precedence
is deployment `--workspace` > `MRL_WORKSPACE` > `SMR_WORKSPACE` > MCP roots > tool workspace
> cwd ancestor discovery; a deployment pin intentionally cannot be overridden by a model.
No missing workspace is silently initialized. Only when explicitly intended, initialize
separately using `math-research-ledger --workspace /absolute/research init`.

After installation, inspect the actual Agent tool list: ON has nine
`mcp__math-research-ledger__research_*` names; OFF has none. Call `research_status`
with your workspace, then `research_search(query="PROBLEM-0001", limit=1)`.
Expected counts and hits depend on your data. Never assume a successful install means
the Host actually loaded the tools. See the repository's `host-smoke.cjs` for a real
Desktop Host profile probe which invokes only these two read-only tools, without a model.

Diagnostics: a missing interpreter reports the `install.py` repair; missing MCP imports
require installing Ledger[mcp] in that interpreter. `NO_WORKSPACE` includes explicit
selection/init steps. Inspect DSH's plugin diagnostics and server stderr for spawn/ACL
errors. A logically read-only status still creates/removes a checkpoint lock for index
consistency. Check process and existing Ledger-subtree integrity levels separately:
labeling a workspace root does not prove its old contents have the same label.
The bounded lock fix reports access denial; it does not fix Windows security attributes.
Do not elevate, loosen research directory ACLs or move research data to fix a
denied launch. A startup failure is optional to DSH: normal chat survives but Ledger
tools are absent. Do not mount the old one-shot patch alongside this bundle (duplicate
server name). MCP stdout is JSON-RPC only; errors go to stderr.

Uninstall with `dsh plugin --profile desktop remove dsh-math-research-ledger`, then
reload/restart. After removal, you may delete the extracted bundle and its private Python
runtime. Uninstallation never removes `.math-research-ledger/`, workspace.yaml or ordinary
research files. Do not run uninstall against a different profile accidentally.

Host code and pip dependencies run locally. The server can read selected workspace files
and can write provisional research increments only when its write tools are explicitly
called. Models cannot accept results. No agent loop, model route, credential store, second
database, Git staging, commit or push is added. Keep research private state outside public
repositories, or locally excluded. Only the user chooses publication.
