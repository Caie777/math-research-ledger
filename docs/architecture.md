# Deterministic core product path

```text
core/          refs, hashing, config, atomic IO/locks, limits, paths/process
ledger/        typed dossiers, archive/proposals/reviews, unified manifest,
               typed dependencies, state/authority projection, retained assets
retrieval/     lexical/BM25, optional caller vectors, scoped recall/selection,
               bounded context and external packet serialization
verification/  general receipts, exact checker protocol, advisory review,
               human correspondence, authority/freshness, formal freeze/check
services/      research, ingest, retrieval, review, verification, acceptance, stale
cli/           trusted human/debug adapter
mcp/           optional stdio server + bounded model adapter
```

CLI/MCP call services. Core, ledger, retrieval and verification do not import services, old app, providers or autonomous runtime. Projection composes typed records and verification/authority rules. Existing dossier persistence remains authoritative; there is no universal domain-object replacement.

## Identity and version

ObjectRef(problem_id, kind, object_id) formats as scope:kind:id; global identities use _global. Bare IDs raise on ambiguity. Old IDs are not rewritten.

ManifestEntry preserves full typed record, available full proof/source body, provenance and artifact refs. content_hash is deterministic SHA-256 over semantic record/body/exact artifacts, excluding creation/update/import timestamps. version additionally fingerprints typed dependency declarations. It is not a primary ID. Raw artifact SHA-256 remains separate.

Workspace-local artifact paths enter version/source-version hashes using the frozen v1
identity token `.math-research/...` (not an operational directory selector),
so copying a corpus to another root preserves derived identity. Returned operational paths
resolve in the current workspace. Historical absolute strings inside records/provenance
are unchanged; external formal repository identities remain explicit.

New formal bundles, verification receipts, review reports, dependencies, requests and acceptances use additive JSONL under .math-research-ledger/ledger/. Bundle revisions append; latest projects current content. Verification preserves full per-object version snapshots and referenced artifact bytes; Definition revisions through the service retain full old/new snapshots under ledger/versions/<problem>/definition/<id>/ before updating the typed YAML list. There is no universal blob store.

## Dependencies and freshness

Roles distinguish logical premise, definition, source/reference, proof target, evidence relation, artifact provenance, revision/supersession and formal correspondence. Legacy fields keep their actual roles; similarity is not a dependency. No historical dependency version is invented.

ledger link pins the upstream version. Latest declaration for a (dependent,target,role) tuple is active; earlier records remain. CURRENT / STALE / UNKNOWN is derived with bounded traversal. Changed pinned versions and missing artifacts cause stale. Missing unpinned refs, cycles and traversal bounds fail closed. Explicit cross-Problem dependencies retain qualified scope and participate in source-version coherence.

Verification and acceptance pin complete current closures. Adding/changing a dependency declaration changes version. Upstream changes invalidate downstream current use. Re-pinning does not refresh an old receipt automatically. Historical receipts are never overwritten.

## Authority boundaries

Research state, authority, verification, review and freshness are separate. Canonical means human-recorded research memory; it is not proof. Raw FormalBundle flags remain false/PENDING and checker status cannot yield accepted. Human acceptance is a separate immutable receipt and current projection.

Formal trusted use requires passed hard evidence, current closure, human acceptance and explicit informal/formal correspondence. Exact computation evidence does not masquerade as a formal proof. NO_GAP_FOUND is always advisory.

The human CLI is a trusted channel. Automated scope/environment blocks supported automated callers, and MCP has no accept capability. This is not authentication against arbitrary local code/filesystem access.

## Verification and review

VerificationReceipt supports formal, exact and validated computation. ExactCertificate includes scope, inputs, environment and script/output ArtifactRefs. ValidatedComputation adds method and limitations. A local application registers ExactChecker implementations; certificate data never executes a shell or imports code. No domain checker/experiment executor is bundled.

Lean keeps versioned statement/config/lock snapshots, exact declaration/type probes, source/axiom policy, bounded output and full logs. Services bind project Lean source hashes before/after checking and checker-log hashes. Changed, removed or added project Lean sources invalidate current receipt reuse.

Environment identity currently pins configured toolchain/lockfiles. It does not attest compiler binaries or every byte of installed Mathlib. Use explicitly selected trusted installations; add installation integrity policy before higher-assurance deployment.

