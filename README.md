# Structured Math Research

A local **Research Ledger + Retrieval/Context + Research Workflow + Verification/Authority** system.

```text
RECORD → bounded context packet → external research → VERIFY → RECORD
```

Codex, Claude Code or another harness owns generation, coding and search. This package owns typed research memory, deterministic ingestion/retrieval, verification receipts, human authority and derived freshness. It contains no autonomous model loop, provider routing or Web application.

## Install and inspect

Python 3.11+:

```sh
python -m pip install -e ".[dev]"
smr --help
smr --workspace /path/to/project status
smr --workspace /path/to/project ledger list
```

`math-research` aliases `smr`. Without reinstalling entry points, use `python -m math_research.cli`. Initialize a new workspace explicitly with `smr --workspace /path/to/project init`.

References are qualified: `PROBLEM-0001:claim:CLAIM-0001`. Existing disk IDs are unchanged. A Gap is a Claim with `OPEN_GAP`; verifier submissions and research proofs have separate namespaces.

## Research workflow

```sh
smr -w /path/to/project search "an open obstacle" --problem PROBLEM-0001
smr -w /path/to/project context export PROBLEM-0001:claim:CLAIM-0001 --budget 8000
smr -w /path/to/project ingest source PROBLEM-0001 selected-source.pdf
smr -w /path/to/project ingest episode PROBLEM-0001 output.md --provenance "external harness/session" --preview
smr -w /path/to/project ingest episode PROBLEM-0001 output.md --provenance "external harness/session"
smr -w /path/to/project ingest review PROBLEM-0001 CANDIDATE-ID accept
smr -w /path/to/project review packet PROBLEM-0001:claim:CLAIM-0001
smr -w /path/to/project review record external-review.json
smr -w /path/to/project stale report --problem PROBLEM-0001
```

Replace example IDs with actual workspace objects. Ingestion creates provisional records. Human canonicalization records memory; it does not verify mathematics. Packets label TRUSTED / PROVISIONAL / STALE / FAILED / HISTORICAL and explicitly report missing/truncated mandatory context. The budget counts the entire compact JSON using UTF-8 bytes / 3, not a model tokenizer.

## Verification and human authority

Reusable Lean freeze/check preserves exact source hashes, locks, declaration/type checks, axiom policy and full logs. `formal freeze` / `formal check` call shared services. The service requires an exact target type contract. No proof search runs here.

Exact/validated computation uses a locally registered deterministic `ExactChecker` protocol and certificate manifests. No domain-specific exact checker or experiment executor is bundled. External ReviewReport data always remains ADVISORY, including NO_GAP_FOUND.

```sh
smr -w /path/to/project verify show VERIFY-ID
smr -w /path/to/project acceptance request PROBLEM-0001:formal_bundle:FORMAL-ID VERIFY-ID
smr -w /path/to/project acceptance pending
smr -w /path/to/project acceptance accept REQUEST-ID --actor "human operator" --rationale "reviewed exact scope" --correspondence "informal/formal correspondence rationale"
```

Canonical ≠ verified; checked ≠ accepted; working premise ≠ trusted formal premise. Acceptance records immutable exact version/dependency receipts. Drift disables current trusted use without erasing history. Formal acceptance requires human correspondence.

The human CLI is a trusted operator channel. Automated scope / SMR_AUTOMATED_RESEARCH=1 (legacy MCH_AUTOMATED_RESEARCH is also honored) reject human writes. This is an execution boundary, not authentication against a process with unrestricted shell/filesystem access. Do not give an untrusted harness that channel.

## MCP

An optional stdio skeleton and bounded adapter expose search, scoped object windows, context export, acceptance requests and stale reports. There is no model-callable accept, shell, arbitrary filesystem, freeze or compiler tool.

```sh
python -m pip install -e ".[mcp]"
smr-mcp --workspace /path/to/project
```

Core/CLI work without the optional SDK. See [architecture and compatibility](docs/architecture.md), [Episode contract](docs/research-episode.md), [formal verification](docs/formalization-v0.md), and [中文说明](README.zh-CN.md).

## Checks

```sh
python -m pytest
ruff check src tests
ruff format --check src tests
mypy
python -m build
```

Tests use synthetic temporary stores and fake compiler results. No real-paper formalization is part of the suite. Apache-2.0.
