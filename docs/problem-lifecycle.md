# Problem lifecycle (1.2.2 development)

The development checkout exposes eleven MCP tools. The published 1.2.1 release has
nine; its recorded real Host acceptance does not cover these two new tools.
Formal package/plugin versions remain 1.2.1 until a separate release task.

## Create an explicit research line

```json
{
  "title": "A new research question",
  "statement": "State the question and assumptions in full.",
  "primary_target": "State the mathematical target as text.",
  "dry_run": true
}
```

Send this to `research_create_problem`, inspect the normalized fields and impact,
then repeat with `dry_run=false` when authorized. Optional fields are `summary`,
`source_refs` (provenance strings), and `metadata` (up to ten small string pairs).
Input is bounded to 12,000 UTF-8 bytes. Title/statement/target cannot be blank.

A real call allocates a fresh `PROBLEM-NNNN`, initially **active**. Titles are not
unique: repeating a create allocates a different ID and never overwrites a Problem.
A preview's proposed ID is not reserved and can change if another writer intervenes.
The current Problem selection is unchanged. Use the returned explicit ID for status,
search, context and subsequent Episodes; ingest never creates an unknown Problem.
Missing workspace state must be initialized explicitly with the CLI.

`primary_target` is mathematical text. It does not create a Claim or set the existing
human-maintained `primary_claim_id` designation. Status exposes this target text;
`research_get_object` reads the Problem statement, target and labelled project metadata
through its existing pagination. New and semantically revised statements are provisional.

## Pause, close or reopen

Use `research_update_problem` with an explicit `problem_id`:

```json
{
  "problem_id": "PROBLEM-0001",
  "lifecycle_status": "closed",
  "closure_kind": "abandoned",
  "closure_reason": "The current route is no longer being pursued.",
  "resolution_refs": [],
  "dry_run": true
}
```

States are **active**, **paused**, **closed**. Any state can return to active.
Closing requires a nonempty reason and one of **resolved**, **abandoned**,
**superseded**, **other**. `resolution_refs` link existing Ledger objects (Claim,
Proof, paper or receipt); they do not add premise edges or grant authority.
Links are saved as qualified refs; bare IDs resolve only within the selected Problem.
Reopening retains the most recent closure details as history; `lifecycle_status`
alone states whether the Problem is currently closed. There is no delete operation.

Closed/resolved does not verify a Claim or create human acceptance. Existing
verification and acceptance receipts are untouched. **Project lifecycle !=
mathematical authority; checked != accepted.**

## Metadata versus mathematical revision

The default `revision_kind="metadata"` supports title, summary, provenance,
custom metadata, lifecycle and closure fields. These updates preserve the
Problem's mathematical version and do not make dependents STALE.

Supplying `statement` or `primary_target` requires explicit
`revision_kind="semantic"`, even if the supplied value is identical. A real text
change updates the existing content-derived version. Express changed assumptions
in the statement; this tool does not mutate separate Assumption/Claim records.
Merely declaring a semantic revision without changing a semantic field does not
bump the mathematical version.
An identical statement request also preserves the original statement file bytes,
including legacy Windows line endings.

Problem refs already participate in the dependency engine. An existing version-pinned
dependency on the Problem can become STALE, including its transitive dependents.
Objects that merely belong to the Problem are not automatically marked stale.
Unbound historical edges keep their existing UNKNOWN semantics. No second stale
system or automatic re-verification is introduced.

An optional `expected_version` rejects conflicting mathematical revisions. Updates
patch only supplied fields while holding the writer lock. Prior semantic versions
are preserved through the existing `ledger/versions` snapshots; the current version
remains in the dossier. A failed revision may retain a snapshot of the **previously
committed** version, just as failed Episode publication retains source bytes.

Both tools support zero-write `dry_run`. Invalid inputs return validation/service
errors and never silently repair research. Actual writes use the existing checkpoint
lock, rollback journal and generation fence. Interrupted publication blocks reads
until explicit trusted-human checkpoint recovery. All concurrent writers must be upgraded.
