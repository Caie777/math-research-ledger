# Known limitations and deferred review

MathResearch Ledger 1.2.0 provides the core Ledger, CLI, nine-tool MCP surface and
Codex integration. Automated regression tests and recorded integration checks cover
these paths; they do not establish mathematical truth or general long-term research reliability.

DeepSeek Harness is **experimental**. Historical isolated Host ToolRuntime checks
verified nine-tool discovery, read-only calls and ON/OFF/ON. User-provided Desktop
diagnostics report successful nine-tool registration but unsuccessful status on an
existing Windows research workspace. These are different acceptance levels.

## Windows diagnosis

The reported sandbox Python process runs at Low Integrity; the workspace root received
a Low label, while its existing Ledger subtree remained Medium. Denied creation of
`.math-research-ledger/.checkpoint.lock` is the observed failure. Windows Mandatory
Integrity Control's no-write-up rule explains that failure given those reported labels;
the release task has not independently inspected or modified the real directory.

The lock fix bounds waiting and surfaces permission errors. It does not change security
attributes. Successful MCP handshake or tools/list does not establish tools/call access.
Keep the exact error, distinguish process startup from file-access failure, and have
the user inspect process and subtree integrity levels separately from ordinary ACLs.
Stop on denied access. Installation and calls never silently change ACLs, labels,
owners, authentication or Full Access settings. Any targeted security change requires
separate informed user approval; no such repair is part of this release.

Real Windows existing-workspace DSH status/search and post-restart session acceptance
remain incomplete. macOS/Linux DSH Host acceptance is untested. This does not block
the core/Codex release, and is not a claim that DSH installs work for every user.

## 1.2.1 development — not yet released

The working-tree read-path fix replaces the six pure MCP tools' exclusive checkpoint
lock with bounded whole-operation consistency checks. Episode preview also uses this
read path. It requires readable state, not state-directory writes; acceptance requests
remain writes. All concurrent checkpoint writers must use the new generation protocol;
reload old cached installations before mixing readers and writers. See the
[implementation and validation report](archive/2026-10/read-only-checkpoint-2026-10-23.md).

This does not repair existing Windows security labels or establish real DSH Host
acceptance. Formal package metadata remains 1.2.0 until a separately authorized release.

## Remaining review backlog — not implemented or promised fixes

1. **Read-path deployment:** released 1.2.0 readers still create/remove a checkpoint lock.
   The development fix above needs release and real Host acceptance. It does not move
   locks into `%TEMP%` or make write tools work on nonwritable state.
2. **Windows sandbox compatibility:** investigate Low/Medium Integrity mismatch for
   existing Ledger state only after user approval and with narrowly scoped acceptance.
3. **Workspace scope:** prefer authoritative Host/MCP roots over arbitrary model-supplied
   absolute workspace paths where the host can provide them. Current deployment pins
   and explicit workspace behavior remain as documented.
4. **Multi-root selection:** consider selecting the unique root containing Ledger state;
   current ambiguous-root behavior must not be mistaken for completed support.
5. **Legacy public APIs:** keep retrieval/compatibility APIs frozen until a consumer and
   deprecation audit. No approximately 651-LOC removal is included.
6. **DSH native Bundle:** retain experimental status; complete Windows user-session
   acceptance and document supported platforms before broad compatibility claims.
7. **Performance:** current corpus scale does not justify a new cache or FTS subsystem.
   Revisit only with measured usage needs.

Deferred suggestions also include SQLite FTS5, BM25 caches, embeddings, rerankers,
prefetch, backup/doctor commands, PID-aware lock redesign, TTY acceptance authentication,
a custom DSH MCP client and large retrieval refactors. None is part of 1.2.0.

Human acceptance is a workflow boundary on the supported MCP surface, not authentication
or sandboxing against arbitrary local code/filesystem access. See
[architecture](architecture.md), [Codex setup](codex-mcp.md),
[DSH installation](../integrations/deepseek-harness/README.md) and
[historical engineering evidence](archive/2026-10/README.md).
