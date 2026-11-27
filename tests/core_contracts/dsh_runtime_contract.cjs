'use strict';

// Exercises the npm payload, with only DSH modules and PATH fixture Python stubbed.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const cp = require('node:child_process');
const Module = require('node:module');
const [first, second, realPython] = process.argv.slice(2);
const base = path.dirname(first);
const state = '.math-research-ledger';
const pointer = '.math-research-ledger-link';
const executable = process.platform === 'win32' ? 'python.exe' : 'python3';
const oldBin = path.join(base, '失效 runtime');
const newBin = path.join(base, '新 runtime');
const oldPython = path.join(oldBin, executable);
const newPython = path.join(newBin, executable);
const originalPath = process.env.PATH;
const load = Module._load;
const execFile = cp.execFile;
const probes = [];
const launches = [];
let probeStatus = 'MRL_RUNTIME_VERSION:1.4.0';
Module._load = function (id, ...args) {
  if (id === '@deepseek-ai/schemastery') return { object: fields => fields, string: () => 'optional' };
  if (id === '@deepseek-ai/dsh-mcp-client') return {};
  return load.call(this, id, ...args);
};
cp.execFile = function (file, args, options, callback) {
  if (args.includes('-c')) probes.push({ file, args, options });
  if (file === newPython && args.includes('-c')) {
    return queueMicrotask(() => callback(null, `${probeStatus}\n`));
  }
  return execFile.call(this, file, args, options, callback);
};

function setup(packageDir, config = {}) {
  let created, command;
  const plugin = require(path.join(packageDir, 'index.cjs'));
  plugin.apply({
    on(name, listener) { assert.equal(name, 'agent/created'); created = listener; },
    commands: { register(definition) { command = definition.handler; } },
  }, config);
  return { created, command };
}

function agentAt(cwd) {
  fs.mkdirSync(cwd);
  return {
    session: { header: { cwd } }, status: 'idle',
    runMaintenance: work => work(new AbortController().signal),
    ctx: { plugin(_mcp, config) { launches.push(config); return Promise.resolve(); } },
  };
}

(async () => {
  const root = path.join(base, '数学 workspace');
  const agent = agentAt(root);
  const legacy = setup(first, { python: oldPython });
  process.env.PATH = '.';
  await legacy.created({ agent });
  assert.equal(probes.length, 0);
  const run = (host, rawInput) => host.command({ agent, rawInput, signal: new AbortController().signal });
  assert.match((await run(legacy, 'enable ../escape')).text, /^INVALID_ACTIVATION_PATH:/);
  assert.equal(probes.length, 0);
  assert.match((await run(legacy, 'enable missing/parent')).text, /^MRL_RUNTIME_UNAVAILABLE:/);
  assert.deepEqual(fs.readdirSync(root), []);
  assert.equal(launches.length, 0);

  // Relocate just the installed package, leaving the old executable unavailable.
  fs.renameSync(first, second);
  const host = setup(second);
  const nested = path.join(root, '研究 notes');
  fs.mkdirSync(path.join(nested, state), { recursive: true });
  fs.writeFileSync(path.join(root, pointer), `研究 notes/${state}\n`);
  await assert.rejects(host.created({ agent }), /MRL_RUNTIME_UNAVAILABLE: No .* Host PATH/);
  fs.mkdirSync(newBin);
  fs.writeFileSync(newPython, 'synthetic executable', { mode: 0o755 });
  process.env.PATH = [oldBin, `"${newBin}"`].join(path.delimiter);
  await assert.rejects(setup(second, { python: oldPython }).created({ agent }), /Configured Python/);
  assert.equal(launches.length, 0, 'a stale explicit setting never falls through');
  await assert.rejects(host.created({ agent }), { code: 'MRL_RUNTIME_INCOMPATIBLE' });
  const incompatible = agentAt(path.join(base, '旧版 runtime workspace'));
  const rejection = await host.command({ agent: incompatible, rawInput: 'enable', signal: new AbortController().signal });
  assert.equal(rejection.kind, 'error');
  assert.match(rejection.text, /^MRL_RUNTIME_INCOMPATIBLE: .* 1\.4\.0;/);
  assert.ok(rejection.text.includes('pip install --upgrade "math-research-ledger[mcp]>=1.5.0,<1.6"'));
  assert.deepEqual(fs.readdirSync(incompatible.session.header.cwd), []);
  assert.equal(launches.length, 0);
  probeStatus = 'MRL_RUNTIME_READY';
  await host.created({ agent }); // Same instance can retry after a runtime repair.
  assert.equal(launches.length, 1);
  assert.equal(launches[0].command, newPython);
  assert.equal(launches[0].cwd, nested);
  assert.deepEqual(launches[0].args, ['-I', '-B', '-m', 'math_research.mcp.server', '--workspace', '.']);
  assert.equal(probes.at(-1).options.cwd, second);
  assert.equal(fs.readFileSync(path.join(root, pointer), 'utf8'), `研究 notes/${state}\n`);

  // Real interpreter probe and CLI init; only the DSH transport is stubbed.
  process.env.PATH = originalPath;
  const freshRoot = path.join(base, '新 workspace');
  const fresh = agentAt(freshRoot);
  const explicit = setup(second, { python: realPython });
  const result = await explicit.command({ agent: fresh, rawInput: 'enable', signal: new AbortController().signal });
  assert.equal(result.kind, 'success', result.text);
  assert.equal(fs.readFileSync(path.join(freshRoot, pointer), 'utf8'), `${state}\n`);
  assert.equal(launches.at(-1).command, realPython);
})().catch(error => { console.error(error); process.exitCode = 1; });
