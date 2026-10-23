# Windows lock failure correction

> Historical engineering evidence; results refer to the recorded revision, not a new acceptance.
> Machine-specific locations are generalized. See [current limitations](../../known-limitations.md).

2026-10-22. This is a code and artifact correction, not a new DSH Host acceptance.
No real research workspace, real Profile, authentication, ACL or model was used.

This report preserves the lock-correction evidence. See the
[current stage handoff](dsh-adaptation-handoff-2026-10-22.md) for fresh regression and
artifact checks and the later user-reported Windows Integrity diagnosis. The latter
explains a denied checkpoint-lock create, not a proven cause of the earlier timeout.
Bounded failure does not repair that independent permission boundary.

## Evidence and limits

The user supplied a DSH session summary: MCP initialization/tools/list succeeded,
but research_status timed out at tools/call. A separate sandbox command failed while
granting workspace access. That observation does not identify the server's actual
exception or prove that the command failure caused the MCP timeout.

Static inspection confirmed the actual chain:

```text
MCP research_status -> LedgerAdapter.call -> checkpoint_read
-> file_lock(state / .checkpoint) -> status service -> ledger projections
```

Before editing, the source, distributed wheel and main Bundle's installed module were
byte-identical (SHA-256 710a0d1ae5af908d416e5acd20c6d59fb2ee6f9456ba310b8d2881d0ce2c7ed1).
The old Windows access-denial/stat-error branch was reproduced with injected errors:
a test watchdog stopped it after 201 opens, with only one deadline check and zero
sleeps. The old stale-unlink-error branch also bypassed the wait/deadline logic by
inspection. The new tests cover both categories.

This confirms a real unbounded-loop defect in the shipped implementation. It does
**not** establish the root cause of the user's actual DSH timeout. No real Host was
restarted or called for this correction.

## Behavior changes

- Every acquisition retry checks a finite monotonic deadline and sleeps for at most
  20 ms, capped by remaining time. Invalid infinite/NaN/negative bounds are rejected.
- EEXIST establishes contention. Disappearance during inspection is a bounded retry,
  not a route around timeout checks. Unreadable lock state fails immediately.
- Ordinary access denial fails diagnostically. Windows errors 5, 32 and 303 receive
  at most three short retries, then fail; the overall deadline can end them sooner.
  An absent lock is never treated as evidence of an indefinitely running writer.
- Directory/create/stat/stale-cleanup/owned-cleanup/PID-initialization errors are
  reported as ResearchError with operation, lock path and original cause. Failed PID
  initialization closes the descriptor and attempts cleanup instead of orphaning it.
- Exclusive creation, stale recovery, atomic replacement and checkpoint serialization
  remain. The status read lock is deliberately retained: publication updates two
  indexes under a rollback journal. Skipping that lock would allow mixed generations;
  Windows also requires readers to close files before concurrent replacement.
- MCP runs deterministic service calls in an AnyIO worker thread. Bounded lock waits
  and synchronous IO therefore do not execute directly on the stdio event loop.
- The Bundle installer forces reinstall of the supplied wheel, avoiding stale local
  code when a rebuilt prerelease wheel retains version 1.1.0.

## Tests

| Case | Result |
|---|---|
| Create/release and exception cleanup | Passed |
| Existing lock contention and timeout | Passed |
| Denied create with absent lock, Windows/non-Windows | Passed |
| Windows 5/32/303 persistent denial and transient recovery | Passed |
| Stat permission/IO errors and repeated disappearance | Passed |
| Stale/owned cleanup denial, stale reclamation, failed PID write | Passed |
| Directory/open IO errors and shorter deadline | Passed |
| Finite bounds and failed atomic replace preserving old bytes | Passed |
| Status success and denied checkpoint lock, synthetic state unchanged | Passed |
| Four processes, 60 increments, cooperating readers and atomic writes | Passed |
| New lock tests | 23 passed |
| Earlier restricted regression excluding async MCP tests | 161 passed, 1 skipped (Windows junction permission); superseded by full results below |
| Focused async responsiveness and real MCP stdio | 14 passed, no skips/failures/errors, exit 0; includes both new heartbeat cases |
| Full regression in normal user environment with local IPC | 176 collected/executed, 176 passed, 0 skipped, 0 failures/errors, exit 0, 70.49 seconds |
| Ruff, format, mypy and git diff whitespace | Passed; 111 formatted files and 86 source files type-checked |

A prior restricted run stopped while Python initialized asyncio's Windows socketpair,
before the handler under test ran. Its 20-second faulthandler dump was retained; the
runner was stopped at 75 seconds. That initialization failure is separate from the
lock defect reproduced with mocks.

At the user's explicit request, the tests were then run with local IPC available
under ordinary user permissions, outside that restricted executor. No administrator
privileges, ACL changes, real DSH Host, research workspace or user Profile were used.
Both actual handler heartbeat cases and existing real stdio tests passed, followed
by the entire 176-test suite. This validates the changed revision rather than relying
on the older 151-pass baseline. JUnit XML, exit codes and parsed counts are retained
under ignored <local-evidence> (focused.xml/full.xml and their logs).

## Artifacts and next acceptance

The wheel was rebuilt, both repository-local Bundle copies and their private installed
service package were refreshed, and the actual release tarball was rebuilt. The lock
and MCP server bytes match between source, both wheels, both installed modules and
the inner wheel of the tarball. Both installed runtimes passed synthetic status and
injected Windows denial checks: four attempts, about 63 ms, unchanged synthetic files.
Runtime refreshes ran Python/pip only, never DSH Desktop or a Host.
The tarball contains the expected eight files; its inner-wheel scan covered 100 files
and found no private data, personal paths, credentials or local configuration.
The automated-test closing task rechecked its inner wheel and both installed Bundle
copies against the unchanged fixed source; all comparisons passed without rebuilding.
The artifact audit and installed-runtime results are retained under the ignored
<local-evidence> directory. These checks do not certify an already-running process.
Raw logs, injected-error proof and hash comparisons stay in ignored <local-evidence>

Existing running Python/DSH processes may still hold old imported bytecode; refreshing
files does not reload them. The user must arrange later Host restart/acceptance and
confirm that the updated code returns a bounded, diagnostic outcome under the actual
sandbox. Do not modify workspace permissions, move data or remove checkpoint locks
to make that test pass.

Changed for this correction: core/atomicio.py, mcp/server.py, the Bundle install.py,
two regression test modules and this report. No checkpoint protocol, tool schema,
human-authority gate, real Profile or research record was changed. No Git staging,
commit or push occurred.
