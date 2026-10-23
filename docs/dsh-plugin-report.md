# DSH Bundle engineering acceptance

Historical engineering record. The authoritative current status and resume plan are in
[the 2026-10-22 handoff](dsh-adaptation-handoff-2026-10-22.md). Test counts below identify
earlier runs; this stage's fresh results and package hash are recorded there separately.
Latest user-reported Desktop evidence confirms installation/service startup and nine
registered tools, but real workspace status fails creating its checkpoint lock across
a Low/Medium Integrity boundary. Real Windows acceptance is incomplete and paused.

2026-10-22. The initial Bundle engineering baseline passed runtime installation,
tarball inspection, isolated Host ToolRuntime acceptance and 151 regression tests.
The later [Windows lock correction](windows-lock-fix.md) changes the lock and MCP
scheduling code. Its focused async/stdio tests (14) and full regression (176) now
pass in the normal-user local-IPC environment. No new real DSH Host acceptance has
been performed; the earlier Host baseline does not certify that pending real-session check.
Complete Desktop GUI and real workspace user-session acceptance remain outstanding;
registration alone is insufficient. No registry publication,
Git staging/commit/push, real research work or authentication change is part of this work.

## Verified integration

The historically inspected Desktop, CLI and MCP client were 0.2.1-rc.2
(Node 24.21.0 / pnpm 11.28.5); this archive does not re-query the real installation.
The supported native package contract is `package.json -> dsh.bundle.patch`.
The Desktop-installed `dsh plugin --profile PROFILE add PATH` command maintains the
dependency and ordered bundle selection. The native Plugins page controls Profile-wide
enablement; HMR applies it live when enabled, otherwise restart is required.

A thin deployment adapter delegates connection, discovery, tools and disposal to the
official `@deepseek-ai/dsh-mcp-client`. The existing Python MCP server supplies all nine
schemas and all Core Services. No agent loop, model route, second ledger or duplicate
business decisions were introduced. Security gates, ledger models, Codex manifests,
MCP schemas and Skills are unchanged. The later correction updates the core lock and
MCP scheduling implementation as documented in windows-lock-fix.md.

The isolated acceptance used the official CLI to install into a
fresh synthetic Web-backed Profile, then the actual installed Host ToolRuntime:
initial ON = 9, OFF = 0, ON again = 9. Status reported one synthetic Problem/object;
search returned the synthetic PROBLEM-0001. No model was called. The earlier
`socketpair` and install EPERM observations were execution-environment restrictions,
not an unresolved integration defect. The engineering baseline regression passed
**151 tests**, with no skips or failures, using explicit temporary directories and
cacheprovider disabled (exit 0).

References: [official packaging](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/publish),
[CLI](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/README.md),
[Desktop](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/desktop/README.md),
[MCP bridge](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md),
[Plugin Manager](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/boot/plugin-manager/README.md).

## Independent Python runtime

The interrupted Bundle environment contained only pip and no runtime pointer.
After checking for an active installation and exclusive access to its interpreter image,
only that incomplete Bundle-local .venv was removed. Installation ran as a hidden
background process, with stdout, stderr, PID and final exit status recorded separately.

The online attempt exited 1 after DNS resolution failed while fetching dependencies.
A second background invocation used the installer's supported offline options with
compatible dependency wheels already present in the local pip download cache. It
exited **0**, installed all dependencies inside the Bundle, and saved .runtime.json
pointing to its own .venv interpreter. No ACL, network, account or system settings changed.

An actual `-I -B` import check confirms both `math_research.mcp.server` and `mcp` load
from that Bundle environment, not the development .venv-win. `pip check` reports no
broken requirements. Like an ordinary Python venv, this uses the machine's base Python;
the distributable does not contain a portable Python interpreter binary.

## Actual release package

The actual `npm pack` was rerun **after** independent runtime installation. Its output
and tarball agree on exactly eight regular files:

```text
package/LICENSE
package/README.md
package/cordis.patch.yml
package/index.mjs
package/install.py
package/package.json
package/runtime/math_research_ledger-1.1.0-py3-none-any.whl
package/transport.mjs
```

The Python wheel was rebuilt with current public README metadata before packing.
All 100 files, including wheel contents, were inspected. No research data, private
absolute paths, credentials, raw transcripts, runtime pointer or local configuration
were found. The already-installed .venv and .runtime.json were excluded by the npm
files allowlist. Generated environments, logs, wheelhouse, reports and synthetic
Profiles remain under ignored dist/ and are not release members or Git changes.

