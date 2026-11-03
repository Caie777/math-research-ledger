// Host activation only; research semantics remain in the unchanged Python MCP server.
const path = require('node:path');
const z = require('@deepseek-ai/schemastery');
const { readActivation, activate } = require('./activation.cjs');

exports.name = 'math-research-ledger-host';
exports.inject = ['agents', 'tools', 'commands'];
exports.Config = z.object({ python: z.string().required() });
exports.apply = function apply(ctx, { python }) {
  if (!path.isAbsolute(python)) throw new Error('Select an absolute persistent Python executable.');
  const mounted = new WeakMap();
  const usage = 'Explicitly enable Ledger with /math-research-ledger enable [workspace-relative directory]. '
    + 'The default is .math-research-ledger in this exact session root. No research tools are exposed before activation.';

  function sessionRoot(agent) {
    const root = agent.session.header.cwd;
    if (typeof root !== 'string' || !path.isAbsolute(root)) {
      throw new Error('NO_WORKSPACE: the Host must supply an absolute session header cwd.');
    }
    return root;
  }

  async function mount(agent, binding) {
    const previous = mounted.get(agent);
    if (previous) {
      if (previous.ledgerRoot !== binding.ledgerRoot) {
        throw new Error('ALREADY_ACTIVATED: this Agent is already bound; do not rebind a live Agent.');
      }
      return previous.ready;
    }
    const record = { ledgerRoot: binding.ledgerRoot };
    // Importing the SDK and starting Python both happen only after a valid pointer.
    record.ready = Promise.resolve().then(async () => {
      const mcp = require('@deepseek-ai/dsh-mcp-client');
      const fiber = agent.ctx.plugin(mcp, {
        serverName: 'math-research-ledger',
        transport: 'stdio',
        command: python,
        args: ['-B', '-m', 'math_research.mcp.server', '--workspace', '.'],
        cwd: binding.ledgerRoot,
        failOnStartupError: true,
        toolCallTimeoutMs: 120000,
      });
      try {
        await fiber;
        return binding;
      } catch (error) {
        await fiber.dispose();
        mounted.delete(agent);
        throw error;
      }
    });
    mounted.set(agent, record);
    return record.ready;
  }

  // Exactly one local pointer lookup; no scan, ancestor lookup, init or Python on a miss.
  ctx.on('agent/created', async ({ agent }) => {
    const binding = readActivation(sessionRoot(agent));
    if (binding) await mount(agent, binding);
  });

  // Native composer command, not a model tool. Never infer consent from conversation text.
  ctx.commands.register({
    name: 'math-research-ledger',
    description: 'Explicitly initialize/use MathResearch Ledger for this workspace',
    input: { hint: 'enable [workspace-relative directory]' },
    handler: async ({ agent, rawInput, attachments = [], signal }) => {
      try {
        if (attachments.length || /[\r\n\0]/u.test(rawInput)) {
          throw new Error('ACTIVATION_COMMAND: use one plain command line without attachments.');
        }
        const input = rawInput.trim();
        if (!input || input === 'help') return { kind: 'success', text: usage };
        const match = /^(?:enable|init)(?:[ \t]+(.+))?$/u.exec(input);
        if (!match) throw new Error(usage);
        let directory = match[1]?.trim() || '.';
        if (/^["']/u.test(directory)) {
          const quote = directory[0];
          if (directory.length < 2 || directory.at(-1) !== quote) {
            throw new Error('ACTIVATION_COMMAND: unmatched path quote.');
          }
          directory = directory.slice(1, -1);
        }
        if (agent.status !== 'idle' || typeof agent.runMaintenance !== 'function') {
          throw new Error('AGENT_BUSY: wait until the Agent is idle, then run the command again.');
        }
        // Maintenance latches new task input until init and MCP tool synchronization finish.
        return await agent.runMaintenance(async maintenanceSignal => {
          const combined = AbortSignal.any([signal, maintenanceSignal]);
          combined.throwIfAborted();
          const binding = await activate({ sessionRoot: sessionRoot(agent), directory, python, signal: combined });
          await mount(agent, binding);
          return { kind: 'success', text: `MathResearch Ledger enabled: ${binding.relative}. Eleven research tools are ready for the next task message.` };
        });
      } catch (error) {
        return { kind: 'error', text: error instanceof Error ? error.message : String(error) };
      }
    },
  });
};
