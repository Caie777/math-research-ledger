# Tool and Research Workspace

Develop the software in `D:\Projects\structured-math-research`. Open a Research Workspace
in Codex for mathematical work. A workspace is one complete corpus, potentially containing
many related Problems; papers, notes, experiments and ledger belong under its root.
Human documents do not all need to be stored inside `.math-research`.

```text
D:\Projects\structured-math-research\   tool code, development AGENTS, tests, docs
D:\Research\math-research\              existing multi-Problem research corpus
├─ AGENTS.md                            research workflow
├─ workspace.yaml                       active metadata
├─ papers\                              human source materials
├─ notes\                               notes and migration inventory/audit
├─ experiments\                         optional, create when needed
└─ .math-research\                      unchanged existing ledger and pinned artifacts

D:\Research\riemann-surfaces\           initialized empty workspace, no domain objects
D:\Research\weak-schottky\papers\       original PDF only; no initialized ledger/research
D:\Projects\formalizations\             external Lean repositories, unchanged
```

Use explicit repository identity/provenance when associating an external Lean repository;
this migration creates no mathematical relation or formal bundle.

## Initialization and metadata

With the tool's environment on PATH:

```powershell
mkdir D:\Research\my-new-corpus
cd D:\Research\my-new-corpus
smr init
codex -C .
```

Without activating that environment, invoke the installed executable by its stable path:

```powershell
D:\Projects\structured-math-research\.venv-win\Scripts\smr.exe --workspace D:\Research\my-new-corpus init
```

Init creates `workspace.yaml`, packaged research `AGENTS.md`, human `papers/` and `notes/`,
and empty ledger directories (`papers`, `problems`, `research_archive`). It creates no fake
Claim/Definition/Experiment. Existing files and custom instructions are preserved; repeated
init is idempotent. Init explicitly selects the requested/current root even inside another
corpus, rather than accidentally initializing its ancestor.

The active metadata schema is deliberately small:

```yaml
workspace_version: 1
name: math-research
created_at: '2026-10-20T16:01:16.777720Z'
```

Name defaults to the workspace folder name; created_at records metadata/workspace
initialization, not an invented original research date. Version, nonempty name and a
timezone-aware timestamp are required. Unsupported versions/fields fail with an actionable
error. MCP resolution, CLI setup and status read this metadata. These are not model/provider,
tool execution or authority settings.

The original corpus's `.math-research/config.yaml` had fourteen legacy sections: model,
models, project, agent, permissions, privacy, ui, quality, environment, context, tools,
execution, governance and campaign. The pre-change core had no runtime consumer of those
fields, including context settings; service/tool arguments supplied current retrieval budgets.
The old Config helper was not called by research execution. The new core does not load that
legacy file. It is preserved byte-for-byte as historical compatibility data. The explicit
additive init/migration writes the root metadata, so the ledger remains exactly unchanged.
New workspaces do not receive a legacy runtime config. Unversioned old workspaces remain
readable without migration; status labels them `LEGACY_UNVERSIONED` until explicit init.

Tool AGENTS describes architecture, services/MCP discipline, synthetic tests and real-data
boundaries. Research AGENTS comes from the packaged `core/research_agents.md` template and
guides status, context, Episode/note submission and human-only acceptance. Business gates
remain in the services/server, independently of instructions.

## Whole-corpus cutover and path audit

The existing corpus moved as a whole, retaining all three Problems and their history.
Procedure: inventory + SHA256, copy to a missing destination, independently re-inventory and
verify both trees, then remove only the exact verified source. No Problem split, historical
JSONL/Markdown rewrite, provenance repair, formal experiment or human acceptance occurred.

| Check | Result |
| --- | --- |
| Files | 750 → 750 |
| Total bytes | 7,569,519 |
| Changed / missing / unexpected | 0 / 0 / 0 |
| Old active tool ledger | removed after verification |
| Unified objects / Problems | 270 / 3 |
| Operational artifact references | 30; none missing |
| Old run assets, rebuilt read-only | 5 runs, 559 assets; all 535 retained assets verified |
| Portable object versions / source version | identical between source and copied roots |

