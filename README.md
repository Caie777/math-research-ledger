# Structured Math Research

A local workspace for **Memory → Retrieval / Context → Long-Horizon Research Agent**.
Keep mathematical investigations traceable and resume work from structured research state.

## What it does

- **Structured Research Memory:** archive Episodes and review proposed Claims, Proofs, Gaps and failed attempts. Model output stays provisional until Human Review.
- **Retrieval / Context Construction:** search prior work and assemble bounded context with provenance and research state.
- **Long-Horizon Research Agent:** explicitly start, stop and resume a bounded investigation, with checkpoints and public progress.

## Quick Start

Windows: Python 3.11+ and Node.js 20.19+ or 22.12+.

```powershell
git clone https://github.com/Caie777/structured-math-research.git
cd structured-math-research
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[openai,anthropic]"
npm --prefix web ci
.\start.bat
```

Subsequent launches: double-click `start.bat`. It builds the frontend when needed,
initializes a missing workspace, starts the local backend and opens your browser.
Keep the diagnostic console open; Ctrl+C stops the service. If the port is occupied,
use `start.bat --port 8001`. The service binds only to this machine's loopback interface.

Manual startup: build with `npm --prefix web run build`, initialize with
`math-research init`, then run `math-research serve` from your activated environment.

## Model Setup

Open **Research Settings → Models**. Choose your own model for `coordinator` and
`research`; `cheap_semantic` is reserved. Supported Web transports: OpenAI, Anthropic,
Mistral and local Ollama. Cloud providers use **your own API credentials**.

Keys are write-only in Settings and stored locally in ignored `.local/`, outside
research memory. Saving settings does not call a model. Browsing, deterministic
queries and Episode import work without model configuration; model actions require it.

**Codex/operator is optional:** select that entry explicitly to use your own installed,
authenticated Codex CLI and applicable product quota, without an API key. Web API
roles do not share Codex subscription credentials.

## Usage

1. Create a Problem and import the small [synthetic Episode](examples/demo_research_episode.md), or paste your own Markdown into **Import Research Episode**. Preview before committing.
2. Review proposals to build canonical memory. Ask the Coordinator `/portfolio`, `/state P1` or `/recall square` to inspect saved work; `/import` opens the importer.
3. Select an unresolved Claim/Gap and explicitly start Research Agent. Watch **Progress**, stop when needed, or resume an interrupted run with its original budgets.

Research data lives in ignored `.math-research/`; do not publish it or your credentials.
Review decisions and generated proofs are not formal verification certificates.

## Architecture

```text
Episode → deterministic parsing → Proposals → Human Review → Memory
                                                           ↓
                                              Retrieval / Context
                                                           ↓
                                                 Research Agent
                                                           ↓
                                                Episode + Progress
```

React uses same-origin `/api/*`; FastAPI serves the built Web app and local research
services. Model roles resolve through existing provider transports. Code is under
`src/math_research/` and `web/src/`.

For the small offline core suite: `python -m pip install -e ".[dev]"`, `python -m pytest`,
then `npm --prefix web test`. Models are mocked. Licensed under [Apache-2.0](LICENSE).
