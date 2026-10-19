# Formalization V0

This package checks an existing, trusted local Lean/Lake repository. It is independent
of the Research Agent, canonical Claims, research ledgers and retrieval. It neither
downloads dependencies nor generates statements or proofs. It is not a sandbox for
untrusted Lake configurations or Lean metaprograms.

`FormalState` names `provisional_formal`, `checked`, and `accepted`. V0 deliberately
has no acceptance operation: a checker can only return the first two. A clean check
does not grant premise authority. `FormalBundle` fixes human correspondence to
`PENDING`, and `usable_as_premise`, `human_accepted`, `promotes_claim` to false.
Human acceptance and canonical integration require a later, explicit design.

## Freeze before proof search

Typecheck the statement separately first. Then freeze its whole source file, every
project-defined mathematical definition it depends on, the toolchain file, Lake
configuration and Lake manifest. List no local definitions if there are none.
Proof helper lemmas need not be represented as statement definitions.

```python
from pathlib import Path
from math_research.formalization import freeze, LeanChecker

repo = Path("D:/Projects/formalizations/weak-schottky")
store = Path("D:/Projects/structured-math-research/.local-eval/example/freezes")
frozen = freeze(repo, "WeakSchottky/Lemma41Statement.lean", (), store)

checker = LeanChecker(
    Path("D:/Tools/elan/toolchains/leanprover--lean4---v4.35.0/bin/lake.exe")
)
result = checker.check(
    repo, "WeakSchottky.Lemma41Proof", "WeakSchottky.lemma41", frozen,
    store.parent / "check.log",
)
print(result.status)
```

The example creates a new version and a new log: choose unused output paths.
`freeze` refuses to overwrite `v1`. A changed target requires `version=2`, an
explicit reason, and an existing `v1/manifest.json`; prior bytes remain intact.
`load_freeze` restores the typed manifest. `verify_frozen` reports exact drift.
Never replace a manifest merely because verification reports drift.

Raw SHA-256 is authoritative. The auxiliary normalized SHA-256 only replaces CRLF
with LF. Spacing, comments, indentation and Unicode are intentionally not normalized;
this is not a Lean parser or a semantic equivalence test. Statement source and file
hash coincide because V0 freezes the entire file. External definitions are locked
by the toolchain and dependency manifest, not by per-definition Mathlib hashes.
The caller is responsible for listing all local definition sources and choosing a
faithful target. The checker does not establish informal/formal correspondence.

## Deterministic check

Before and after commands, the checker compares frozen raw hashes and dependency
identity. A mismatch returns `FROZEN_SOURCE_DRIFT` and cannot rebind the snapshot.
It runs fixed argument arrays with `shell=False`:

1. `<configured lake> build`
2. `<configured lake> env lean --stdin`, with a generated import, exact `#check`
   and `#print axioms` for the validated declaration.

There is no bundle command field. Repository paths are canonicalized; source paths
reject both Windows and POSIX traversal. Declaration/module names use a restricted
ASCII dotted-identifier grammar. The log must be outside the Lean repository and
must not already exist. `ELAN_HOME` is explicitly set for every subprocess (default
`D:/Tools/elan`), with the frozen toolchain override and configured Lake directory
first on PATH. Final checks never invoke `lake update` or cache download.

Output is streamed directly to the full log file. Each command retains at most
64 KiB in its typed result (configurable, bounded); an oversized axiom report fails
closed. Commands have a timeout and process-tree cleanup. On Windows this uses a
fixed `taskkill /PID <owned PID> /T /F` argument array, never a shell string.

The exact target must exist and its axiom report must parse. The only automatically
allowed axioms are `propext`, `Classical.choice`, `Quot.sound`; empty closure is also
valid. `sorryAx`, custom/unknown axioms, source `sorry`/`admit`/`axiom`, nonzero exits,
timeout, or unreadable reports prevent `checked`. All repository-owned `.lean`
sources are scanned, excluding `.lake` and `.git`; nested comments and strings are
excluded. `native_decide` is recorded separately. This conservative lexical scan is
an additional check, not a replacement for the kernel axiom closure.

The formal repository commit and source/dependency hashes identify the long-term
artifact. V0 does not create a repository mirror or a git bundle. Keep that commit
locally available. It does not verify compiler binaries or dependency caches against
an independent trust root; the pinned installed toolchain is part of the trusted
verification environment.

## Validation

Unit tests use temporary synthetic repositories and fake subprocess outputs. They
cover drift of statements, definitions and locks; version preservation; authority
boundaries; exact declarations; axioms; failures/timeouts; lexical scanning;
bounded capture/full logs; fixed commands and traversal rejection. They do not
download Mathlib. The real Lemma 4.1 checkout is a separate integration acceptance
artifact under `.local-eval/formalization-spike-v0/`, never real `.math-research`.
