# MathResearch Ledger for DeepSeek Harness

This configuration-only Bundle uses DSH's built-in `@deepseek-ai/dsh-mcp-client`
and an external persistent Python runtime (3.12 recommended). The server pins one
workspace at startup and exposes nine tools. DSH's native Plugins page controls OFF/ON.

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

Windows Desktop DSH 0.2.1-rc.2 / Python 3.12.10 Host acceptance passed, including
synthetic writes, real-workspace read-only access and OFF/ON. DSH macOS/Linux and
formal real-corpus writes are untested. Installation does not initialize research
state or change permissions, security labels, authentication or Full Access.
