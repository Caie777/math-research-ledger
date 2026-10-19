# Research Asset Retention V1

Execution files stay in `research_runs/<run_id>/work`, `artifacts` and `checkpoint`.
The optional run-local `assets.json` is an operational manifest, not a mathematical
record or another storage system. Old runs without a manifest remain readable
through their existing run-local interfaces; reads never migrate them.

## Identity and integrity

`ResearchAssetRef` pins `(run_id, path, sha256)` and byte size. Its ID is
`ASSET-` followed by the first 16 uppercase hexadecimal characters of
`sha256(run_id + "\0" + path + "\0" + file_sha256)`. Absolute paths, traversal,
Windows drive/UNC/alternate-stream paths and redirects are rejected on all hosts.

`resolve_research_asset` verifies existence, size and SHA-256. Bounded content
readers verify the complete file and extract a preview from the same open read;
they do not verify a path and then reopen it for an unchecked response. Missing
files and integrity failures are explicit errors. **Hash match means byte identity
only: it does not establish mathematical correctness, verification or Human Accept.**

## Building and retention

`build_asset_manifest(run_dir)` only returns an in-memory model. It scans existing
allowlisted files, associates unambiguous script/output filenames and public
artifacts, and matches code to public tool events for success/failure/timeout.
Unknown metadata stays null; a nonempty output does not imply execution success.
Inputs with no explicit provenance are not inferred from code.

`publish_asset_manifest(run_dir)` rebuilds under the existing file lock and writes
atomically. New Research Agent finalization invokes it after Episode archival and
proposal extraction, including initialization-failure handoffs. No historical
manifest is written by retrieval, polling, context building or the API.

Retained files have explicit paths in the final/associated Episodes,
candidates/accepted projections, checkpoint summaries or public ledger. The
checkpoint's size/mtime inventory alone is discovery, not a retention citation.
The only relation closure is a directly referenced output to its unambiguous
producer script; inputs and other outputs are not recursively retained. Missing
exact references and unresolved script/output associations are reported.

Retention is monotone once published. Previously published object links and
identities remain pinned when rebuilding. A mutable checkpoint path can receive
a new content ID; reading its old ID must still fail the old hash, rather than
silently returning the new bytes. No duplicate asset ID is appended on rebuild.

`can_delete_asset` and `can_delete_run` are read-only automatic-deletion guards.
They inspect explicit references even without a published manifest. Any retained
asset (including a missing pinned file) prevents automatic deletion of its path
or run. V1 adds no deletion or cleanup operation.

## Discovery and cross-run reads

Research Agent tools:

- `list_research_assets(object_id, offset, limit)` returns bounded manifest
  metadata for an Episode/candidate/working/canonical object ID.
- `read_object` also includes the first metadata page of associated assets.
- `read_research_asset(asset_id, offset, length)` accepts only an opaque ID,
  requires retained status and the current Problem scope, verifies integrity and
  returns at most 4,000 bytes decoded as a text preview. Offsets/lengths are bytes;
  `chars` counts the decoded preview, `size` the complete file.

Late Human Review aliases are resolved through the existing review ledger to the
manifest's candidate links. This discovery does not rewrite the manifest. Scripts
are never automatically injected into ContextBuilder.

Read-only API equivalents under `/api/problems/{problem_id}/research-assets`:

- `GET ?object_id=...&offset=0&limit=12` — up to 20 metadata records.
- `GET /{asset_id}` — integrity-checked metadata.
- `GET /{asset_id}/content?offset=0&length=4000` — verified bounded preview.

Unknown IDs/files return 404, scratch returns 403, and hash/size drift returns
409. Invalid IDs and stored manifest validation fail closed through existing
API error handlers. Binary files retain their hashes and sizes; these endpoints
provide text previews, not full binary downloads.

There is no blob store, deduplication database, migration, packet/resume schema,
new truth system, authority promotion or automatic acceptance in this feature.
