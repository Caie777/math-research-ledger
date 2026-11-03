/* Actual DSH services/factory activation smoke: A–F workspace gating, no model.
 * Args: DSH_NODE_MODULES PERSISTENT_PYTHON NEW_OUTPUT_UNDER_DIST [REAL_WORKSPACE_WITH_POINTER]
 * ASAR installations must use Desktop's Electron Node mode; ordinary installs use Node.
 */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const cp = require('node:child_process');
const { syncBuiltinESMExports } = require('node:module');
const { pathToFileURL } = require('node:url');
const [modules, python, output, realWorkspace] = process.argv.slice(2);
const expectedTools = [
  'research_create_problem', 'research_update_problem', 'research_status',
  'research_search', 'research_get_object', 'research_context_packet',
  'research_review_packet', 'research_stale_report', 'research_ingest_episode',
  'research_save_note', 'research_request_acceptance',
].map(n => 'mcp__math-research-ledger__' + n).sort();
const checkout = path.resolve(__dirname, '../..');
const base = path.resolve(output || '.');
assert(base.startsWith(path.join(checkout, 'dist') + path.sep) && !fs.existsSync(base));
fs.mkdirSync(base, { recursive: true });
process.env.DSH_HOME = path.join(base, 'home');
const launches = [];
const spawn = cp.spawn;
cp.spawn = function(command, args, options) {
  const child = spawn.call(this, command, args, options);
  if (Array.isArray(args) && args.includes('math_research.mcp.server')) {
    launches.push({ child, pid: child.pid, cwd: options.cwd, args });
  }
  return child;
};
syncBuiltinESMExports();
const load = name => import(pathToFileURL(path.join(modules, '@deepseek-ai', name, 'lib/index.js')).href);
const report = { cases: {}, model_called: false };
function record(name, facts) {
  report.cases[name] = { passed: true, ...facts };
  fs.writeFileSync(path.join(base, 'acceptance.json'), JSON.stringify(report, null, 2));
  console.log(name, JSON.stringify(facts));
}
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function gone(list) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    if (list.every(p => p.child.exitCode !== null || p.child.signalCode !== null)) return;
    await sleep(50);
  }
  assert.fail('MCP transport/process did not exit after Agent disposal');
}

