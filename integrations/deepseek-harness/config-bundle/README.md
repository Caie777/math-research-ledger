# MathResearch Ledger — Fallback for DeepSeek Harness

**Fallback / manual single-workspace integration — not the default.** The only
recommended **1.3.0** installation is the separate official Agent Host plugin,
displayed as **MathResearch Ledger for DSH** (`host-plugin/` in the source archive).
Its DSH rc.3 acceptance cited below is historical, not a new 1.3.0 gate result.
Choose this alternative only for an explicit installation-time workspace pin. **Remove the Host plugin
before installing this Bundle; do not install both in one Profile.**

DSH can show both installed dependencies as candidates even when OFF or neither
Bundle is selected. Disabling Host does not remove its candidate. The displayed
Fallback / 备用 title distinguishes this retained alternative; its stable package
ID `dsh-math-research-ledger` and MCP `serverName` `math-research-ledger` are unchanged.
This Bundle intentionally keeps its existing configuration-only behavior, without
a JavaScript adapter or custom lifecycle code.

This configuration-only Bundle uses DSH's built-in `@deepseek-ai/dsh-mcp-client`
and an external persistent Python runtime (3.12 recommended). The server pins one
workspace at startup and retains eleven tools in 1.3.0. DSH's native Plugins page
controls OFF/ON. **Protocol-neutral, DSH-first, other Harnesses on demand** retains
standard MCP and best-effort Codex compatibility; this manual fallback introduces
no Core/MCP breaking change or research-schema migration.

This package is an **unrendered template**. Download the matching Python wheel and
source archive from https://github.com/Caie777/math-research-ledger/releases.
From the extracted source root, run:

```powershell
python scripts/prepare_dsh_config_bundle.py --workspace '<research-workspace>' --wheel '<local-wheel>'
```

The script prepares only this explicitly requested fallback, prints a strong Host
removal warning, installs the wheel non-editably into an external runtime, validates
versions, and renders local paths. It never invokes DSH or changes the real Profile.
Run its printed installation commands with the normal Desktop-installed `dsh` in
ordinary PowerShell, not in a sandboxed DSH shell:

```powershell
# Replace desktop with the target Profile; skip removals for absent packages.
# Remove Host first; OFF alone is not removal.
dsh plugin --profile desktop remove dsh-math-research-ledger-host
# Existing fallback upgrade only:
dsh plugin --profile desktop remove dsh-math-research-ledger
dsh plugin --profile desktop add '<rendered-bundle-path>'
```

To return to the recommended Host path, remove `dsh-math-research-ledger`, then
prepare/add Host instead. Do not manually edit Profile files.
Keep the rendered Bundle and runtime at stable locations.
Rendered configuration is private; do not publish it. See
`integrations/deepseek-harness/README.md` in the source archive for options and uninstall.

**Historical acceptance is not current deployment state.** Recorded **2026-10-26**
Agent Host Windows rc.3 isolated and real Profile read-only cutover results on the
1.2.2 development implementation are historical,
not evidence of the currently installed version or active Bundle. The last reported
disk inspection on **2026-10-30** found both package dependencies at 1.2.1 and
neither selected; this snapshot is not evidence of a 1.3.0 deployment. These
instructions have not upgraded or enabled them. Historical fallback results
are not a compatibility claim for rc.2 or for this eleven-tool package. Problem
mutations were covered synthetically; real-corpus mutations, macOS/Linux and GUI
conversational acceptance are untested. The source archive retains legacy overlays
and test-only smokes for reproducibility, not extra installation steps.
Installation does not initialize research state or change permissions, security
labels, authentication or Full Access.
