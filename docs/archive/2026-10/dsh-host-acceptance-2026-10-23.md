# Windows Host acceptance — 2026-10-23

## Evidence source and candidate

The maintainer reported the following completed real Desktop/session checks on
2026-10-23. This record attributes those results to that report; the documentation
and release audit did not rerun Desktop, inspect private Profiles or access the real
research corpus. Paths are generalized as `<research-workspace>`.

- MathResearch Ledger candidate: 1.2.1, source commit
  `75cf43a89dad6cca2f2e27b346a0b3b763bf70ea`.
- Candidate wheel SHA256:
  `4fcc525bfae875b3031a702646c3ae113c9df9d2f1a14dd42ef219b24cf9a9ce`.
- This is the accepted **candidate** hash, not the final release asset hash.
  Final artifacts are rebuilt after documentation updates; use the release's
  `SHA256SUMS` for their identities. Production Python is unchanged by this doc update.

## DeepSeek Harness

Environment: Windows Desktop, DSH **0.2.1-rc.2**, Python **3.12.10**.
Integration: configuration-only Bundle, native `@deepseek-ai/dsh-mcp-client`, external
persistent Python, startup `--workspace <research-workspace>`.

| Check | Reported result |
|---|---|
| Tool discovery | Nine research tools registered |
| Workspace scope | Startup pin honored; cross-workspace requests rejected |
| Synthetic workspace | Read and provisional write passed |
| Real workspace | Read-only acceptance passed with zero writes |
| Desktop restart | Configuration and access persisted |
| Plugins OFF | Tools removed; server stopped |
| Plugins ON | Tools restored; server respawned |
| Security properties | No ACL, MIC or owner modification |

The sandboxed-shell `asyncio/socketpair` failure was not the real Host MCP path.
Earlier shell/Low Integrity diagnostics must not be presented as a current real Host
blocker. The read-only checkpoint implementation avoids lock-file writes; it does not
change Windows security properties.

## Codex

The maintainer also reported successful Windows fresh-session acceptance using a
persistent Python **3.12.10** runtime with `math_research` **1.2.1**, project-local
direct MCP and an explicit startup pin. The plugin skill remained available while
bundled MCP was disabled. Exactly one set of nine tools was present; real-workspace
read-only checks made zero writes and cross-workspace requests were rejected.

## Limits

Formal writes to the real research corpus were not separately exercised. DSH
macOS/Linux Host acceptance is untested. Synthetic writes do not establish general
research correctness or universal install-and-run compatibility. No private research
payload, object title, credential or local deployment configuration is included here.