(async () => {
  const version = JSON.parse(fs.readFileSync(path.join(modules, '@deepseek-ai', 'dsh/package.json'))).version;
  const versions = ['dsh-agent', 'dsh-mcp-client'].map(n => JSON.parse(fs.readFileSync(path.join(modules, '@deepseek-ai', n, 'package.json'))).version);
  assert(versions.every(v => v === version));
  report.dsh = version;
  const rootA = path.join(base, 'ordinary-A');
  const rootB = path.join(base, 'default-B');
  const rootC = path.join(base, 'custom-C');
  const rootE = path.join(rootB, 'child-no-pointer');
  for (const p of [rootA, rootB, rootC, rootE]) fs.mkdirSync(p);
  const { Context } = await load('cordis');
  let ctx = new Context();
  const handles = [];
  let host;
  let serial = 0;
  const names = agent => ctx.tools.schemas(agent).map(t => t.name).filter(n => n.startsWith('mcp__math-research-ledger__')).sort();
  const create = async root => {
    const handle = await ctx.agents.create({ sessionId: 'fixture-' + (++serial), meta: root ? { cwd: root } : {}, agentOptions: { provider: 'no-network', model: 'fixture' } });
    handles.push(handle);
    return handle;
  };
  const run = async (handle, line) => ctx.commands.execute(handle.agent, line, [], new AbortController().signal);
  const call = async (handle, tool = 'research_status', args = {}) => {
    const r = await ctx.tools.execute({ callId: 'fixture-' + (++serial), name: 'mcp__math-research-ledger__' + tool, arguments: args, agent: handle.agent, signal: new AbortController().signal });
    if (r.value?.structuredContent) return r.value.structuredContent;
    if (r.isError && r.error?.message) {
      const payload = JSON.parse(r.error.message);
      assert(payload.error?.code, 'Expected a structured MCP failure');
      return payload;
    }
    assert.fail('Tool execution failed without a structured result');
  };
  const live = () => launches.filter(p => p.child.exitCode === null && p.child.signalCode === null);
  const plugin = require('./host-plugin/index.cjs');
  async function boot() {
    for (const n of ['dsh-session', 'dsh-agent', 'dsh-llm', 'dsh-system-prompt', 'dsh-tools', 'dsh-session-projection', 'dsh-subprocess-local', 'dsh-commands']) await ctx.plugin((await load(n)).default, {});
    const persistence = await load('dsh-session-persistence-jsonl');
    await ctx.plugin(persistence, { root: path.join(base, 'sessions'), compression: 'none' });
    await ctx.plugin((await load('dsh-agent-loop')).default, { agents: [], maxParallelToolCalls: 10 });
    host = await ctx.plugin(plugin, { python });
  }
  try {
    await boot();
    // A: ordinary workspace, no activation metadata -> no tools, no process, no files.
    const a = await create(rootA);
    assert.equal(names(a.agent).length, 0);
    assert.equal(launches.length, 0);
    assert.equal(fs.existsSync(path.join(rootA, '.math-research-ledger')), false);
    assert.equal(fs.existsSync(path.join(rootA, '.math-research-ledger-link')), false);
    const help = await run(a, '/math-research-ledger help');
    assert.equal(help.result.kind, 'success');
    assert.equal(names(a.agent).length, 0);
    record('absence_no_tools_no_process_no_state', { tools: 0, python_processes: 0, state_created: false, pointer_created: false, help_exposes_no_tools: true });

    // B: explicit native command initializes the default path, then 11 tools.
    const b = await create(rootB);
    const enableB = await run(b, '/math-research-ledger enable');
    assert.equal(enableB.result.kind, 'success', enableB.result.text);
    assert.equal(names(b.agent).length, 11);
    assert.equal(fs.readFileSync(path.join(rootB, '.math-research-ledger-link'), 'utf8').trim(), '.math-research-ledger');
    const bStatus = await call(b);
    assert.equal(path.resolve(bStatus.workspace_root), path.resolve(rootB));
    const bNext = await create(rootB);
    assert.deepEqual(names(bNext.agent), expectedTools);
    assert.equal(path.resolve((await call(bNext)).workspace_root), path.resolve(rootB));
    record('explicit_default_activation', { tools_after_command: 11, new_agent_tools: 11, status_ok: true, pointer: '.math-research-ledger', ledger_created: true });

    // C: explicit subdirectory inside the exact session root.
    const c = await create(rootC);
    assert.equal((await run(c, '/math-research-ledger enable research/foo')).result.kind, 'success');
    assert.equal(fs.readFileSync(path.join(rootC, '.math-research-ledger-link'), 'utf8').trim(), 'research/foo/.math-research-ledger');
    assert.equal(fs.existsSync(path.join(rootC, 'research/foo/.math-research-ledger')), true);
    assert.equal(path.resolve((await call(c)).workspace_root), path.resolve(rootC, 'research/foo'));
    assert.deepEqual(names((await create(rootC)).agent), expectedTools);
    record('explicit_subdirectory_activation', { tools: 11, bound: 'research/foo', status_root_matches: true });

    // D: escapes and non-enable input are rejected without side effects.
    const d = await create(rootA);
    const before = fs.readdirSync(rootA).sort();
    for (const line of ['/math-research-ledger enable ../escape', '/math-research-ledger enable ' + path.dirname(base), '/math-research-ledger status']) {
      const result = await run(d, line);
      assert.equal(result.result.kind, 'error');
    }
    assert.deepEqual(fs.readdirSync(rootA).sort(), before);
    assert.equal(names(d.agent).length, 0);
    record('reject_outside_and_unknown', { rejected: 3, side_effects: false, tools: 0 });

    // E: a parent with a Ledger never grants a child workspace without its own pointer.
    const e = await create(rootE);
    assert.equal(names(e.agent).length, 0);
    assert.equal(fs.existsSync(path.join(rootE, '.math-research-ledger-link')), false);
    assert.equal(fs.existsSync(path.join(rootE, '.math-research-ledger')), false);
    assert.equal(launches.filter(p => p.cwd === rootE).length, 0);
    record('no_ancestor_search', { parent_ledger: 'default-B', child_tools: 0, child_python_processes: 0, child_state_created: false });

    // Global registration holds no Ledger tools for any Agent by default.
    assert.deepEqual(ctx.tools.schemas().map(t => t.name).filter(n => n.startsWith('mcp__math-research-ledger__')), []);
    record('global_tools_absent', { global_ledger_tools: 0, host_still_loaded: true });

    if (realWorkspace) {
      // F: existing real Ledger reached only through its explicit pointer.
      const real = await create(path.resolve(realWorkspace));
      assert.deepEqual(names(real.agent), expectedTools);
      const status = await call(real);
      assert.equal(path.resolve(status.workspace_root), path.resolve(realWorkspace));
      const search = await call(real, 'research_search', { query: 'PROBLEM-0001', limit: 1 });
      assert(Array.isArray(search.hits));
      record('existing_real_workspace_pointer', { tools: 11, status_ok: true, search_ok: true, problems: status.problems });
    }
  } finally {
    for (const h of handles.reverse()) await h.dispose();
    handles.length = 0;
    if (host) await host.dispose();
    await ctx.fiber.dispose();
    await gone(launches);
    report.launches = launches.map(({ pid, cwd, args }) => ({ pid, cwd, args }));
    fs.writeFileSync(path.join(base, 'acceptance.json'), JSON.stringify(report, null, 2));
  }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
