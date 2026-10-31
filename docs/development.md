# Development and release gates

Release documentation for MathResearch Ledger **1.3.0**, updated 2026-10-31;
support policy established 2026-10-30. **Protocol-neutral, DSH-first, other Harnesses
on demand.** The standard MCP server and deterministic services are shared, while
DeepSeek Harness is the primary supported and tested Host. Its official UI name is
**MathResearch Ledger for DSH**. There is no Core/MCP breaking change or
research-schema migration in this release. See the
[adapter contract](adapter-contract.md) and [dated capability matrix](harness-capability-matrix.md).

## Workspace and change boundaries

- This checkout contains tooling, not an active research workspace. Do not initialize
  research state at its root or edit a real research corpus as part of development.
- Use synthetic temporary workspaces for tests. Real-data migration, writes and
  read-only acceptance each require explicit authorization and scope.
- Keep Core/ledger/retrieval/verification independent of CLI, MCP and Harnesses.
  Adapters call shared services; they do not duplicate business decisions.
- Preserve automated-scope, provisional-write and human-authority enforcement in
  server-side code. Prompts, shared skills and tool descriptions are not substitutes.
- Tool upgrades must not rewrite corpus history or absolute historical provenance.
  Keep local paths, credentials, Profile snapshots and private evidence out of public
  source/release artifacts. MCP stdout remains protocol-only and responses bounded.

## Prepare a persistent development/runtime Python

Requires Python **3.11+**; the historical Windows Host evidence used Python 3.12.
Choose an absolute, persistent runtime path outside research data and disposable
build/test output. The release runner's `--python` interpreter must have **both
`dev` and `mcp` dependencies**, not just an installed wheel with `[mcp]`:

```powershell
python -m venv '<persistent-dev-runtime>'
& '<persistent-dev-runtime>/Scripts/python.exe' -m pip install -e '.[dev,mcp]'
```

Run from the tool checkout. On macOS/Linux use `bin/python`; Host-platform acceptance
must still be established separately. Installing dependencies is explicit: the runner
must not silently install/upgrade a runtime or modify a user's DSH Profile. Updating
source or metadata does not upgrade an existing non-editable deployed runtime.

A clean, installed-wheel `[mcp]` runtime is useful for separate distribution smoke
checks, but it is not by itself a release-runner development environment. Refresh
matching deployed wheels/packages and start new sessions/restart before adopting a
new implementation; do not replace runtimes underneath active research sessions.

## Baseline development checks

With that interpreter activated, run:

```powershell
python -m pytest
python -m ruff check src tests scripts benchmarks
python -m ruff format --check src tests scripts benchmarks
python -m mypy
python -m build
git diff --check
```

These cover full pytest, lint, format, typing, packaging and whitespace checks. They
are necessary but do not by themselves prove an actual DSH Host regression ran: an
optional local Host test can skip when its prerequisites are absent. Inspect test
outcomes, not just the overall exit status. Synthetic writes never establish
acceptance for mutations of a real research corpus.

## Release-blocking runner

The release gate is **Core + MCP + actual DSH Host acceptance**. DSH is Tier 1
official: actively developed, documented, regression-tested and release-blocking.
The runner interface is `scripts/release_gate.py`:

```powershell
& '<persistent-dev-runtime>/Scripts/python.exe' scripts/release_gate.py `
  --dsh-executable '<absolute-DSH-executable>' `
  --dsh-node-modules '<absolute-DSH-node_modules>' `
  --python '<persistent-dev-runtime>/Scripts/python.exe'
```

| Argument | Meaning |
|---|---|
| `--dsh-executable` | Actual DSH Host executable, not a mock/replacement server. For an ASAR Desktop installation this is its Electron binary used in supported Node mode. |
| `--dsh-node-modules` | Matching installed DSH `node_modules` directory used by the real Host tests. |
| `--python` | Absolute persistent Python with this checkout and `.[dev,mcp]` installed; used for Python checks and the MCP runtime. |
| `--real-workspace` | Optional, explicitly authorized existing research root for additional **read-only** DSH Agent status/search; never an initialization, migration or mutation request. |
| `--output` | Optional new evidence directory **inside checkout `dist/`**, outside research data; defaults to `dist/_run/release-<unique>`. An existing directory is rejected rather than overwritten. |

Explicit flags are recommended. DSH executable/modules may also come from
`MRL_DSH_EXECUTABLE` / `MRL_DSH_NODE_MODULES`; `--python` defaults to the invoking
interpreter. All must satisfy the same prerequisites. `--real-workspace` must name
an existing exact root with a normal (non-symlink) `.math-research-ledger` state
directory; it is not a request to migrate legacy state.

The runner executes required pytest with `-m 'not codex_compat'` and
`MRL_DSH_REQUIRED=1`, so missing actual-Host prerequisites must fail rather than
silently skip that gate. It also runs Ruff lint/format, mypy, build and Git diff
checks. `pytest -m codex_compat` is recorded separately as a non-blocking compatibility
return code; a shared Core/MCP semantic defect must still be triaged as blocking,
not dismissed just because it appeared in a Codex test. Full `python -m pytest`
remains the baseline all-tests command, including compatibility tests.

The new output directory contains `result.json`; its `dsh_acceptance_report` field
locates the actual Host report under the same new output directory. With `--real-workspace`, the
additional `readonly-before.json` / `readonly-after.json` state inventories bracket
read-only DSH Agent status/search. Without that option the runner does not touch
real research data. Keep these reports local: they may include private paths and
research metadata. Exit success and evidence must reflect the required gate, not a
historical count or only the compatibility return code.

Example with separately authorized real-workspace reads:

```powershell
& '<persistent-dev-runtime>/Scripts/python.exe' scripts/release_gate.py `
  --dsh-executable '<absolute-DSH-executable>' `
  --dsh-node-modules '<absolute-DSH-node_modules>' `
  --python '<persistent-dev-runtime>/Scripts/python.exe' `
  --real-workspace '<authorized-existing-research-root>'
