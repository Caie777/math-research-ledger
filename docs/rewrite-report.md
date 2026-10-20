# Scope contraction delivery — 2026-10-20

## 1. New product path

```text
src/math_research/
├── core/          qualified refs/version pins, hashing, config, atomic IO/locks
├── ledger/        typed records, archive/proposals/human review, manifest,
│                  typed dependencies, history, state/projection, source/assets
├── retrieval/     BM25/scoped navigation, bounded dependency context, packet
├── verification/
│   ├── formal/    freeze, models, exact Lean declaration/type/axiom checker
│   ├── models.py  general hard receipts, exact/validated-computation contracts
│   ├── review.py  independent advisory packet/report/verdict
│   ├── authority.py
│   └── freshness.py
├── services/      research, ingest, retrieval, review, verification, acceptance, stale
├── cli/           shared-services human/debug interface
└── mcp/           optional stdio skeleton and validated bounded adapter
```

Python source files contracted from 147 to 84. There are no imports from the removed agent/app/formalization packages, and lower-level packages do not import services. CLI and MCP use the same deterministic services. Full design and limits: architecture.md.

## 2. Removed subsystems

Removed tracked standalone agent loops, provider adapters/routing, Codex-native executor, tool-call parsing, compaction, token accounting, custom sandbox/permission runtime, coordinator, streaming/progress runtime, Source Digest model runtime, relation scout/adjudication runtime, internal formalization loop/executors/benchmark, React source, old FastAPI product routes, old launch/build wrappers, and tests exclusive to those runtimes. The obsolete formalization-agent document and unused thread-scope helper were also removed.

No large legacy directory was created. Git history retains old code. Ignored local build/dependency artifacts and all historical research-run data were not recursively purged.

## 3. Retained core assets

Typed dossier records and all existing disk layouts; exact Episode archive/provenance/spans; deterministic simple and numbered parsing; provisional identities; Human Review boundary; canonical full proofs; failed/rejected work; counterexamples; scoped Recall/BM25/material selection; MUST/SHOULD/MAY and incomplete semantics; atomic IO/locks; retained asset identity/integrity/provenance; Lean freeze/check and negative source/axiom policy.

Former memory code moved to ledger. Useful proof/source readers and saved Source Digest acceptance guards were extracted from app/agent into pure ledger helpers. Caller-supplied vector interfaces remain, without provider/network initialization.

## 4. Unified Ledger semantics

Domain models remain typed. ManifestEntry is a reference/projection view, not a replacement universal domain object. It includes qualified_id, ref(kind/scope/id), content_hash, version, research_state, authority, verification, review, dependencies, provenance, artifact_refs, full record/body and warnings. ObjectView adds derived freshness and distinct working/trusted-formal premise flags.

ObjectRef uses problem_id:kind:object_id, with _global for workspace-level records. Bare-ID lookup rejects ambiguity. Dossier proofs and old verifier submissions have distinct kinds. No historical ID migration occurred.

## 5. Dependencies, versions and stale

Content/byte identity is SHA-256. Version additionally binds declared typed dependencies; dependency hashes never enter research primary IDs. Roles distinguish logical premise, definition, source/reference, proof target, evidence, artifact provenance, revision/supersession and formal correspondence. Semantic similarity remains relevance only.

Explicit links pin upstream versions, with append-only history. Freshness is derived CURRENT/STALE/UNKNOWN with bounded traversal. Missing/unresolved inputs and cycles cannot produce trusted currentness. Explicit cross-scope dependencies participate in source coherence. Episode input_versions bind only explicitly declared Uses/proof-target relations and survive human canonicalization.

Verification pins the complete current closure and preserves per-object full version snapshots and referenced artifact bytes. Definition revisions preserve old/new typed snapshots. Stale does not erase verification or human receipts. Re-pinning alone does not refresh old accepted evidence; recheck and a new human decision are needed.

## 6. Verification and authority

FormalCheckResult remains checked/provisional; it cannot self-accept. Raw FormalBundle flags remain false/PENDING. Authority elevation is a separate immutable human receipt. Formal acceptance requires passed current hard evidence and explicit correspondence between exact informal/formal versions. Changing a proof, frozen input, dependency, or checker log disables current trusted use while retaining history.

VerificationReceipt supports formal, exact and validated computation. ExactCertificate/ValidatedComputation describe inputs, scripts, environment, outputs, checker, scope and limitations. ExactChecker is a local registered protocol; there is no domain-specific exact checker or experiment executor bundled.

The trusted human CLI enforces automated context and both SMR_AUTOMATED_RESEARCH / legacy MCH_AUTOMATED_RESEARCH environment guards. This is not authentication against unrestricted local code or filesystem access. MCP exposes no accept capability.

## 7. External Harness integration

