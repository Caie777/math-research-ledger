# MathResearch Ledger for DSH

The official Agent Host plugin is the **only recommended / default installation**
in **1.5.0** for DSH **0.2.x**. **MathResearch Ledger for DSH** is its Host UI
name; the product remains MathResearch Ledger. **Protocol-neutral, DSH-first, other
Harnesses on demand** means the standard MCP contract is retained, Codex is
best-effort compatibility and other adapters need a real use case.

Install the matching Python wheel with MCP dependencies into a persistent
runtime for eleven tools. No Core/MCP breaking change or research-schema migration
is introduced.
The adapter contains no research logic: it awaits the official MCP client inside
each new Agent's scope, using the Host's immutable `agent.session.header.cwd`.
The existing Python server supplies the shared research workflow instructions.

## Workspace-gated activation

The Host entry may stay globally ON. ON alone grants no Ledger tools: it only
permits a workspace that owns an activation pointer to use them. There is no
ancestor search, workspace scan or automatic Ledger creation.

For each new Agent, the Host reads exactly one tiny pointer in the exact session
root, `.math-research-ledger-link`. The pointer contains a session-root-relative
Ledger state directory such as `.math-research-ledger` or
`research/foo/.math-research-ledger`.

| Exact session-root state | Result |
|---|---|
| no pointer | 0 Ledger tools and no Python MCP process |
| valid pointer | one scoped MCP client bound to that Ledger; exactly eleven tools |
| invalid or escaping pointer | Agent setup fails with a clear diagnostic; no substitute directory |

Enable Ledger only with the native human command, not by mentioning it in a model
prompt:

```text
/math-research-ledger enable [workspace-relative directory]
```

The command initializes the default `./.math-research-ledger`, or the requested
directory inside the exact session root. Absolute paths outside the root, `..`,
and symlink/junction escapes are rejected. Initialization runs the normal
`math_research` CLI once; without an existing pointer the research tools never
appear and Python is never started. There is intentionally no resident bootstrap
tool schema.

Prepare a new local package with an already installed persistent Python runtime:

```powershell
python scripts/prepare_dsh_host_plugin.py --out '<new-local-plugin-directory>' --python '<persistent-python>'
# In ordinary PowerShell: remove the old fallback if installed in this Profile.
dsh plugin --profile '<profile>' remove dsh-math-research-ledger
# Host upgrade only: remove an existing Host installation before re-adding.
# dsh plugin --profile '<profile>' remove dsh-math-research-ledger-host
dsh plugin --profile '<profile>' add '<new-local-plugin-directory>'
```

Preparation installs no runtime, selects no workspace and never initializes Ledger.
The unrendered public package contains `__MRL_PYTHON__`: configure the absolute
Python path before activation, or render it with the helper. Rendered packages
contain a local runtime path and must stay private. Uninstall through normal DSH
`plugin --profile '<profile>' remove dsh-math-research-ledger-host`.

Preparation and its printed installation instructions prepare **only this Host
package**, never the fallback. Use the normal Desktop-installed `dsh` command in
ordinary PowerShell, not a sandboxed DSH shell; skip removal for packages not installed.

**Remove**, rather than merely disable, the old `dsh-math-research-ledger` config-only
Bundle before adding this one. Both installed dependencies can appear as installation
candidates even when OFF or unselected. They are alternative deployments, not two
clients to install together. The old Bundle remains a non-default **Fallback / manual
single-workspace integration**; no compatibility code has been removed.

The **2026-10-30** disk inspection found both dependencies at 1.2.1 and neither Bundle
selected. This historical snapshot and the acceptance below do not establish a
completed 1.3.0 migration or today's deployment state. These instructions do not
upgrade or enable the real Profile, and must not be implemented
by manually rewriting its files.

Load this Host entry before creating the Agents it should serve; after install,
enable or reload, create/resume a new Agent. `agent/created` is an awaited DSH
factory barrier. Without a pointer the Agent simply has no Ledger tools; with one,
tools are ready before the first model request. Existing Agents are not retrofitted.
Profile/plugin OFF removes the creation listener: new Agents have no Ledger tools,
while already-created Agents retain their scoped client until disposal. ON affects
subsequently created Agents and remains necessary for the `/math-research-ledger`
command.

Each Agent owns at most one active connection/process. Agent disposal closes its
official MCP transport and tools.

The process cwd is the bound Ledger root and args are
`-B -m math_research.mcp.server --workspace .`. Shell cwd changes do not rebind it.
Resume uses the saved session header and the same pointer, not ambient cwd. A
missing pointer yields zero tools rather than a `NO_WORKSPACE` client. A malformed
or escaping pointer refuses Agent setup without spawning a process or guessing
another directory. No parent discovery, model-selected scope, silent init, ACL
changes, authentication handling or automatic authority promotion is added.

## Public 1.5.0 package

The public Host npm tarball contains **eight files**: `index.cjs`, `activation.cjs`,
`package.json`, `cordis.patch.yml`, `README.md`, `LICENSE`, `locale/en.json` and
`locale/zh.json`. The locales supply the **MathResearch Ledger for DSH** Host title;
the stable package ID `dsh-math-research-ledger-host`, MCP server name and runtime
binding are unchanged. The seven-file 1.3.0 layout and five-file 1.2.2 layout are
historical. No Python runtime, rendered local configuration, research state or
private evidence belongs in the public tarball.


## Historical validation boundary

**Historical acceptance (2026-10-26; 1.2.2 development):** the recorded Windows rc.3 synthetic factory run covered
isolation, concurrent writers, exact roots, first-request readiness, disposal,
persistence/resume and ON/OFF. The recorded real rc.3 Profile cutover also passed
read-only access, isolation, resume, Host restart and new-Agent OFF/ON with zero
Ledger writes. That run used the official Desktop Host entry, not GUI conversational
turns. It is not a fresh test or evidence of today's installed/active Profile.
rc.2, macOS/Linux and UNC are unverified. See `integrations/deepseek-harness/README.md`
in the source archive for the complete matrix, reproduction and retained fallback.
The separate **2026-10-30** closeout on a 1.2.2 checkout is also historical; neither
record substitutes for the final 1.3.0 gate or proves Desktop migration has occurred.