```

Keep the DSH executable and modules from the same installation/version. The dated
Windows acceptance used **DSH 0.2.1-rc.3**; rc.2, macOS/Linux and UNC/network roots
remain unverified for this adapter. Do not turn missing Host prerequisites or a
skipped actual Host test into a passing release result. An isolated real-Host test
is not the Desktop GUI, a model conversation or proof that the user's current
Profile selects the package. The [default Agent Host plugin](../integrations/deepseek-harness/host-plugin/README.md)
and the manual / single-workspace config-only fallback are mutually exclusive in
one Profile; the release runner is not a deployment/install command.

## CI versus an actual release gate

The hosted [Core/MCP workflow](../.github/workflows/ci.yml) runs shared checks and DSH
packaging contracts; its green result alone is **not** actual DSH Host acceptance.
Codex packaging compatibility runs in a separate non-blocking job.

The manually dispatched [DSH release workflow](../.github/workflows/dsh-release.yml)
runs the same required runner on a maintained self-hosted Windows runner labeled
`dsh-release`. Configure repository variables `MRL_DSH_EXECUTABLE` and
`MRL_DSH_NODE_MODULES` for the matching official installation. Missing configuration
fails. Both the result summary and actual Host acceptance report are uploaded.
Adding this workflow does not provision a runner, configure repository protection,
or establish that a remote run has succeeded; retain a successful actual gate run
before releasing. No publication is automated here.

## Compatibility checks, not equal release targets

Codex is **Tier 2 compatibility**, retained best-effort. Not every feature needs a
dedicated Codex Harness regression; Codex-only issues do not normally block release
unless shared Core/MCP semantics are affected. Optional reproduction is documented
in the [Codex guide](codex-mcp.md#reproduce-isolated-acceptance) and the
[historical Codex acceptance record](codex-session-acceptance.md). That compatibility
smoke is additional evidence, never a replacement for the DSH gate.

Other Harnesses are **Tier 3 on demand**: do not add a dedicated adapter until a real
use case exists. Standard MCP interoperability does not imply dedicated Host tests
or equal maintenance commitments. No Harness-specific regression may weaken shared
workspace assertions, no-auto-init behavior, provisional writes or human authority.

## Record evidence without rewriting history

For each new run, retain its date, checkout/version identity, exact Python and Host
versions, executed/skipped checks, exit outcomes and private evidence location. Keep
historical test counts attached to their original date and implementation; do not
reuse the 2026-10-26 or 2026-10-30 acceptance numbers as a 1.3.0 release result. Separate:

1. Core/MCP regression and actual isolated DSH Host acceptance;
2. optional Codex compatibility evidence;
3. separately authorized real-workspace read-only acceptance;
4. actual installed Profile selection and enabled deployment state;
5. GUI conversational acceptance, which is not established by the preceding checks.

The 2026-10-30 Profile audit found both DSH packages registered as dependencies but
neither selected in `bundles`; this snapshot and the earlier cutover are historical,
not evidence of current activation or a completed 1.3.0 migration. Documentation or
source changes do not deploy them for the user.
See [known limitations](known-limitations.md), [version 1.3.0 notes](releases/v1.3.0.md),
the [redacted 2026-10-30 closeout](dsh-first-finalization.md) and
[historical engineering reports](archive/2026-10/README.md).

## Package and public-report checks for 1.3.0

The official Host UI title is **MathResearch Ledger for DSH**. The public Host npm
tarball has seven files: the runtime entry, package manifest, bundle patch, README,
LICENSE, and the English/Chinese locale files. The dated 1.2.2 five-file package
result remains historical; the two locales are an intentional 1.3.0 addition, not
an accidental runtime or evidence inclusion. Check wheel/sdist and both DSH tarballs
from the final versioned tree before publication. None should include rendered
runtime paths, real Profile files, research state or local acceptance evidence.

A public acceptance summary may retain dated software versions, test counts and a
generalized zero-write conclusion. Keep exact private-corpus inventories, hashes,
generation values, object counts, timestamps and process identifiers out of public
reports. Do not link ignored local evidence or permission-recovery records from
public docs. Record fresh 1.3.0 results only after the corresponding checks finish;
the 2026-10-30 report's 31+5 uncommitted-file snapshot is not the release tree or a
reason to discard the intentional version/locale changes.
