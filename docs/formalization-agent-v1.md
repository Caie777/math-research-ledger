# Internal Formalization Agent V1

The standalone agent uses the existing `BaseProvider.generate` abstraction and
provider/credential settings. It never calls Codex CLI, native transport, another
coding agent, the Research Agent loop or research memory. `select_api_provider`
prefers the local research API role, then explicitly configured legacy API research
defaults. Native-only or missing API settings return `BLOCKED_API_CONFIGURATION`.
There is no fallback or automatic model choice. Credentials stay in the adapter.

## Capabilities

`FormalWorkspace` exposes audited list/read and atomic proof writes. Statement,
definition, lock and root-module files are immutable. Only `.lean` files under
`WeakSchottky/Proofs/`, `WeakSchottky/Helpers/`, `WeakSchottky/Scratch/` are writable.
Both slash conventions, absolute paths, traversal, symlinks and junctions are
checked. Literal Mathlib search and windowed source reads stay in the isolated
copy's `Mathlib/` tree. Each file tool records allowed/denied access. There is no
general filesystem or shell capability.

Obvious executable Lean metaprograms/IO are rejected at write time. This is a
restricted proof-authoring surface, not an OS sandbox or a complete Lean language
security verifier. The compiler and pinned Mathlib tactics are trusted. Hashes
are checked before/after compiler calls; no refreeze or acceptance tool exists.

`FormalTools` reuses V0's logged subprocess runner and deterministic checker.
Changed target files trigger project builds; other proof/helper/scratch files get
a fixed `lake env lean <validated file>` check. An explicit project build is also
available. Successful declaration facts are keyed by file hash and discarded on
edit; only checked files or the root's imported source closure supply facts.
Final checking reserves a build from the same budget and applies V0's target,
axiom and hash policy. An additional type ascription compares the target with the
original frozen predicate, preventing a same-named weaker declaration. The
benchmark derives this from a simple explicit-parameter Prop header; unsupported
headers fail rather than being weakened.

Full compiler logs stay on disk. Structured diagnostics retain file, line, column,
severity, message, goals/context and error signature. Prompts contain bounded
source views, up to six compressed diagnostics, successful facts, previous action
results and budgets. They contain no baseline proof, whole PDF, full conversation,
raw historical logs or keys. Model output is public JSON, not hidden reasoning.

## Loop and budgets

`FormalizationLoop` persists state before external work. Limits are at most 16 model
calls, 24 compiler/build invocations and 4 target checks. Target checking's build
counts too. The default total token guard is 160,000, with a 24,000 estimated
context limit and an 8,192 output reservation/configuration per request. Exact
provider usage is reused; estimates and missing usage are labelled. Cached tokens
are null when the existing provider abstraction does not expose them. Usage stays
in the run, never in the real research ledger.

Repeated proof hashes, empty edits, three repeated error signatures and looping
lookups/actions trigger one concise reflection opportunity. Continued stagnation
stops `NO_PROGRESS`. Other terminal reasons include `CHECKED`, `BUDGET_EXHAUSTED`,
`MODEL_FAILURE`, `TOOL_FAILURE`. Malformed JSON gets one bounded repair opportunity.
Truncated provider output is not executed as a complete proof.

`--configuration-only` is an explicit no-generation mode. Even a configured API
provider is blocked before any `generate` call; only a sealed configuration
checkpoint is produced. It cannot be mistaken for a capability benchmark.

An unfinished run can be reconstructed without resetting budgets or replaying an
uncertain operation. Official recovery is stricter: an infrastructure crash
invalidates the experiment. An exclusive reservation prevents an automatic second
official run. Final sources/evidence are hashed and sealed before post-hoc
comparison; terminal runs cannot be resumed by the loop.

## Benchmark preparation and execution

`prepare_workspace` copies only approved frozen statement/config bytes and
dependency package caches into a new independent repository. It never checks out
the baseline commit or copies its proof sources or root `.lake/build`. It checks
the original raw statement hash and freezes the new root import module as well.
`informal_source` extracts just the lemma/proof passage from the verified PDF,
without reading a prior formalization report.

After setup, tests and a setup-only build, invoke once:

```powershell
$env:ELAN_HOME = 'D:\Tools\elan'
python scripts/run_formalization_benchmark.py --project <main-project> --repo <isolated-repo> --output <new-output> --lake <pinned-lake.exe>
```

The command consumes prepared `setup.json`, `frozen-inputs.json` and
`informal-target.md`. It reserves one attempt, resolves existing API configuration
and either runs the loop or records BLOCKED. BLOCKED is not a capability
measurement or a proof failure. Do not optimize/retry after an official model run.

Checked still grants no acceptance, premise authority or canonical Claim promotion.
This V1 does not implement Acceptance/Stale, Definition V2, canonical migration,
review UI or Proposition 4.2. Unit tests use synthetic targets/fake providers only.
