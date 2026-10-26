# Codex session-workspace acceptance

Date: 2026-10-26. Target: 1.2.2 development, with formal package/plugin identity
still 1.2.1. This is local engineering acceptance, not a release or Plugin Directory
submission. All commands were run from the tool checkout. Only isolated synthetic
workspaces and a fresh Codex home were used; no real project configuration or
research state was changed. DSH integration was not changed or exercised.

## Deployment under test

Windows, Codex CLI/app-server **0.160.0**, clean non-editable Python **3.12.10**.
The runtime installed the newly built wheel with its MCP dependencies offline.
Its installed Python sources matched the checkout byte-for-byte; this was not an
old installed wheel or an editable import from the development checkout.

The prepared Codex-native package contains its compatibility manifest, `.mcp.json`,
the shared `continue-research` skill and LICENSE. The manifest references
`./skills/` and `./.mcp.json`. The generated MCP command selects the persistent
runtime's Python; arguments are:

```text
-B -m math_research.mcp.server --workspace .
```

There is no configured cwd or workspace environment. The native Host supplies the
new session's process cwd, which is resolved once and pinned for that server's
lifetime. This is measured 0.160.0 behavior, not an official stable project-root
placeholder/API. Runtime processes need not be shared between sessions.

The portable Agent Plugins root `plugin.json`/`mcp.json` are deliberately excluded
by `prepare_local_plugin.py`. That format uses a different Codex loader, with a
plugin-directory cwd default. Installing the raw checkout is not this deployment.
The [official packaging guide](https://developers.openai.com/plugins/build/plugins)
describes both portable and supported Codex compatibility layouts. Follow the
[installation guide](codex-mcp.md) for the exact package used here.

## Exact-root fix and compatibility

MCP `resolve_workspace()` still calls shared `state_at(root)` for an explicit
`--workspace`, `MRL_WORKSPACE` or legacy `SMR_WORKSPACE`. It now requires the returned
state directory's parent to equal the canonical explicit root. If that check fails,
tool calls return `NO_WORKSPACE`; the server and tool registration remain available.

The counterexample was startup cwd at an initialized workspace's
`.math-research-ledger` directory with `--workspace .`. The shared helper recognizes
state-directory aliases and previously selected the parent's Ledger. That path now
fails the parent-equality check and returns `NO_WORKSPACE`, with no fallback or init.

`core/paths.py` and `state_at()` were not changed. Legacy aliases and implicit
cwd/ancestor discovery remain tested when no explicit source exists. Canonical
case/junction equivalence, assertion-only tool workspace arguments and
`WORKSPACE_OUT_OF_SCOPE` rejection remain intact. No data format, dependency,
checkpoint, authority, verification, lifecycle service or tool schema changed.

## Native Host acceptance matrix

These tests use the actual Codex app-server plugin loader and MCP transport. No
model turn or real Desktop GUI interaction was used. The isolated configuration
has no direct MCP and uses an allowlist of OS environment settings, without copying
user authentication, workspace environment overrides or a real Codex home.

| Case | Observed result |
|---|---|
| Different workspace concurrent | A/B each expose 11 tools, distinct Python processes and their own fixture state; cross-workspace assertion rejected |
| Same workspace concurrent | Two servers concurrently create distinct synthetic Problems; both see the same 3 Problems; generation changes and writer lock is released |
| Status/search | Both read operations succeed on the initialized synthetic Ledger |
| Ordinary uninitialized directory | 11 tools register; call returns `NO_WORKSPACE`; no state created |
| Ordinary subdirectory | `NO_WORKSPACE` even with initialized parent |
| State-directory counterexample | `NO_WORKSPACE` from `.math-research-ledger` cwd; no nested state created |
| Plugin OFF | Shared skill unavailable, 0 Ledger tools; new OFF session starts no Ledger Python process |
| Plugin ON | Shared skill available, exactly 11 Ledger tools, one server registration |
| OFF/ON existing session + native reload | Skill/tools switch 0/11; idle processes remain and are reused on ON |
| Session dispose/archive | Native `thread/archive` releases that thread's Python children |
| Host/transport disposal | All observed owned Python children exit |
| No-change reload | Keeps the same processes/root; does not rebind |
| Shell cd immutability | Native read-only `command/exec` changes shell cwd from A to B; already running MCP remains A |
| Restart/new session | A fresh workspace-bound server starts correctly, with 11 tools |
| Windows paths | Absolute, case-equivalent and junction-equivalent roots succeed |

OFF is tool/skill deactivation, not guaranteed immediate OS process termination.
The previous isolated lifecycle investigation also found that unsubscribe alone
did not dispose a retained thread; archive/Host close did. No adapter process manager
or rebind mechanism was added to change native Host retention behavior.

The earlier isolated interpreter-update experiment found that normal plugin
reinstall left the existing server on its old interpreter; a new session used the
replacement. Explicit reload rebuilt the old server with the replacement without
changing its session root. Same-version remove/add refreshed cached native config.
These are version-specific observations; use a fresh session/restart after updates.

## Verification and reproduction

Focused packaging/scope/real-stdio regression: **68 passed**, including every explicit
source, both state-directory aliases, implicit ancestor discovery, canonical aliases
and the formerly failing module-entry startup case.

The separate clean Python 3.12 package smoke verifies all installed Python source
bytes, actual eleven-tool stdio discovery, status/search, cross-root rejection,
zero-write reads, all three missing-root cases and retained shared alias behavior.
`pip check` and installed-module location checks passed.

Full pytest: **475 collected, 474 passed, 1 skipped, 0 failed** in 738.35 seconds,
exit 0. The skip is the existing platform-specific permission test. Ruff lint and
format check passed across 140 files; mypy passed across 96 source files;
`git diff --check` passed. Wheel/sdist inspection and an entry-by-entry comparison
of a wheel rebuilt from sdist accompany the final local commit's delivery report.
Private logs, JUnit, runtime, synthetic profiles and build artifacts stay in ignored
`dist/`, not this public source package.

Reproduce from the checkout after installing the development/test dependencies:

```powershell
python -m pytest
ruff check src tests scripts benchmarks
ruff format --check src tests scripts benchmarks
python -m mypy
git diff --check
python -m build
python scripts/codex_plugin_smoke.py --python '<new-wheel-runtime>/Scripts/python.exe' --output 'dist/_run/codex-acceptance-new'
```

The evidence directory must not exist. The script creates a temporary marketplace,
Codex home and synthetic Git/initialized/empty roots inside it; it uses native
configuration writes/reload for plugin policy, not direct server injection. The
runtime must have this checkout's freshly built wheel with MCP installed.

## Remaining deployment boundary

Real project direct MCP was not removed and no real configuration was edited. A
later authorized cutover should back up config, install the prepared native package
with the new runtime, disable the old direct entry and stale bundled-server override,
then open a fresh session at the exact research root. Verify eleven tools, reported
root and scoped status/search; verify OFF yields zero tools before retiring the old
entry permanently. Keep the backup for rollback.

Actual Desktop GUI switch interaction and the real-workspace cutover remain untested
for this deployment. macOS/Linux Host behavior and UNC/network paths are untested.
Neither this acceptance nor installation changes permissions, integrity labels or
authentication. Research initialization requires explicit user authorization.
