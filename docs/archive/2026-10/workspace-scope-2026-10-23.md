# MCP workspace scope — 1.2.1 development

Date: 2026-10-23 (Asia/Shanghai). All Git, code, test and build orchestration commands
run from the tool repository root. Host subprocesses use explicitly selected synthetic
directories. No real research workspace, notes repository, DSH Profile, credential,
ACL, owner or integrity label is read or changed for this task.

## Independent checkpoint commit

The initial working tree matched the preceding read-only checkpoint audit: 10 tracked
modified files and 2 untracked public files, nothing staged, on `main` at released
`15e6b095446d07365053466d13e6a64c43c01c89`.
Only those 12 named files were staged, inspected and committed as:

`e0748d3e16783470c71d8679f0dca63a34478b58`
`fix: allow consistent read-only checkpoint access`

Cached diff/stat/check and post-commit status were inspected; the tree was clean before
scope development began. Previous evidence was 377 passed / 1 skipped. No push, remote
mutation, amend or version change occurred. The previous report remains a historical
record of its then-uncommitted state; scope work below is not part of that commit.

## Audit of the original call chain

```text
MCP initialize/tools/list
  -> validated tool arguments
  -> per-call client_workspace
       --workspace, else MRL_WORKSPACE / SMR_WORKSPACE
       else session.list_roots() if advertised: one supported local file URI
       else absolute tool workspace
       else process cwd -> ancestors
  -> resolve_workspace -> shared state_at -> LedgerAdapter -> shared services
```

There was no mandatory session pin. Startup flag/environment selections already took
precedence, but were resolved per call; a conflicting tool path was silently ignored.
In the absence of those selections and usable Host roots, any model-supplied absolute
path containing valid state could select a different Ledger. This is an MCP workflow
scope defect, not a claim of escaping a filesystem sandbox.

The public Codex `mcp.json` launches `python -B ${PLUGIN_ROOT}/scripts/smr_mcp.py`;
the launcher preserves cwd and may re-exec `MRL_PYTHON`. The inspected local cached
configuration sets only `MRL_PYTHON`, not a workspace pin. Historical Codex 0.160.0
evidence records package-directory cwd and no advertised MCP roots. The current source
does not assume any automatic Host session-root token or injection.

The installed Python MCP SDK 1.30.0 has `ClientCapabilities.roots`,
`ServerSession.list_roots()` and a client `list_roots_callback`. This establishes API
availability, not universal Host support or authorization. Stdio tests advertise zero,
one and two roots; none can expand this implementation's scope. No claim is made that
fresh Codex or DSH advertised roots during this task's pinned calls; the new server
does not request them. Roots remain a future integration point.

CLI selection remains separate: `cli.main` resolves its explicit workspace, supports
private-state paths, uses `find_workspace_root` and shares `state_at`. The older
`resolve_cli_workspace_root` helper is not called by this MCP path. The separate
`resolve_workspace_path` helper bounds artifact/file paths inside a workspace; it does
not select or authorize an MCP root. The existing CLI/MCP selection policies share
state-format validation and are not merged into a new workspace manager.

## Authority model and path contract

```text
server startup --workspace > MRL_WORKSPACE > legacy SMR_WORKSPACE
    > startup cwd/ancestor discovery
    -> capture one canonical state/root, or retain NO_WORKSPACE

each tool call -> validate schema -> optional exact-root assertion
    -> WORKSPACE_OUT_OF_SCOPE before opening another Ledger
    -> adapter/services for the captured state only
```

The startup selection happens once in `create_server`, not on the first model-selected
path. Later environment/cwd changes, new state directories or changed root offers do
not rebind it. An invalid explicit startup selection does not fall through to another
corpus. Without a usable startup scope, tools/list still exposes nine tools but calls
fail with actionable `NO_WORKSPACE`; no state is initialized. MCP roots, including a
single root, are not a scope source in this version. A roots-only Host must provide
an explicit startup pin. This intentionally removes the older roots-selection fallback
along with the unsafe model-argument fallback.

All nine tool fields/types/limits remain; only the workspace description and server/skill
guidance change. Normally omit `workspace`. A supplied field is a compatibility assertion
of the exact root, never a request to select another Ledger. It uses `expanduser` and
filesystem `Path.resolve`, with relative forms anchored to the pinned root. Trailing
separators, `..` returning to the same root, Windows drive/path case and equivalent
symlink/junction aliases are accepted. Parents, children (even initialized Ledgers),
siblings, escaping paths, state-directory paths and malformed paths are rejected.
There is no implicit child-root inheritance. Rejections do not call the target Ledger
resolver/services, echo its path or expose its contents.

Startup root aliases resolve to their canonical target. Retargeting that alias afterward
does not change the captured root; asserting its new different target is rejected.
Redirected private-state directories are refused at startup, including Windows junctions.
This is not authentication against arbitrary local code, live filesystem replacement or
other trusted actors mutating the deployment. No registry, ACL system, token, watcher,
root manager, selection heuristic or new production module is introduced.

