# Checkpoint-local precision replay

Engineering-only synthetic records, separate from the frozen bilingual continuity gold.
Production code does not import this fixture. No real-data path or model is used.

From the tool repository:

```powershell
.\.venv-win\Scripts\python.exe scripts/evaluate_context_precision.py --output dist/precision-new
```

`--output` must be a new directory. To reproduce the previous implementation, supply
`--runtime-source` pointing at an explicitly retained old plugin's `src` directory.
The replay code, graph roles and content requirements stay the same for both runs.
Do not change judgments to improve results. No actual research is represented here.

The fixture has a primary, selected Gap, direct input, three checkpoint outputs
(including a large proof), a direct failed route and counterexample, an unrelated
same-Problem route with strong lexical overlap, and an old advisory Episode.
Budgets: 2000/8000/16000. MUST gold has three identities; SHOULD gold has six.

The driver restores status/context, reads any still-missing mandatory content and
the large proof, and restores missing produced/negative navigation by exact ID.
It does not require all optional mathematical bodies for basic operational recovery.
Those content requirements are declared by the fixture, not decisions measured from
a model. Call counts are an equivalent workflow comparison, not the real 12-call trace.

Metrics include identity/SHOULD recall, irrelevant item count and serialized bytes /
UTF-8 estimated tokens, duplicate identities, proof bytes that would be reread,
actual exact-read/restore calls, required omissions, unsafe premise flags and zero
local-reasoning calls. A page continuation is necessary content access, not automatically
duplicate waste. Zero unsafe counts do not establish mathematical correctness.
At 2k, omitted SHOULD navigation is expected and separately visible in SHOULD recall.

See [results and real-data read-only limits](../../docs/archive/2026-10/context-precision-after-vertical-slice-2026-10-22.md).
