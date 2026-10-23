# Finalization and acceptance report

Historical product/finalization baseline. For the current, paused DSH Windows status,
fresh engineering checks and remaining acceptance, see the
[2026-10-22 handoff](dsh-adaptation-handoff-2026-10-22.md).

Local machine path examples in this public report are redacted; historical Ledger provenance is unchanged.

2026-10-21–22 (Asia/Shanghai). Tool/plugin development and synthetic engineering only.
No new real mathematical research, formalization or human acceptance was conducted.

## 1. Identity

Display name **MathResearch Ledger**. Distribution/plugin ID `math-research-ledger`,
version `1.1.0`. MCP server identity `math-research-ledger`, version `1.1.0`.
The nine raw `research_*` names are unchanged. Python imports remain `math_research`:
there is no namespace conflict and renaming imports would break integrations for no benefit.

## 2. Repositories and initial audit

Started at `<tool-checkout>`, branch `main`, HEAD
`77753f98901b929bad9200b99798ae13d0e28bb5`, with clean tracked status. Initial distribution
and server identity used the previous brand; console scripts were smr, math-research and
smr-mcp. No plugin package existed. Global Codex registration pointed to the renamed-away
source path. Initial resolver selected .math-research; metadata supported only v1.

The tool origin now points to `https://github.com/Caie777/math-research-ledger.git`.
History was preserved; no new repository or rewritten history, and no push.
The complete initial reference audit and full inventories are retained locally under
`.local-eval/finalization/`, excluded from publication. Remaining old-name references
are explicit migration/compatibility identifiers, a frozen hash token or labelled
historical documentation, not active installation paths.

## 3. CLI

Canonical `math-research-ledger`; legacy compatibility aliases `smr` and `math-research`
are retained and labelled in help/docs. Canonical transport executable
`math-research-ledger-mcp`; legacy smr-mcp remains. All entry-point help/import smokes
passed. Obsolete distribution metadata was removed from the development venv and the
new editable distribution was refreshed without removing legacy command compatibility.

## 4. Codex plugin package and native state

Root plugin.json + mcp.json + skills/ are canonical. A minimal .codex-plugin/plugin.json
compatibility manifest references the same product and server configuration. No hooks,
daemon, custom switch, or public Plugin Directory submission was added.

Native local marketplace `math-research-ledger-local` is installed from
`<tool-checkout>\.local\codex-marketplace`. The cached plugin is under
`%USERPROFILE%\.codex\plugins\cache\math-research-ledger-local\math-research-ledger\1.1.0`.
The final native config is **enabled = false**. Enable through Plugins UI or the native
`plugins."math-research-ledger@math-research-ledger-local"` config, then start a fresh session.
Developer staging uses a stable venv interpreter through MRL_PYTHON; the portable command
remains bare python. A normal install needs the transport dependencies in its interpreter.
[Installation details](codex-mcp.md).

## 5. Legacy global registration

Removed only the old `structured-math-research` global MCP after plugin-owned calls
worked. Other plugins/MCPs were preserved. There is no duplicate Ledger global server.

## 6. OFF/ON host results

Codex CLI `0.160.0`, actual native app-server sessions:

- OFF: zero Ledger servers/tools; normal thread initialization succeeds. A fresh
  ordinary model turn returned OFF-SMOKE-OK without Ledger tools.
- ON: exactly nine Ledger tools, working status/context and provisional ingest.
- Natural-language prompt only: “继续这个已有研究问题，先了解当前进度。” automatically
  selected research_status followed by research_context_packet.
- Final package was checked again and left OFF; unrelated config was structurally verified.

Codex starts plugin stdio in the installation directory and this client does not
advertise MCP roots. Tool arguments now support optional `workspace`, and skill/server
instructions make the agent supply its current harness root. The natural-language test
did so automatically. Other hosts can supply standard MCP roots or preserve child cwd.
Explicit server selection stays authoritative, missing state never auto-initializes, and
ambiguous roots/refs fail explicitly. The currently open desktop chat was not reloaded;
UI toggle rendering was not independently driven. Native installation/enabled config and
fresh actual hosts were verified, without claiming a desktop UI interaction.

## 7. Workspace migration design

Explicit v1 .math-research → v2 .math-research-ledger. New init creates only canonical
state and root metadata/instructions; no fake objects, ordinary-file relocation or AGENTS
overwrite. It is idempotent. Legacy reads require no writes; init gives a migration path.
Conflicts, unknown targets, version mismatches and pending migration journals fail closed.

The offline migration uses a same-volume atomic directory rename plus atomic metadata
publication with a durable rollback journal. Interrupted publication requires explicit
rollback; failure tests cover restoration. Stop other writers before migrating. Pure
path moves keep the frozen v1 identity hash token, remap old archive prefixes only for
operational reads, and never rewrite historical absolute provenance.

## 8. Actual workspace discovery and final layout

