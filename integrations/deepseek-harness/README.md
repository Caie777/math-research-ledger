# DeepSeek Harness integration

Use the same MathResearch Ledger MCP server and ledger as Codex. Do not duplicate the
core or run a daemon. Nothing is mounted by default; omit --patch to leave Ledger OFF.

The installed Desktop CLI is 0.2.1-rc.2. It already ships the matching official
@deepseek-ai/dsh-mcp-client; do not install an unrelated or older rc. For another version,
check dsh --version, dsh --help and the official MCP client reference first.

Install MathResearch Ledger .[mcp] into a Python environment, open any initialized
Research Workspace, then opt in per invocation:

```powershell
$env:MRL_PYTHON = '<Python environment>/Scripts/python.exe'
dsh --profile headless --patch '<source>/integrations/deepseek-harness/math-research-ledger.patch.yml' '<task>'
```

The stdio child's cwd is process.cwd(), not any fixed user research path. Tools appear
as mcp__math-research-ledger__research_status and the other eight stable raw names.
The server supplies harness-agnostic instructions; workspace AGENTS is supplementary.

## Reuse an existing Desktop account

The shipped headless profile disables stored credentials and their authorization/account
consumers. A missing DEEPSEEK_API_KEY on deepseek-official does not mean Desktop account
authentication is unavailable. Use the optional, one-shot desktop-account.patch.yml:

```powershell
dsh --profile headless --patch '<source>/integrations/deepseek-harness/desktop-account.patch.yml' --patch '<source>/integrations/deepseek-harness/math-research-ledger.patch.yml' '<synthetic task>'
```

This enables credentials, authorization and deepseek-account for that invocation and
selects the account provider. It reuses the existing DSH_HOME; it does not create a second
credential store, copy tokens, change global settings, sign out, or fall back to an API key.
Never paste or commit secrets. Verify only getState().status through the official account
service when debugging login presence; do not print credential records. The overlay selects
the shipped deepseek-flash model; change that deliberate test choice if another supported
account model is wanted. Account billing is handled by DeepSeek's account provider.

## Reproducible discovery without a model

`discovery-smoke.cjs` boots the installed real DSH profile and ToolRuntime. A separate
one-shot probe patch disables headless-startup/headless-runner and sets tools mode native;
it changes no persistent profile. The probe verifies nine tools, reads synthetic checkpoint
A and can write synthetic B. It does not substitute a fake MCP client or send model requests.
The actual account-authenticated model run is a separate acceptance check.

Only synthetic engineering fixtures are used. See [public-safe results](../../docs/finalization-report.md).

Official references:
[MCP client](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/mcp/mcp-client/README.md),
[headless stored authentication](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/bundle/headless/README.md#credentials),
[account route](https://github.com/deepseek-ai/deepseek-harness/blob/master/packages/llm/llm-deepseek-account/README.md).
