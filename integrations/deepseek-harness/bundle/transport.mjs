// Deployment settings only. Workspace resolution and all research decisions stay in Python.
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export async function transportConfig(config = {}, env = process.env, root = fileURLToPath(new URL('.', import.meta.url))) {
  let python = config.python || env.MRL_PYTHON;
  if (!python) {
    try {
      python = JSON.parse(await readFile(path.join(root, '.runtime.json'), 'utf8')).python;
    } catch (error) {
      if (error.code !== 'ENOENT') throw new Error('Ledger: invalid local .runtime.json; rerun python install.py.', { cause: error });
    }
  }
  if (typeof python !== 'string' || !path.isAbsolute(python) || !existsSync(python)) {
    throw new Error('Ledger Python is unavailable. Run python install.py in the installed bundle, or configure python with an existing absolute interpreter path that has MathResearch Ledger[mcp].');
  }
  const args = ['-B', '-m', 'math_research.mcp.server'];
  if (config.workspace) args.push('--workspace', config.workspace);
  return { serverName: 'math-research-ledger', transport: 'stdio', command: python,
    args, cwd: process.cwd(), failOnStartupError: true, env: {},
    toolCallTimeoutMs: 60000, maxInstructionBytes: 32768,
    reconnect: { enabled: true, initialDelayMs: 500, maxDelayMs: 30000, maxAttempts: 10 } };
}