The user confirmed the renamed canonical root `<research-workspace>`. Discovery found one
nonempty corpus (750 files) under Research/math-research/.math-research, plus a separate
zero-file legacy child under Research/riemann-surfaces. No competing nonempty ledger,
partial corpus or merge was inferred. The empty child was preserved, not repurposed.

```text
<research-workspace>\
├─ existing ordinary research directories/files (unchanged)
├─ math-research-notes\       existing independent publication Git repo
├─ AGENTS.md                  local-only
├─ workspace.yaml             local-only, workspace_version: 2
└─ .math-research-ledger\     migrated private state
```

Only the identified nonempty private state moved. Old source-side AGENTS/workspace.yaml
remain byte-identical ordinary metadata. Open the unified root for unified research;
an explicitly opened separately initialized child is still its own workspace.

## 9. Corpus integrity

| Measurement | Before | After |
|---|---:|---:|
| Files | 750 | 750 |
| Total bytes | 7,569,519 | 7,569,519 |
| Unified objects | 270 | 270 |
| Problems | 3 | 3 |
| Changed / missing / unexpected files | — | 0 / 0 / 0 |
| Changed object versions | — | 0 |
| Surfaced artifact references missing | 0 / 30 | 0 / 30 |

Canonical inventory hash (same before/after):
`4fa07cf1f3994416b15c3ec3f87ba29d56f492e6eec732cbac8cf7a9bfcb3883`.
Source version (same before/after):
`3c034969d089e767bb5b5b32acdb89dc9c094a5e2dc742e9003b7284e9d8cd8c`.

Every file SHA256 and all 270 object versions were compared. Retained asset bytes and
operational references remained intact. Two existing “upstream unproved research target
dependency” cautions stayed unchanged; no history was repaired or accepted.
The final local real-workspace stdio smoke discovered the canonical root, nine tools,
270 objects and three Problems with v2 metadata. No real payload was sent to a model.

## 10. User files and publication ownership

27,045 ordinary file paths/sizes/mtime values matched before/after; no ordinary research
file was moved, renamed, edited or deleted. Ledger raw state also matched per-file hashes.
The notes repository's HEAD and Git index stayed unchanged through migration.

The actual root is not itself a Git repo. As confirmed by the user, publication remains
nested at `<research-workspace>\math-research-notes`, whose remote is independently
`https://github.com/Caie777/math-research-notes.git`.

| Repository | Responsibility |
|---|---|
| math-research-ledger | Tool/plugin source, synthetic tests and public-safe engineering reports |
| math-research-notes | Mature mathematical results/notes deliberately selected by the user |

Private state and root metadata live outside the publication repo. Defense-in-depth local
exclusions were added only to that repo's `.git/info/exclude`: .math-research-ledger/,
workspace.yaml, AGENTS.md. Its public .gitignore was not changed. No private Ledger files
were found tracked; final notes status is clean. No research Git add/commit/push was run.
Synthetic tests also verify capture leaves a Git index unchanged and creates no commit.

## 11. Episode audit before this change

ResearchEpisode already had structured object groups, explicit dependency/relation hints,
input-version pins, raw Markdown preservation and provisional staging. The deterministic
parser recognized ordinary/numbered objects and legacy handoff planning. It did not
explicitly represent Confirmed Research Increment vs Next Research Directions or a
recoverable typed round delta. Thus the complete checkpoint distinction was not machine
guaranteed; Next Directions containing recognized object headings could be extracted.
The prior MCP initialize response had no server-wide instructions.

## 12. Machine-readable checkpoint increment

ResearchEpisode now carries state_delta[] with Added/Revised/Invalidated/Refuted/Still Open,
reference, statement, original SHA256 and source line spans, plus separately stored
advisory next_research_directions. Existing representations are reused; no second truth
ledger was added. Full raw Markdown is preserved. Empty optional fields do not alter
legacy object versions. Explicit local references cannot promote advisory-only objects.

Candidates/dependencies exclude Next Directions even when it contains Claim/RESULT
headings or relation wording. Delta assertions are source-reported: they do not change
canonical targets, confer verification or grant human authority. Typed bounded checkpoint
views are available through research_get_object, with explicit omissions and paging.

## 13. Publication transaction

Checkpoint metadata ingestion is serialized with the same deterministic services for
all harnesses. Archive/proposal indexes have a durable rollback journal and MCP read lock.
Injected publication failure restores both indexes; crash recovery fails closed and is
available only through trusted-human ingest recover. Raw source bytes remain retained
if metadata publication fails. No per-turn dependency rebuild/index rewrite was added.

## 14. Capture and retention semantics

Research hot paths stay light; meaningful checkpoints consolidate through one ingest.
Save-note is a sparse provisional capture of one important claim/gap/failure/evidence,
not every-round memory. Store broadly, retrieve selectively: preserve raw Episodes,
proofs, failed attempts, counterexamples, rejected/deferred routes and revision history.
No per-chat or per-tool-call recording hook or aggressive deletion policy was added.

## 15. MCP safety and instructions