CLI remains unrestricted by this model-callable contract. Its explicit second-workspace
read succeeds in regression while the same path is rejected by the pinned MCP session.

## Host integration and deployment limits

The local Codex 0.160.0 app-server was exercised with a fresh repository-local
`CODEX_HOME`, local marketplace and staged current-source plugin, using the existing
`prepare_local_plugin.py` and `codex_plugin_smoke.Host`. A private generated `mcp.json`
adds `--workspace A`; it is not a change to the public manifest or user installation.
The test's Python/runtime paths and synthetic absolute roots stay in ignored evidence.

| Synthetic Codex configuration | Result |
| --- | --- |
| Explicit startup pin A | Nine tools discovered |
| Pin A; status/search/context omit tool workspace | All succeed, status identifies A |
| Pin A; tool requests initialized Ledger B | WORKSPACE_OUT_OF_SCOPE, no B content |
| New ordinary project, new HOME, opt-in plugin without pin | Nine tools discoverable, no scope |
| Unpinned ordinary project; tool requests valid A or B | Both NO_WORKSPACE; no state created |

These are actual app-server tool calls without a model, not Desktop GUI acceptance or
automatic session-root discovery. The test invoked native enablement only in its isolated
HOME. No global real-user pin, plugin refresh or Profile edit was made. Existing installed
copies do not acquire this fix merely because source changed.

Codex deployments whose startup cwd is the plugin directory need a deliberate private
`--workspace` or `MRL_WORKSPACE` setting and reload. A shared deployment pin binds every
session using it: keep native project-only activation, rather than globally enabling a
research pin in ordinary projects. No invented `${WORKSPACE_ROOT}` token is used.
The configuration mechanisms are documented in
[official MCP configuration](https://learn.chatgpt.com/docs/extend/mcp) and
[desktop plugin packaging](https://developers.openai.com/plugins/deploy/desktop-only).
Those sources do not establish automatic current-project injection.

DSH was inspected only as configuration/source: its existing `transportConfig` appends
`--workspace config.workspace` when provided and preserves `process.cwd()`. Thus a
future deployment of this Python fix can use the existing private config field for the
same pin. No Bundle adapter, installer, distributed wheel, real Profile, Low Integrity
environment or DSH Host is updated/tested here. There is no new DSH compatibility claim.

## Tests, wheel and change size

There are 30 additional collected cases: 29 in the new scope test module and one additional
roots-count case in the existing transport test. Coverage includes omitted/exact/relative/
normalized paths, Windows case, actual Windows junction aliases and retargeting, redirected
state, sibling/parent/child/escape refusal, rejection before services across all nine tools,
fixed flag/env/cwd behavior, missing scope, zero/one/multiple offered roots, and independent
CLI selection. Fixtures and sentinel contents are synthetic only.

- Focused real-stdio/scope/plugin/workspace/async regression: **55 passed**, exit 0.
- Full pytest: **408 collected, 407 passed, 1 skipped, 0 failures/errors**, exit 0,
  417.63 seconds. The sole skip is the existing physical POSIX permission test on Windows;
  Linux execution is not claimed.
- Ruff check and format check cover `src tests scripts benchmarks`: exit 0,
  138 files already formatted. mypy: 95 source files, exit 0. `git diff --check`: exit 0.
- A wheel built from an isolated current public-source copy installs offline with `[mcp]`
  into a fresh venv; `pip check`: no broken requirements. Actual installed-package stdio
  smoke discovers all nine matching schemas, runs pinned status/search/context, accepts
  an equivalent pin, rejects B, and leaves both entire state byte inventories unchanged.
- All 95 packaged Python files equal current source bytes. The 102-member wheel has no
  venv, cache, private state or personal-path matches. SHA-256:
  `82471263b5ae79179d203b54b324e92c9bb7888018fc7438f5a6d2abc0108244`.
  Version remains 1.2.0: this local development wheel must not replace a released asset.

Production scope diff is two existing files: `mcp/server.py` 44 additions / 48 deletions,
and `mcp/adapter.py` 2 / 2, total 46 / 50, net **-4 lines**. No core/ledger/CLI logic,
dependencies, formal versions or public manifests change. The skill, README translations,
architecture, limitations, Codex guide, DSH contract note and archive index are updated.
One test module and this report are added; one existing transport test module is updated.

At handoff, `main` remains at `e0748d3`: 11 tracked modifications, 2 untracked public files,
zero staged files. Scope work is deliberately uncommitted. Raw logs, JUnit XML, temporary
Codex HOMEs/marketplaces, venvs, build copies and synthetic state remain ignored under
`dist/_run/workspace-scope-20261023/`. No remote operation, push, tag or release occurs.

## Next step

Do not move directly into automatic multi-root selection. First review this diff and
choose a supported private startup pin for the intended Host, refresh that deployment
separately, and validate project-only activation. If future roots are used, establish the
Host-authorized stable allowed set before deciding which member to select. Multiple
directories containing state are not permission to access them. Multi-root, DSH Bundle,
ACL/Integrity repair, doctor, cache and all other deferred work remain out of scope.
