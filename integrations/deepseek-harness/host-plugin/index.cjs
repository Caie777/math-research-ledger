// Host composition only; all research behavior belongs to the Python MCP server.
const path = require('node:path');
const z = require('@deepseek-ai/schemastery');
const mcp = require('@deepseek-ai/dsh-mcp-client');

exports.name = 'math-research-ledger-host';
exports.inject = ['agents', 'tools'];
exports.Config = z.object({ python: z.string().required() });
exports.apply = async function apply(ctx, { python }) {
  if (!path.isAbsolute(python)) throw new Error('Select an absolute persistent Python executable.');
  // DSH serially awaits creation listeners before publishing a usable Agent.
  ctx.on('agent/created', async ({ agent }) => {
    const root = agent.session.header.cwd;
    if (typeof root !== 'string' || !path.isAbsolute(root)) {
      throw new Error('NO_WORKSPACE: the Host must supply an absolute session header cwd.');
    }
    await agent.ctx.plugin(mcp, {
      serverName: 'math-research-ledger',
      transport: 'stdio',
      command: python,
      args: ['-B', '-m', 'math_research.mcp.server', '--workspace', '.'],
      cwd: root,
      failOnStartupError: true,
      toolCallTimeoutMs: 120000,
    });
  });
};