SHA256 of the canonical sorted relative-path/size/file-SHA256 inventory is identical:

```text
514d6b4a78fc592152edf218498f5f9cf050cfa6ded8fd498a68fc1edd83fb46
```

Full per-file inventories and verification reports live under the workspace's
`notes/workspace-migration-20261020/` and the tool's ignored
`.local-eval/workspace-decoupling-20261020/` development evidence directory.
The final audit ran after source removal and local MCP reads.

Operational Episode archive paths, Proof bodies, pinned source paths, run-relative assets
and config resolution use the current workspace root. Legacy absolute `source_path` values
in run evidence/provenance stay unchanged; they are not used to re-open the deleted source.
No current external formal repository registration or modern verification/acceptance ledger
needed path rebinding in this corpus. External repository identity remains explicit.

One code issue was fixed: derived hashes included absolute runtime artifact paths, causing
29 of 270 object versions to change merely on relocation under the old code. Workspace-local
artifact identities now hash `.math-research/...`; returned operational paths still resolve
to the current root. Source-version hashing uses the same portable representation. Historical
strings inside records are untouched. This changes the old derived hash algorithm for those
artifact-bearing objects; no persisted modern receipts or Episode input-version pins existed
in this corpus to rewrite. Existing historical pins elsewhere are never silently re-signed.

The tool repo no longer contains active `.math-research`, the original loose PDF, or old
operator control files. Obsolete operator logs/leases were preserved under ignored development
evidence. Removed the retired default runtime YAML and stale `/.opentorus/` and `/papers/`
ignore rules; development fixtures, examples and smoke evidence remain.

The original untracked PDF is now at:

```text
D:\Research\weak-schottky\papers\triangular_jacobian_weak_schottky_minor_revision.pdf
SHA256 e6a3143ebdced7d3dca52ff87574731a80639ae67f0ef70f85913f68c2f3d86c
```

Both source and destination hashes matched before source removal. This is only original
file custody; no Weak Schottky workspace, Claim, experiment or formalization was started.

## MCP discovery validation

The global Codex registration still launches the absolute tool Python and wrapper with no
fixed workspace argument/env/cwd. The server discovers the corpus from host cwd; it never
falls back from the tool checkout to a hardcoded research directory. The tool root now
returns `NO_WORKSPACE`.

Post-cutover local MCP stdio initialization/tools/list succeeded, exposing all nine tools.
Read-only status returned root `D:\Research\math-research`, state
`D:\Research\math-research\.math-research`, and versioned metadata. A bounded search returned
one existing hit. Local stdio validation does not invoke an external model.

The requested fresh Codex model session was blocked by automatic approval review because
real status/search/content could be transmitted to an external Codex service. Approval was
requested for status plus one bounded search excerpt only. Until authorized and run, this
report does **not** claim a post-cutover real Codex host behavior pass. Exact local payload
preview: `.local-eval/workspace-decoupling-20261020/host-readonly-payload-preview.json`.
Earlier synthetic CLI host discovery remains documented in [Codex MCP](codex-mcp.md).

Validation: workspace/config tests 8 passed; combined workspace/MCP/assets/interfaces tests
52 passed; complete pytest 127 passed; Ruff lint/format 98 files; mypy 84 source files;
Git diff check passed. A clean wheel includes the research instructions, excludes the retired
runtime YAML, and successfully initializes a workspace directly from the wheel.

## Independent backup and versioning

Back up the entire Research Workspace independently of tool source. The ledger's text
YAML/JSONL/Markdown suits private Git. Choose exclusions or Git LFS for large PDFs/artifacts;
keep required artifacts in some independent backup and preserve pinned identities. A remote
Git repository is optional and was not configured by this task. Tool upgrades must preserve
the corpus's historical bytes; workspace metadata changes should be explicit/additive or
versioned rather than rewriting historical provenance.
