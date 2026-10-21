# Workspace format, ownership and migration

Harness owns the workspace. User owns ordinary files. MathResearch Ledger owns only
`.math-research-ledger/`. Never move PDFs, rename research directories, organize files,
stage/commit/push, or select publication as part of Ledger capture.

```text
D:\Projects\math-research-ledger\       tool/plugin source: Caie777/math-research-ledger
D:\Math Research\                      user's unified research workspace
├─ ordinary research files/directories  preserved in their existing locations
├─ math-research-notes\                 separate Git repo: Caie777/math-research-notes
├─ workspace.yaml                       local-only metadata
├─ AGENTS.md                            local-only research instructions
└─ .math-research-ledger\                local-only persistent ledger
```

The actual publication repo is nested under the workspace; the workspace root is not
a Git repo. Preserve this user-confirmed layout. The publication repo contains mature
research selected by the user, never provisional state automatically.

When a workspace itself is a Git repo, inspect `git ls-files` before local exclusion.
Add `.math-research-ledger/`, `workspace.yaml`, `AGENTS.md` to `.git/info/exclude`, not
the public `.gitignore`. Excludes do not untrack files: report tracked private state
without deleting history or remote files. Ordinary init/capture/retrieval never call Git.

## Explicit format v2

New workspaces use root metadata `workspace_version: 2`, name and timezone-aware
created_at, with `.math-research-ledger/`. Version 1 and unversioned `.math-research/`
remain readable without writes. Init on legacy state gives an explicit migration path;
it cannot silently create another ledger. Conflicting state directories, mismatched
metadata, unknown targets and pending migration journals fail explicitly.

```powershell
math-research-ledger --workspace '<target root>' migrate --from-workspace '<old root>'
math-research-ledger --workspace '<same root>' migrate
math-research-ledger --workspace '<target root>' migrate --rollback
```

Stop writers first. Migration uses a same-volume atomic directory rename and atomic
metadata publication with a durable rollback journal. A crash between publications
blocks discovery until rollback. Unknown directories are never overwritten; cross-volume
moves fail without partial copies. Source-side ordinary metadata/instructions remain
unchanged. Init target instructions explicitly after migration; existing AGENTS is preserved.

Inventory before/after includes files, bytes, per-file SHA256, canonical inventory hash,
object/Problem counts, object versions, source version, pinned assets and operational
paths. `scripts/workspace_inventory.py` writes outside state. Keep full private-path
inventories local; publish only aggregate measurements and hashes.

Historical absolute provenance stays immutable. Old archive prefixes are mapped only
for operational reads. The `.math-research/` token in version hash identity stays frozen
to preserve historical pins; it is not an active directory selector. Empty new optional
checkpoint fields do not change legacy Episode versions. Back up state and local metadata
under the workspace's existing policy. papers/notes are optional conventions.