Export a bounded packet, let Codex/Claude Code/another harness research outside this package, then ingest its standard Research Episode. Provenance, exact source bytes, spans, full proof text, failed routes and provisional authority remain intact. Inputs may include version pins from the exported packet. Preview is read-only and import is content-idempotent.

Packets label TRUSTED/PROVISIONAL/STALE/FAILED/HISTORICAL, budget compact JSON, signal mandatory omission/truncation and check source-version coherence. Existing scoped intent/currentness/relation navigation is fused with unified BM25 search. Raw old Episodes are only optional excerpts.

## 8. Soft review

ReviewPacket contains exact Claim, Definitions, Assumptions, available full Proof, explicit dependencies, referenced results and provenance. External reports support GAP_FOUND, DEPENDENCY_GAP, SCOPE_MISMATCH, INCONCLUSIVE and NO_GAP_FOUND. All reports are ADVISORY; no verdict promotes verification or authority. No LLM runtime is included.

## 9. CLI

Entry points: smr and math-research alias. Without reinstalling console entry points, use the workspace Python with -m math_research.cli.

```text
init / status / search
ledger list / show / history / create-problem / add-claim
ledger add-definition / revise-definition / link
context export
ingest source / episode / review [--edits JSON]
review packet / record
verify show
formal freeze / check
acceptance request / pending / accept
stale report
```

CLI contains adapters, not duplicated domain logic. JSON output preserves mathematical Unicode on pipes. Actual command parameters are available via --help.

## 10. MCP

Implemented a bounded, schema-validated adapter and optional stdio server skeleton. Capabilities: search_research, get_research_object (scoped window), export_context_packet, request_acceptance, get_stale_report. Output cap: 64 KiB. No accept, arbitrary path, shell or compiler tools. The server exposes a dispatcher and capability schemas.

Adapter contracts are tested. The optional MCP SDK is not installed in this environment; real SDK transport/host integration was not run. Install .[mcp] and perform a host smoke test before connecting it. Freeze/check/link tools can be added later only with explicit registered repository capabilities.

## 11. Existing research data

The real .math-research tree was not migrated, repaired, accepted or rewritten. Before/after comparison covered 750 files: 0 changed, 0 added, 0 removed. Read-only smoke checks loaded 270 unified objects, searched existing research, and exported an 8000-token packet with explicit incomplete-required-context signaling. No real mathematics experiment or new formalization was run. No Weak Schottky object was registered or accepted.

Both archive layouts and existing YAML/JSONL/Markdown remain readable. Saved runtime config keys are tolerated but not executed. Old Python import paths and old Web/CLI interfaces are intentionally removed; disk compatibility is distinct from those APIs. Existing unknown references remain visible as unresolved rather than silently repaired.

## 12. Validation

- 108 passed, 1 skipped: synthetic core contract suite, including retained formal-check and asset tests.
- The skipped test requires creating a Windows junction, which this sandbox denies. Other path/argument/hash/integrity tests ran.
- Ruff lint and format check passed; mypy passed for 84 source files.
- Git diff whitespace checks passed.
- Clean wheel build passed with no dependency download/build isolation. Wheel content excludes old runtime packages; 82 importable submodules and bundled default config were smoke-tested directly from the wheel.
- Optional MCP SDK protocol transport was not exercised.

## 13–14. Local Git delivery

A recoverable local checkpoint commit is aa7380f, followed by the final scope-contraction delivery commit (see git log). No push. The only pre-existing untracked input is triangular_jacobian_weak_schottky_minor_revision.pdf; it is not part of either commit. Research state/evaluation directories remain ignored.

## 15. Remaining scope

No real-paper acceptance or stale experiment was performed. Before a real slice, select a new paper and exact target, record its source/Definitions/Assumptions, and prepare the authorized external Lean repository and trusted toolchain. New PDFs without cached extraction require external text extraction/OCR. A problem-specific exact checker must be registered if using computation instead of Lean. MCP SDK/host smoke testing and stronger installed dependency/binary attestation remain optional deployment work.

## READY FOR FIRST REAL RESEARCH VERTICAL SLICE

1. User chooses the new Riemann-surface/classical-theory paper and one short, precise target; this task chose no paper.
2. Create the Problem/Claim, pin source and Definitions/Assumptions, and record explicit dependency roles. Extract/OCR source externally if needed.
3. Export a budgeted context packet and supply it to the chosen external harness. Preserve qualified IDs and actual input versions.
4. Ingest its complete provisional Episode; independently review the exact review packet and record the advisory report. Human canonicalization remains explicit.
5. Prepare the authorized formal repo/frozen type contract, run the fixed checker, inspect exact evidence and informal/formal correspondence.
6. Request acceptance, have the human accept the exact current version, then exercise an explicitly chosen controlled revision and inspect stale/history. No automatic acceptance occurs.

The generic synthetic end-to-end infrastructure for those steps is implemented. The remaining first-slice work is real source/target preparation, external execution, human judgment and environment/adapter validation, not another autonomous runtime.
