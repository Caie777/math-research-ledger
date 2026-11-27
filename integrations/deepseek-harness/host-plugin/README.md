# MathResearch Ledger for DSH

The recommended DSH 0.2.x integration. The Host adapter binds the existing Python
MCP server to each Agent's immutable session root, with eleven scoped tools. It
contains no research logic and does not migrate any Ledger data.

## Install

From [GitHub Releases](https://github.com/Caie777/math-research-ledger/releases/tag/v1.5.1),
use `dsh-math-research-ledger-host-1.5.1.tgz` and the matching `math_research_ledger`
wheel with the `[mcp]` extra. The original v1.5.0 Host tarball predates this fix.

1. Install Python 3.11+ (3.12 recommended). Create a dedicated venv outside the
   plugin directory, source checkout and research workspace, at a location you choose.
   In ordinary PowerShell, for example:

   ```powershell
   $runtime = '<runtime-directory>'
   py -3.12 -m venv $runtime
   & "$runtime\Scripts\python.exe" -m pip install '<matching-wheel-filename>.whl[mcp]'
   ```

   On macOS/Linux use `python3 -m venv` and `<runtime-directory>/bin/python`.
   Install the wheel non-editably; the finished runtime does not require source code.
2. In the target DSH Profile, use **Plugins → Add plugin** with the absolute path
   to the Host `.tgz`, then enable **MathResearch Ledger for DSH**. This is a normal
   DSH package install, not a link to an extracted source directory. No rendering,
   symlink setup, install-time Python path, or workspace selection is needed.
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
`MRL_RUNTIME_UNAVAILABLE` indicates a missing, unusable or incomplete runtime;
update/clear the override or repair the environment and retry with a new Agent.
The package does not download Python, install dependencies, or modify PATH.

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

- **From a prepared legacy Host:** remove its package in the target DSH Profile,
  then add the fixed public tarball. Remove `dsh-math-research-ledger` if the old
  single-workspace fallback is installed; switching it OFF is not removal.
  Clear any stale `python` Profile override or update it for the new runtime.
- **If only the DSH installation moved:** reuse the unchanged Python environment.
  If DSH has a broken old package link or tarball source, add the portable tarball
  through the native manager again at its new location, rather than repairing the
  bundle's contents. Keep the tarball available for package-manager reinstalls.
- **If Python or the venv moved:** recreate the environment with a working base
  Python at the destination and reinstall the matching wheel with `[mcp]`. Update
  Host PATH or the Profile override. Do not copy/move a venv and assume its base
  interpreter references, launchers, or editable installs still work.
- **Uninstall:** remove `dsh-math-research-ledger-host` using DSH's normal package
  management. Remove only its override and, optionally, its dedicated runtime if
  nothing else uses it. Do not delete the workspace or its activation pointer.

The bundle, Python environment, and research workspace are three independent
locations. Do not rewrite Ledger data, history, provenance, or valid activation
pointers during a plugin/runtime move. For the deliberately pinned fallback and
validation boundaries, see the DSH integration guide in the source archive.