ReviewPacket includes exact Claim, Definitions, Assumptions, available full Proof, dependencies, referenced results and provenance. ReviewReport verdicts: GAP_FOUND, DEPENDENCY_GAP, SCOPE_MISMATCH, INCONCLUSIVE, NO_GAP_FOUND. No LLM runtime or automatic authority is implemented.

## External packets and ingestion

Existing material selection supplies current/history/failed-route relevance and required proofs. Packet serialization adds qualified identities and authority/freshness. It preserves MUST/SHOULD/MAY, budgets the entire compact JSON, reports missing/truncated mandatory content and checks source-version coherence. Raw Episodes are optional bounded excerpts, not wholesale old conversations.

TRUSTED is current human-accepted hard evidence in its stated scope. PROVISIONAL includes unverified canonical working records. STALE/FAILED/HISTORICAL never authorize positive premises. UNKNOWN freshness renders conservatively as STALE while retaining its exact field. Incomplete full proofs are not marked usable. Tiny budgets that cannot hold mandatory identity/authority metadata explicitly fail.

External harnesses consume packets and return standard Research Episodes. Ingestion preserves exact UTF-8 bytes, source spans, full bodies, failed routes and provisional identities. Preview is read-only; duplicate import is content-idempotent; parse/validation precedes archive writes. Human canonicalization, checking and acceptance are independent. Episode input_versions pin only explicitly declared Uses/proof targets, including after canonicalization.

## Compatibility and limits

Tool and Research Workspace are separate roots. The workspace contains the full corpus,
including optional human papers/notes/experiments outside `.math-research-ledger`. Active root
`workspace.yaml` has strict version/name/created_at metadata. Legacy `.math-research/config.yaml`
is an opaque historical file, with no runtime/Agent/provider consumers. Reading never migrates;
new init uses v2; legacy state needs explicit `math-research-ledger migrate` before init.
Both operations preserve ordinary files and historical provenance.
See [workspace configuration and backup](research-workspaces.md).

Existing .math-research requires no migration or writes to read. Both archive layouts, canonical records, source-digest evidence, relation decisions, rejected work, full proofs and run assets remain readable. Source-digest acceptance validation is a pure compatibility guard; generation/scout runtimes are gone. Retained assets keep identity/integrity/retention APIs without an executor.

Unresolved historical references remain explicit, not silently repaired or accepted. Old Python import paths memory/app/formalization are removed. Disk compatibility does not promise old scripts or Web/CLI compatibility.

Workspace v2 changes the private directory to `.math-research-ledger/`; v1 stays readable.
An offline rename and atomic metadata publication have a rollback journal; interrupted
migrations fail closed. The harness/user own the workspace/ordinary files; Ledger owns
only private state and never stages, commits, pushes, or selects research publication.

Checkpoint delta assertions are typed as Added/Revised/Invalidated/Refuted/Still Open,
with exact source digest and line spans. Next Research Directions are excluded from
candidate/dependency generation and stay advisory. A delta never grants authority or
mutates a canonical target by itself. Raw Episode bytes remain complete. Checkpoint
publication serializes both indexes behind the writer lock and a durable rollback
journal; failed publication retains raw bytes. Pure MCP reads
instead validate the entire materialized operation against persisted metadata/object
versions and a writer generation marker, with bounded replay on change. Readers never
create state or a lock; observed pending journals fail closed. The marker advances even
on rollback and is coordination metadata, not an object version or authority receipt.
Acceptance requests still write and retain the exclusive guard without replay.
Interrupted metadata needs trusted-human
`ingest recover`. No per-turn capture hook or full-ledger rewrite is installed.

MCP exposes nine top-level `research_*` tools: status, search, object windows, context/review packets, stale reports, provisional Episode/note ingestion and pending acceptance requests. `tools/list` provides descriptions and strict schemas; there is no generic dispatcher. External references are strings, resolved to internal ObjectRef values without guessing ambiguous IDs. Episode/note writes reuse the existing archive/Proposal Store, content deduplication, locks and atomic IO. Output, including both SDK representations, is bounded to 64 KiB; review inputs are never silently truncated. Errors include a code and recovery action. There is no compiler, filesystem, shell or human accept. See [Codex integration and validation](codex-mcp.md).

MCP captures a single canonical workspace from startup flag,
environment or cwd discovery. Tool `workspace` is only an exact-root compatibility
assertion; it cannot expand scope. MCP roots are not used for authorization in this
version. CLI selection remains independent. No authorization database or filesystem
sandbox is introduced.
