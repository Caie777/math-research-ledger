# Read-only MCP checkpoint consistency — 1.2.1 development

Work is based on released `v1.2.0`, commit
`15e6b095446d07365053466d13e6a64c43c01c89`. The formal version stays 1.2.0;
this is an uncommitted development change, not a release or renewed real-workspace
DSH acceptance. All commands run from the tool repository. Only synthetic state is used.

## Original contract and protected races

`checkpoint_transaction` holds the state-dir `.checkpoint.lock`, durably writes
`.checkpoint-pending.json`, then publishes the project Episode index and the scoped
candidate index. Exceptions restore both prior byte sequences; raw sources remain.
Recovery is a separate trusted-human operation under that same writer lock.

The old MCP `checkpoint_read` took the same exclusive lock for the entire operation.
It prevented readers from seeing an Episode without its candidates, crossing a complete
publication between separate reads, or seeing transient state that was later rolled back.
Its journal guard also rejected interrupted publication after a writer died. The lock
did not coordinate arbitrary local filesystem edits or every legacy human API.

`research_request_acceptance` persists a request and is not a pure read. It retains the
exclusive guard and is never automatically replayed. Its checks and write stay in that
non-replayable operation; no separate model-callable acceptance/precheck API is added.

## Read algorithm

The six read-only tools and Episode `dry_run=true` use
`consistent_checkpoint_read(state, operation)`:

1. Require existing state; strictly inspect the journal without creating anything.
2. Capture the generation marker and an ephemeral content fingerprint, rejecting a
   journal or changed generation while constructing the fingerprint.
3. Execute the entire materialized MCP operation, including its bounded output projection.
4. Capture the same fence again. Return only if both generation and content match.
5. On change, discard the result and replay the whole pure operation, at most three times,
   sleeping 20 ms between attempts. Exhaustion returns a diagnostic ResearchError.

An observed journal always fails closed. Stable operation errors retain their original
validation/integrity meaning; an error produced during a changed generation can be retried.
Missing or unreadable state/control metadata is never repaired or initialized by a reader.

The content fingerprint uses existing `Ledger.objects()` qualified versions for records,
dependencies and referenced proof/source/artifact bytes, plus SHA-256 of persisted JSON,
JSONL and YAML metadata and optional workspace metadata. No identity, dependency or premise
projection is reimplemented. Unreachable retained blobs need no additional whole-tree
byte sweep. The fingerprint is ephemeral and is not an object ID, version pin or database.

The existing public `Ledger.source_version()` is **unchanged**. A synthetic legacy Claim
without persisted timestamps showed that parsed default timestamps can change its result
despite identical stored bytes. Using it directly would reject otherwise stable status reads.
The new fence hashes stored metadata bytes and existing object versions instead. This does
not change the separate source-version checks already inside packet/verification services.

## Why a generation marker is necessary

A failing writer can publish intermediate indexes, restore their exact prior bytes and
remove the journal entirely during one reader operation. Source/content equality alone
would miss that ABA window. Writers therefore atomically replace the 32-byte random
`.checkpoint-generation` after the durable journal and before publication work. They never
roll it back, even after failure or a duplicate/no-op write attempt. Recovery advances it
before restoring indexes as well. If the marker cannot be advanced, no publication body runs.

Thus, a reader overlapping a supported publication either observes a journal, observes a
different generation, or completed all its reads before publication began. Rollback cannot
make the fence look unchanged. Changing content without a new checkpoint epoch is also
detected by the content fence. These are optimistic checks, not a persistent snapshot copy.

Pre-marker workspaces remain readable with an absent marker, without migration or writes.
All concurrent checkpoint writers must use this protocol: reload old installed/cached
writers before concurrent use. Arbitrary uncoordinated filesystem changes, old binaries
and restoring a backup require quiescence; this is not a filesystem security boundary.

## Windows sharing and retained boundaries

A deterministic synthetic reproduction confirmed Windows returns Win32 5 when an ordinary
read handle briefly blocks atomic replacement. `atomic_write_text` now retries only known
Windows access/sharing/lock errors (5/32/33), at most three 20-ms sleeps. It still uses the
same fsynced temporary file and atomic replacement. Persistent denial preserves the original
target and fails; no permission, ACL, owner or integrity label is changed.

The writer lock, rollback journal, authoritative JSONL checks, human recovery and provisional
authority gates remain. Data idempotency tests still compare every research byte; they now
explicitly allow only the advancing coordination marker on mutating attempts. Pure-read and
preview tests continue to compare **all** state bytes, including the marker.

## Validation and performance

All commands run from the tool repository root. No real research state or real
DSH Profile is used. The change adds 44 parametrized test cases (37 checkpoint-read and
7 Windows atomic-replacement cases), taking collection from 334 to 378. Existing tests
also assert the new read-only semantics and distinguish coordination-marker changes from
research-record writes. Final full pytest collects 378 cases: **377 passed, 1 skipped,
0 failed/errors**, exit 0, in 615.85 seconds. The skip is the physical POSIX permission
test on Windows. It uses fresh synthetic temporary paths, `-p no:cacheprovider` and
normal-user local IPC; no administrator permission or security-setting changes.

