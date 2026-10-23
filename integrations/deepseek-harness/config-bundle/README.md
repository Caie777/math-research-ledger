# MathResearch Ledger for DeepSeek Harness

This configuration-only Bundle uses DSH 0.2.1-rc.2's built-in
`@deepseek-ai/dsh-mcp-client`. There is no JS wrapper, dependency glue or private
Python runtime inside the Bundle. Python 3.12 is recommended; the persistent runtime
is external. The workspace is pinned during preparation, not selected by tool arguments.

From a checkout/sdist, use `scripts/prepare_dsh_config_bundle.py` with an existing
workspace and a local MathResearch Ledger wheel. See the integration README for commands.
The script installs the wheel non-editably and renders paths; it never initializes
research state, edits DSH Profiles or invokes DSH. LICENSE is copied from the source root.
`--no-install --python PATH` explicitly reuses an already prepared interpreter.
Wheel, runtime and Bundle versions must agree; mismatch is an error.

Run the printed installation/upgrade commands from ordinary PowerShell, using the
Desktop-installed dsh command. Do not run DSH plugin installation from a sandboxed DSH
shell. Keep both the rendered directory and external runtime in place. The native
Plugins page controls ON/OFF; disabling/removing the Bundle does not delete research data.

Real DSH Desktop installation and Host acceptance remain pending after this code handoff.
Successful rendering or MCP stdio smoke is not Desktop acceptance. The plugin does not
change permissions, security labels, authentication or Full Access settings.