## Historical execution record (fresh rerun in the handoff)

| Check | Result |
|---|---|
| Independent runtime installation/imports | Passed; offline background installer exit 0, isolated imports and pip check passed |
| Actual post-install tarball | Passed; eight members, npm/tar agreement and nested-wheel safety audit |
| Baseline regression before lock correction | 151 passed, no skips/failures, exit 0; current correction results are in windows-lock-fix.md |
| Earlier lock-corrected regression | 176 passed, 0 skipped/failures/errors, exit 0; focused async/stdio subset 14 passed; current rerun is in the handoff |
| Historical native isolated Host with Bundle Python, before lock correction | Passed; real ToolRuntime ON/OFF/ON = 9/0/9 and readonly status/search, no model; not rerun for the later lock correction |
| Actual child-process interpreter evidence | Four MCP launches, all using the Bundle .venv; MRL_PYTHON override unset |
| Native PluginManager changes | Both OFF and ON returned application=applied, no warnings |
| Synthetic workspace integrity | All files byte-identical before/after; one Problem/object; search hit PROBLEM-0001 |
| Ruff lint/format, mypy, Node syntax, git diff whitespace | Passed |
| Actual Desktop GUI/user session | Later user report: installed/service started, nine tools registered; real workspace status denied, search not accepted |
| macOS/Linux Host | Unverified |

The first restricted attempt refused pnpm's Profile/store symlink creation with EPERM.
After explicit user authorization, native installation, the isolated Host and full
regression ran outside that sandbox with ordinary user permissions. No administrator
privileges, ACL changes or authentication changes were used. No isolated Host probe
remains running. Current execution evidence is retained under dist/_run; it contains only
engineering
artifacts and synthetic data. The install logs retain both the failed online attempt
and successful offline run; runtime-import.json, release-audit.json,
host-bundle-python.json, host-assertions.json and pytest.status.json record the results.
No real Profile, credential store, Ledger or notes repo was accessed in this closing task.

## Reproduction and remaining boundary

See the [DSH installation guide](../integrations/deepseek-harness/README.md) and
[Bundle manual](../integrations/deepseek-harness/bundle/README.md) for build, explicit
runtime installation, native ON/OFF, diagnostics and uninstall commands.

Use a writable temporary directory and disable pytest's cacheprovider when an old
temporary directory/cache has stale permissions. For Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force dist/_run/tmp | Out-Null
$env:TMP = (Resolve-Path dist/_run/tmp).Path
$env:TEMP = $env:TMP
python -m pytest -q -p no:cacheprovider --basetemp dist/_run/bt
```

For an offline runtime, prepare a wheelhouse separately and run
`python install.py --no-index --find-links /absolute/wheelhouse`. Run long installs
as a background task with separate stdout/stderr, PID and an exit-code record;
poll progress instead of imposing a short download timeout. Do not confuse a failed
network lookup with a missing dependency release.

The existing `host-smoke.cjs --cycle` uses the real installed Host and official
PluginManager with an isolated Profile/synthetic workspace. It asserts initial ON,
OFF and final ON, calls only status/search, and records only the Ledger child
process executables/PIDs to prove which Python was launched. Reports stay private.

The complete real Desktop GUI/user-session check remains outstanding regardless of isolated
Host success. Do not claim an already-open session refreshed, normal-user chat was
observed, or real research calls passed from an isolated ToolRuntime test.

## Change audit

Modified: .gitignore, MANIFEST.in, README.md, README.zh-CN.md,
integrations/deepseek-harness/README.md, docs/finalization-report.md and
docs/research-workspaces.md. The last two changes redact local machine path examples
from public documentation; stored historical research provenance is untouched.

Added: docs/dsh-plugin-report.md; integrations/deepseek-harness/bundle/{package.json,
cordis.patch.yml,index.mjs,transport.mjs,install.py,README.md};
integrations/deepseek-harness/host-smoke.cjs; scripts/build_dsh_bundle.py;
tests/core_contracts/test_dsh_bundle.py. The Host probe additionally asserts initial ON
and records only the actual Ledger process executables/PIDs for runtime evidence.

Removed the temporary docs/dsh-handoff.md after incorporating its measured results.
dist/ remains entirely ignored and untracked. No git add, commit or push was executed;
the source working tree deliberately remains modified/untracked for user review.