The first full run had one old assertion treating an advancing coordination marker on
invalid ingest as a research-record write (376 passed, 1 skipped, 1 failed). That assertion
now explicitly verifies marker advancement and identical original research bytes; pure
preview still permits no changes. The targeted correction and the entire final suite pass.
Ruff check and format check cover `src tests scripts benchmarks` (137 files formatted);
mypy passes all 95 production files. `git diff --check` exits 0 (only existing CRLF/LF
normalization warnings, no whitespace errors).

Controlled thread/process tests exercise a half-published checkpoint, complete publication
during an actual MCP callback, rollback ABA with identical restored source version,
process termination leaving a journal, trusted-human recovery, and two concurrent writer
processes publishing six Episodes while a reader polls. Stable reads execute once;
continuous change exhausts three attempts. Unreadable journal/marker and malformed marker
fail diagnostically. The existing worker-thread tests keep the event loop responsive.

The six pure tools and Episode preview succeed under portable write-denial mocks, with
both absent and present generation markers. They leave every state byte unchanged.
The physical POSIX directory/file mode test is present but skipped on Windows; no Linux
execution is claimed. Windows readonly attributes are not a write-permission test.

A fresh local development wheel installs with `[mcp]` into a clean venv; `pip check` passes.
Its actual stdio MCP session discovers all nine unchanged schemas. Six pure tools and
Episode preview succeed under a process-wide Python audit hook denying state writes:
zero unexpected write attempts and identical whole-state byte inventories. A negative
save-note call is denied, preserving the writer boundary. This is OS-API denial simulation,
not a claim of DACL/MIC enforcement. All 95 packaged production Python files match current
source byte-for-byte. The wheel has 102 members, no runtime/cache/state members or private
path matches, and SHA-256
`2ba1af13f0f6055514355ca01a2f23434562dd75e3331e6eebaf13f0a9607288`.
It deliberately retains version 1.2.0 and must not replace the released 1.2.0 artifact.

The restricted process reports Low Integrity (SID S-1-16-4096). Direct calls using the
installed adapter succeed for all six pure tools without changing state. However, an
ordinary creation probe in that synthetic directory also succeeds: this is not an
OS-enforced read-only Low Integrity test. The actual Low Integrity stdio/DSH Host check
is **not passed**: a minimal `asyncio.run` probe times out after 10 seconds in
`socket.accept -> _fallback_socketpair -> _make_self_pipe`, before any MCP handler.
No Desktop, real Profile, model or authentication is invoked. Automatic approval review
rejected a proposed security-label change on a new synthetic fixture; that command did
not execute. The user then chose to retain mock validation and record the limitation.
No ACL, owner or integrity label was changed, and no alternative security mutation was
attempted. Real DSH synthetic Host acceptance remains unavailable this run.

The timing corpus is synthetic: 3 Problems / 270 objects / 750 files / 7,569,519 bytes, plus
a larger 1,500-object / 3,000-file / 30-MB case. These match sizes, not private research content.
A complete raw-file sweep took about 0.51/2.24 seconds warm and 5.8/25.3 seconds cold,
respectively. That alternative was rejected; no cache, FTS, snapshot service or new database
was introduced. Paired runs alternate the old exclusive read wrapper and the new adapter,
assert identical outputs and report medians of three samples (milliseconds):

| Objects | Tool | Exclusive read | Optimistic read |
| --- | --- | ---: | ---: |
| 270 | status | 207.789 | 596.634 |
| 270 | search | 1298.081 | 2225.346 |
| 270 | context | 2107.383 | 2992.266 |
| 1500 | status | 694.320 | 2076.247 |
| 1500 | search | 2065.781 | 3452.279 |
| 1500 | context | 3304.466 | 4696.775 |

One content-fence sample costs approximately 208/693 ms respectively. Two fences add
measurable work, particularly to cheap status queries; this is a documented tradeoff,
not a performance improvement or an SLO. Padding represents unindexed retained blobs;
these synthetic cases do not establish every possible artifact-heavy corpus cost.

Local raw logs, JUnit results, timing JSON, build/install records and smoke scripts are
retained under ignored `dist/_run/readonly-checkpoint-20261023/`. Nothing was staged,
committed, pushed, tagged or published.

## Change size and next step

Production changes are limited to three existing files: `ledger/checkpoint.py`
(132 added / 4 removed lines), `mcp/adapter.py` (8 / 4), and `core/atomicio.py` (15 / 1):
155 additions / 9 deletions, net +146 lines. There are no new production modules,
dependencies, schemas, tools, version formats or changes to Codex manifests/Skills.
Four existing test files are updated, one test module and this report are added, and
architecture/limitations/archive-index documentation is updated. HEAD remains the
baseline on `main`, with 10 tracked modified and 2 untracked public files, nothing staged.
Builds, venvs, private timing fixtures and raw logs remain ignored under `dist/`.

The next separate hardening task should establish authoritative workspace scope/pinning
before multi-root selection. Multiple roots should not expand permitted scope implicitly.
Neither is implemented here. First arrange safe synthetic Low Integrity Host acceptance;
POSIX physical-permission/concurrency execution also remains to be run on a Linux host.

## Deferred work

Real existing-workspace Low/Medium Integrity repair and acceptance, workspace scope,
multi-root choice, Bundle installation/peer dependencies, doctor/backup, acceptance
authentication, legacy API removal and retrieval caches remain out of scope.
