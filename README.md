# Structured Math Research

A local **Research Ledger + Retrieval/Context + Research Workflow + Verification/Authority** system.

```text
RECORD → bounded context packet → external research → VERIFY → RECORD
```

Codex, Claude Code or another harness owns generation, coding and search. This package owns typed research memory, deterministic ingestion/retrieval, verification receipts, human authority and derived freshness. It contains no autonomous model loop, provider routing or Web application.

## Use from Codex

Python 3.11+:

One-time Windows setup from this checkout (use the existing `.venv-win`):

```powershell
$python = (Resolve-Path .venv-win/Scripts/python.exe).Path
& $python -m pip install -e '.[mcp]'
codex mcp add structured-math-research -- $python -B (Join-Path $PWD 'scripts/smr_mcp.py')
codex mcp list
codex mcp get structured-math-research --json
codex -C .
```

In a fresh Codex chat in the research project, ask naturally: “Continue PROBLEM-0001; first tell me where we left off.” The project `AGENTS.md` guides status/context lookup and provisional output capture. Nine tools are directly discoverable through MCP `tools/list`; no dispatcher is needed. Codex owns the conversation. The CLI below is for debugging and trusted human authority, not the primary chat interface.

CLI and IDE/desktop share Codex MCP configuration; start a fresh session after registration. CLI host calls and automatic cwd discovery have been exercised here; the already-open desktop session has not been reloaded or independently verified. See [MCP setup and smoke evidence](docs/codex-mcp.md).

`math-research` aliases `smr`. Without reinstalling entry points, use `python -m math_research.cli`. Initialize a new workspace explicitly with `smr --workspace /path/to/project init`. Missing state never initializes itself through MCP.

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

The optional stdio server directly exposes nine `research_*` tools: status, search, object windows, context/review packets, stale reports, provisional Episode/note ingestion and pending acceptance requests. There is no model-callable accept, shell, arbitrary filesystem, freeze or compiler tool. Tool results, including duplicated SDK text/structured representations, are bounded to 64 KiB; oversized results return structured errors. Mandatory context omissions/truncation remain explicit.

```sh
python -m pip install -e ".[mcp]"
python -m math_research.mcp.server --workspace /path/to/project
```

Workspace resolution: explicit `--workspace`, then `SMR_WORKSPACE`, then server cwd ancestors containing `.math-research`. The checkout wrapper preserves host cwd. A global registration works across research projects in the tested Codex CLI. Use a fixed absolute `--workspace` or `SMR_WORKSPACE` when another host does not pass its project cwd.

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
