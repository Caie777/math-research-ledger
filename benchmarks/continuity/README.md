# Frozen continuity evaluation

This is an engineering benchmark, not mathematical research or an LLM evaluation.
It makes actual `LedgerAdapter.call` invocations against isolated synthetic workspaces.
There are 18 English/Chinese task inputs, three strategies, and budgets 2000/8000/16000.
Gold is scored after replay. Production modules never import these fixtures or labels.

Run from the tool repository with its development Python:

```powershell
.\.venv-win\Scripts\python.exe scripts/evaluate_continuity.py --output dist/continuity-new-run
```

The output directory must be new. Every budget builds one synthetic seed and copies
identical bytes into independent A/B/C workspaces. No real workspace option is accepted.
The terminal checkpoint previews and ingests only a synthetic provisional increment.
Fixture setup uses synthetic human decisions and an explicitly fake checker; it does
not supply a mathematical verifier, model route, compiler or research agent.

- **A / Heavy:** search and rebuild context at each non-checkpoint task, with exact
  checks for premise decisions.
- **B / Session-only:** status/context at start; no more reads until checkpoint.
- **C / Event-triggered:** status/context at start; narrow search or exact reads on
  declared decision events; no tool calls during the three local reasoning tasks.
- All strategies preview once and ingest once at the declared meaningful checkpoint.

The external fixture changes a definition after session restore, before a premise
reuse decision. This measures exposure to stale memory; it does not assert that a
real model necessarily makes the corresponding reasoning error.

Report denominators, safety evidence coverage and output costs, not just recall.
Missing memory is not silently counted as a correct safety check. The fake equality
checker does not confer `trusted_formal_premise`. A known irrelevant historical
source shares query wording: its false positive remains a scored limitation, distinct
from a forbidden cross-Problem leak. Gold must not be changed to improve that score.

MUST recall measures the four frozen required identities actually present as MUST
items, not whether all proof bodies fit. Truncation and omissions are separate fields.
Key-source recall@10 refers to five frozen memory document refs (including failed
routes and counterexamples), not necessarily raw Episodes or published papers.
JSON result bytes are measured at the adapter boundary, not as SDK wire bytes or
model tokenizer counts. `token_estimate` uses the production UTF-8 estimator.

Frozen inputs (2026-10-22):

| File | SHA-256 |
|---|---|
| tasks.json | 49ecc8711e0b1d60697a4f8392398412971e8d54923de2d6338f4ca9804cb8b9 |
| gold.json | a35eeaa335f21fb23d00b47866cd6185fa3b19e355b21121ec9d4e1421e8fd60 |

The regression test pins these hashes. Review and explicitly update the benchmark
version when changing tasks or judgments; never feed gold to the ranker.
