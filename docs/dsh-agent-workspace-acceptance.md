# DSH Agent workspace acceptance

2026-10-26; 1.2.2 development, formal package identity still 1.2.1.
All commands run from the tool checkout. The actual installed official Desktop
packages are **0.2.1-rc.3**; the user approved testing that version after discovery.
rc.2 is unverified for this new adapter. No real Profile, credentials, research
workspace, persistent Python runtime, Codex integration or Core was modified.

## Capability and implementation

The official Session header supplies a validated absolute, deep-frozen `cwd`.
Desktop session creation supplies Host workspace metadata; persistence/resume
restores that header. The adapter never reads process cwd or model tool arguments
to choose scope. `agent/created` is serially awaited inside the factory's
rollback-covered publication, before callers can drive the new Agent.

The 27-line runtime adapter reads that header and awaits
`agent.ctx.plugin(@deepseek-ai/dsh-mcp-client, config)`. The client owns names,
discovery, protocol negotiation, tools, instructions and teardown. Configuration
contains only an absolute Python executable. Child cwd is the session root; args
are `-B -m math_research.mcp.server --workspace .`. The same server owns all eleven
schemas, scope assertions, read/write enforcement and Ledger behavior.

Load the Host plugin before creating its Agents. There is no retrofit of existing
Agents. Missing Host cwd rejects setup with a `NO_WORKSPACE` diagnostic without
spawning a child; it does not guess a path. An existing empty root still registers
eleven tools and returns the server's `NO_WORKSPACE` normally.

## Actual isolated Host matrix

The test composes official Cordis, AgentRegistry, AgentLoop, SessionStore,
ToolRuntime, system prompt, LLM service without a provider, and the official JSONL
session persistence backend rooted only in disposable test storage. No Profile or
account is copied. The real factory, scope and MCP transport are used.

| Case | Observed result |
|---|---|
| Different workspace concurrent | A/B each 11 tools and one active Python MCP process, distinct PID; own state only; both cross-root assertions rejected |
| Same workspace concurrent | Two Agents/processes; equal status/search; concurrent writes create distinct Problems, count 3; generation changes and lock releases |
| Uninitialized | 11 tools, `NO_WORKSPACE`, no init or crash |
| Ordinary subdirectory | `NO_WORKSPACE`, no parent fallback |
| State-directory exact-root | `NO_WORKSPACE`, no parent alias binding |
| Agent create | Tools registered before the actual factory create call returns |
| First-turn availability | Actual driver's `agent/request` boundary sees 11 tools; a test gate stops before provider I/O; no model call |
| Agent dispose | Official scope disposal closes the active transport/process |
| Resume | Official disk persistence restores workspace-A header while Host cwd is B; starts a new correctly bound process |
| Shell cd immutability | Official Agent-local shell executes cd to B; changing Host process cwd too leaves existing MCP bound to A |
| Profile/plugin OFF | Normal Cordis entry disposal removes listener: new Agent has 0 Ledger tools; existing Agent retains 11 until its own dispose |
| Profile/plugin ON | New Agent gets 11 tools |
| Restart | Entire isolated Host Context disposed/recreated; persisted session resumes with correct root and 11 tools |
| Missing Host root | Setup fails closed; no process starts |

The SDK started and closed one additional process per connection during startup;
only one active process per Agent remained at the acceptance boundary. This is
official connection/protocol handling, not an adapter process pool or manager.

Profile/plugin ON/OFF here exercises the actual underlying Cordis entry lifecycle,
not a real Desktop GUI toggle or installation into the user's Profile. Existing
Agent immediate unload is intentionally not claimed. A complete Desktop UI restart,
real-workspace cutover, macOS/Linux and network paths remain separate acceptance.

## Regression and package checks

Completed checks: focused Host/config-only packaging suite **22 passed**; the
strengthened actual shell/whole-Host restart test **1 passed**; full pytest
**480 collected, 479 passed, 1 skipped, 0 failed** in 418.25 seconds. The existing
POSIX permission test skips on Windows; the actual rc.3 Host test ran in the full
suite. Ruff and format passed across 142 files; mypy passed across 96 source files;
`git diff --check` passed. The public five-file npm tarball was unpacked and its
actual adapter passed the complete Host matrix too. Python wheel contents match
the unchanged Core sources. Private logs and fingerprints stay ignored in dist/.

The focused test can be enabled with `MRL_DSH_EXECUTABLE`, `MRL_DSH_NODE_MODULES`
and `MRL_DSH_PYTHON`. For an ASAR Desktop installation the executable is its
Electron binary; the test uses its supported `ELECTRON_RUN_AS_NODE` mode. The modules
path is that installation's DSH node_modules. `--basetemp` must be a new directory
under checkout `dist/`, and no real DSH home is used.

```powershell
python -m pytest tests/core_contracts/test_dsh_host_plugin.py tests/core_contracts/test_dsh_config_bundle.py -p no:cacheprovider --basetemp 'dist/_run/dsh-focused-new'
python -m pytest -p no:cacheprovider --basetemp 'dist/_run/dsh-full-new'
ruff check src tests scripts benchmarks
ruff format --check src tests scripts benchmarks
python -m mypy
git diff --check
python -m build
```

Public npm packaging uses a copy of `host-plugin/` with the root LICENSE added,
retaining the Python placeholder. The rendered local package selects a runtime
only, never a workspace, and is private. The five-file tarball excludes runtime,
state, local config and evidence. The old seven-file config-only Bundle is retained
unchanged in behavior, documented as manual/single-workspace fallback. Do not load
both in one profile: inherited and local server names could conflict or duplicate.

Official sources: installed rc.3 compiled Agent factory, session header, Cordis
effect loader and MCP client implementation; upstream
[Agent reference](https://github.com/deepseek-ai/deepseek-harness/tree/master/packages/core/agent)
and [MCP subsystem](https://github.com/deepseek-ai/deepseek-harness/blob/master/docs/subsystems/mcp.md).
Online master is supporting context, not evidence that another version passed.
