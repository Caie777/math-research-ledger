# MathResearch Ledger Agent Host plugin

The 1.2.2 default for DSH **0.2.1-rc.3**. Install the matching Python wheel with
MCP dependencies into a persistent runtime for eleven tools.
The adapter contains no research logic: it awaits the official MCP client inside
each new Agent's scope, using the Host's immutable `agent.session.header.cwd`.
The existing Python server supplies the shared research workflow instructions.

Prepare a new local package with an already installed persistent Python runtime:

```powershell
python scripts/prepare_dsh_host_plugin.py --out '<new-local-plugin-directory>' --python '<persistent-python>'
dsh plugin --profile '<profile>' add '<new-local-plugin-directory>'
```

Preparation installs no runtime, selects no workspace and never initializes Ledger.
The unrendered public package contains `__MRL_PYTHON__`: configure the absolute
Python path before activation, or render it with the helper. Rendered packages
contain a local runtime path and must stay private. Uninstall through normal DSH
`plugin --profile '<profile>' remove dsh-math-research-ledger-host`.

Disable the old `dsh-math-research-ledger` config-only Bundle before enabling this
one. They are alternative deployments, not two clients to install together.
The old Bundle remains a single-workspace/manual fallback.

Load this Host entry before creating the Agents it should serve; after install,
enable or reload, create/resume a new Agent. `agent/created` is an awaited DSH
factory barrier: after creation resolves, tools are ready before the first model
request. Existing Agents are not retrofitted. Profile/plugin OFF removes the
creation listener: new Agents have no Ledger tools, while already-created Agents
retain their scoped client until disposal. ON affects subsequently created Agents.

Each Agent owns one active connection/process. An additional short-lived startup
process was observed with the tested SDK/Host before its active connection; the
adapter adds no process manager. Agent disposal closes its official MCP transport
and tools.

The process cwd is the Agent's recorded root and args are
`-B -m math_research.mcp.server --workspace .`. Shell cwd changes do not rebind it.
Resume uses the saved session header, not ambient cwd. A known but uninitialized
root, ordinary subdirectory or state directory registers eleven tools and returns
`NO_WORKSPACE`. Missing Host cwd rejects Agent setup with that diagnostic without
spawning a process. No parent discovery, model-selected scope, silent init, ACL
changes, authentication handling or automatic authority promotion is added.

Windows rc.3 synthetic factory acceptance covers isolation, concurrent writers,
exact roots, first-request readiness, disposal, persistence/resume and ON/OFF.
The real rc.3 Profile cutover also passed read-only access, isolation, resume,
Host restart and new-Agent OFF/ON with zero Ledger writes. This used the official
Desktop Host entry, not GUI conversational turns. rc.2, macOS/Linux and UNC are
unverified. See `integrations/deepseek-harness/README.md` in the source archive for
the complete matrix, reproduction and the retained fallback deployment.