Initialize now includes stable harness-agnostic guidance: status/context before substantial
work, exact trust/version/freshness checks, checkpoint vs sparse note capture, advisory
planning/review, state ownership, no automatic Git publication, checked != accepted,
canonical != verified, and human-only authority. AGENTS supplements these instructions.

Nine direct tools remain. Read-only annotations exclude the three writes. No shell,
arbitrary file-write, compiler or model-callable human acceptance capability was added.
64 KiB protocol-envelope bounds, structured actionable errors, strict input schemas,
explicit ambiguity failures and stdout-only JSON-RPC are exercised in real stdio tests.
Automated-scope/provisional-write/human-authority enforcement remains in the services.

## 16. DeepSeek installation and authentication

Installed Desktop Harness and official dsh-mcp-client both `0.2.1-rc.2`; no additional rc
package was installed. The reusable one-shot patch uses process.cwd() and the same MCP
server/core. No persistent Ledger profile mount was added; omitting the patch leaves OFF.

The initial default headless route lacked an API key. Official docs and installed code
confirmed that headless disables stored credentials/authorization/account consumers.
The user authorized reuse of Desktop login. Official getState reported credential-stored
in `%USERPROFILE%\.dsh`. The optional desktop-account.patch.yml restores those services
for the invocation and selects deepseek-account. The real model run succeeded through
that existing account. No raw token was read/printed/copied into this repository; no new
credential store, global login change, sign-out or API-key fallback was performed.
[DeepSeek setup](../integrations/deepseek-harness/README.md).

## 17. Cross-harness continuity

PASS, with precise scope: A used controlled MCP calls through a fresh real Codex
app-server (no model call); B used a fresh real account-authenticated DeepSeek model;
C used a fresh real Codex model with only the natural-language continuation prompt.
Neither B nor C received earlier chat history. All payloads were synthetic engineering.

- A wrote Episode EPISODE-6E3541285D2A87D5 and marker object CLAIM-P93571AD088FE95A7.
- B recovered A via status/search/context/object, wrote Episode EPISODE-22F6DDE4322B6FB7
  and Gap CLAIM-PC0597D3183D7E34B, with Uses pointing to A. Next Directions stayed advisory.
- C automatically called status/context, recovered both markers and B→A dependency,
  and made no state write. Five observed object contracts matched across hosts:
  exact versions, authority, freshness and provenance. Source versions also matched.

A Gap reference using claim kind failed explicitly; DeepSeek recovered the correctly
typed Gap through search. No silent kind guessing occurred. The actual B edge was
unpinned, as submitted; no historical pin was fabricated. Separate tests cover pinned
upstream changes, stale derivation and canonicalization continuity.

A second model-free smoke boots the actual installed DeepSeek profile/ToolRuntime,
discovers nine tools, reads a separate synthetic A and writes B through the official
client. Omitting the Ledger patch was also checked in a fresh real DSH runtime:
zero Ledger tools. No fake harness core was substituted. Public-safe machine evidence is in
[continuity contract](testing/cross-harness-continuity.json); raw conversations and full
private inventories remain excluded from Git.

## 18. Verification

- Full pytest: **147 passed** (52.93 s), including real stdio transport, standard MCP
  roots and install-directory workspace scope, migration rollback/conflicts/idempotence,
  every typed-delta action, advisory-planning isolation, authority and freshness checks.
- Ruff lint and format: passed (src, tests, scripts).
- mypy: passed, 86 source files.
- Native plugin manifest/config parsing, nine-tool ON and zero-tool OFF: passed.
- Canonical CLI and legacy alias help: passed.
- sdist + wheel build and isolated wheel import/template/nine-tool smoke: passed.
- git diff --check: passed; no push.

## 19. Local commits

Existing main history retained. Logical local commits:

- 1ee3d42 — product identity and local Codex plugin package.
- 1bdc8d5 — workspace v2 migration and recoverable publication boundaries.
- ff89a9c — typed checkpoint increments and advisory planning.
- The final integration/report commit adds DeepSeek account interoperability and these
  public-safe acceptance records; its ID is available in the final Git log.

## 20. Final Git and runtime state

Tool repo and notes repo remotes have distinct correct responsibilities. Final tool
changes are committed locally, with clean tracked status; notes repo status is clean.
No private corpus, conversation, credentials, local deployment package or venv is staged.
Codex plugin is installed and disabled. DeepSeek Ledger activation remains per-invocation.
The current open desktop conversation needs a fresh session after manual enable.

## 21. Before a real mathematical vertical slice

No tooling/authentication blocker remains for the tested paths. The user must select
an actual Problem and deliberately enable Ledger in a fresh harness session opened at
<research-workspace>. Use status/context and inspect the existing unproved-target cautions;
retain exact trust/authority boundaries. A separately initialized empty child remains
separate if explicitly opened. Desktop native UI rendering is the only un-driven host
surface check; installation/config and fresh native hosts were measured. No real research
text has been authorized for a new external-model smoke in this task, and none was sent.
Publication to math-research-notes remains a separate, explicit user decision.
