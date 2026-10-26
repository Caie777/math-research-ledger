# MathResearch Ledger for DeepSeek Harness

**Manual / single-workspace fallback.** The 1.2.2 default is the separate
Agent Host plugin (`host-plugin/` in the source archive), validated with DSH rc.3.
Do not enable both deployments in one profile. This Bundle intentionally keeps its
installation-time workspace pin and existing configuration-only behavior.

This configuration-only Bundle uses DSH's built-in `@deepseek-ai/dsh-mcp-client`
and an external persistent Python runtime (3.12 recommended). The server pins one
workspace at startup and exposes eleven tools in 1.2.2. DSH's native Plugins page controls OFF/ON.

This package is an **unrendered template**. Download the matching Python wheel and
source archive from https://github.com/Caie777/math-research-ledger/releases.
From the extracted source root, run:

```powershell
python scripts/prepare_dsh_config_bundle.py --workspace '<research-workspace>' --wheel '<local-wheel>'
```

The script installs the wheel non-editably into an external runtime, validates
versions, and renders local paths. Run its printed DSH installation commands from
ordinary PowerShell. Keep the rendered Bundle and runtime at stable locations.
Rendered configuration is private; do not publish it. See
`integrations/deepseek-harness/README.md` in the source archive for options and uninstall.

The current Agent Host adapter has Windows rc.3 isolated and real Profile read-only
cutover acceptance. Historical fallback results are not a compatibility claim for
rc.2 or for this eleven-tool package. Problem mutations are covered synthetically;
real-corpus mutations, macOS/Linux and GUI conversational acceptance are untested.
Installation does not initialize research state or change permissions, security
labels, authentication or Full Access.
