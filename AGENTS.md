# Tool development

- This checkout contains structured-math-research tooling. Do not conduct mathematical
  research here or create an active research workspace in the repository root.
- Keep core/ledger/retrieval/verification independent of CLI, MCP and external harnesses.
  CLI/MCP call shared deterministic services; do not duplicate business decisions in adapters.
- Preserve server-side automated-scope, provisional-write and human-authority enforcement.
  Prompts and tool descriptions do not replace these gates.
- Do not directly edit real research data. Use synthetic temporary workspaces for tests;
  corpus migration or read-only real-data checks require an explicit task scope.
- Run relevant tests, full pytest, Ruff lint/format, mypy and git diff checks for changes.
  MCP transport tests exercise real stdio; keep stdout protocol-only and outputs bounded.
- Research workspaces have separate AGENTS.md and backup/version history. Tool upgrades
  must not rewrite corpus history or absolute historical provenance.
