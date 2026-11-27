# MathResearch Ledger for DSH

The recommended DSH 0.2.x integration. The Host adapter binds the existing Python
MCP server to each Agent's immutable session root, with eleven scoped tools. It
contains no research logic and does not migrate any Ledger data.

## Install

Standard installation uses PyPI for Python and npm for the DSH Host. Until the
first registry release, use the GitHub Release downloads described below.

1. Install Python 3.11+ (3.12 recommended). Create a dedicated venv outside the
   plugin directory, source checkout and research workspace, at a location you choose.
   In ordinary PowerShell, for example:

   ```powershell
   $runtime = '<runtime-directory>'
   py -3.12 -m venv $runtime
   & "$runtime\Scripts\python.exe" -m pip install 'math-research-ledger[mcp]>=1.5.0,<1.6'
   ```

   On macOS/Linux use `python3 -m venv` and `<runtime-directory>/bin/python`.
2. In the target DSH Profile, use **Plugins → Add plugin** and enter
   `dsh-math-research-ledger-host` as the package name. Enable **MathResearch Ledger for DSH**.
   Do not use a file path or npm alias if you want native registry updates. No
   private package, rendering or workspace selection is needed.
3. Make the runtime visible to the **DSH Host process**: put its `Scripts` (Windows)
   or `bin` directory first on its PATH, or set the optional `python` field in the
   native Profile override below. Activating a venv in an unrelated terminal does
   not change PATH for an already-running Desktop app. Fully restart the Host after
   changing its environment or replacing the installed bundle.

The plugin selects the first executable `python.exe` (Windows) or `python3`
(other platforms) in absolute directories on the Host's PATH. A local override
is authoritative when present; stale overrides do not fall back silently. On
activation, the adapter checks that the executable starts and can import the
Ledger CLI and MCP dependencies. Probe, init and MCP use isolated Python (`-I -B`):
use a venv or normal site-packages, not `PYTHONPATH` or `pip install --user`.
`MRL_RUNTIME_UNAVAILABLE` indicates a missing, unusable or incomplete runtime.
`MRL_RUNTIME_INCOMPATIBLE` reports the installed Ledger version if it is not a
stable **1.5.x** release (at least 1.5.0, below 1.6). Use the same interpreter
DSH selects, with `-m pip install --upgrade 'math-research-ledger[mcp]>=1.5.0,<1.6'`,
and retry with a new Agent. The Host and Python patch versions need not match.
The bundle does not download Python, install dependencies, or modify PATH.

### Offline installation

From [GitHub Releases](https://github.com/Caie777/math-research-ledger/releases),
use the public Host `.tgz` in **Add plugin** and install a compatible wheel with
`[mcp]` using the intended interpreter. For a disconnected machine, also bring
its Python dependency wheels and point `pip` at that wheelhouse. A `.tgz` install
is not eligible for DSH's registry version checks.

### Optional local override

Use the selected Profile's DSH Loader override (normally its `cordis.patch.yml`
under `$DSH_HOME/profiles/<profile>/`). Add or update **one override row** in that
file, preserving unrelated rows. Do not edit the installed bundle or add a second
`insert` row. Substitute the real absolute executable path without shell quotes
inside the YAML value:

```yaml
- id: math-research-ledger-host
  name: dsh-math-research-ledger-host
  config:
    python: '<runtime-directory>/Scripts/python.exe'
```

On macOS/Linux use `bin/python`. To switch back to PATH discovery, remove this
local override (or set its `config: {}`). The path lives only in the user's
Profile, never in the distributed package.

## Use

Open the intended workspace and create/resume an Agent. With no pointer at the
exact session root, the plugin starts no Python and exposes no Ledger tools.
Explicitly opt in using the human composer command:

```text
/math-research-ledger enable [workspace-relative directory]
```

This initializes only missing state, defaulting to `./.math-research-ledger`, and
writes `.math-research-ledger-link` with a relative state directory. An existing
state directory is bound without reinitialization. An invalid or escaping pointer
fails without fallback; there is no scan, ancestor search or model-selectable root.
New Agents at the same root mount the official MCP client at the bound Ledger root.
OFF affects new Agents; dispose existing Agents to close their scoped transports.

## Upgrade, move, or uninstall

- **From link/tarball to npm (once):** remove the old Host package in the target
  Profile, then add `dsh-math-research-ledger-host` by package name. If migrating
  from the single-workspace fallback, remove `dsh-math-research-ledger` too if
  installed; OFF is not removal. Keep a valid `python` override, or clear/update
  a stale one. No change to the activation pointer is needed.
- **Subsequent updates:** open the registry-installed bundle's **Versions** section
  in DSH Plugins to check and install a compatible Host update. This does not
  update Python; only change the runtime if needed by the new Host's requirements.
- **If only the DSH installation moved:** reuse the unchanged Python environment.
  If the old link or tarball source broke, reinstall by name or from an available
  offline tarball rather than editing the bundle contents.
- **If Python or the venv moved:** recreate the environment with a working base
  Python at the destination and reinstall a compatible runtime with `[mcp]`. Update
  Host PATH or the Profile override. Do not copy/move a venv and assume its base
  interpreter references, launchers, or editable installs still work.
- **Uninstall:** remove `dsh-math-research-ledger-host` using DSH's normal package
  management. Remove only its override and, optionally, its dedicated runtime if
  nothing else uses it. Do not delete the workspace or its activation pointer.

The bundle, Python environment, and research workspace are three independent
locations. Do not rewrite Ledger data, history, provenance, or valid activation
pointers during a plugin/runtime move. For the deliberately pinned fallback and
validation boundaries, see the DSH integration guide in the source archive.
