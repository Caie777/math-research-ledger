'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const childProcess = require('node:child_process');
const { POINTER, readActivation, activate } = require('../../integrations/deepseek-harness/host-plugin/activation.cjs');

const STATE = '.math-research-ledger';
const python = process.execPath; // Mocked execFile only: never invoke Python or Core here.

function fixture(t) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'mrl-activation-'));
  const root = path.join(base, 'session');
  fs.mkdirSync(root);
  t.after(() => fs.rmSync(base, { recursive: true, force: true }));
  return { base: fs.realpathSync(base), root: fs.realpathSync(root) };
}

function fakeState(root, directory = '.') {
  const state = path.join(root, directory, STATE);
  fs.mkdirSync(state, { recursive: true });
  return fs.realpathSync(state);
}

function expectCode(code) {
  return error => error.code === code && error.message.startsWith(`${code}:`);
}

function mockInit(t, fn) {
  const original = childProcess.execFile;
  const calls = [];
  childProcess.execFile = (file, args, options, callback) => {
    calls.push({ file, args, options });
    fn({ file, args, options, callback, count: calls.length });
  };
  t.after(() => { childProcess.execFile = original; });
  return calls;
}

function forbidInit(t) {
  return mockInit(t, () => { throw new Error('Unexpected initialization CLI invocation.'); });
}

function writePointer(root, text) {
  fs.writeFileSync(path.join(root, POINTER), text);
}

function makeLink(t, target, link, type) {
  try {
    fs.symlinkSync(target, link, type);
    return true;
  } catch (error) {
    if (['EPERM', 'EACCES', 'ENOTSUP', 'EINVAL', 'UNKNOWN'].includes(error.code)) {
      t.skip(`This environment cannot create ${type} links: ${error.code}`);
      return false;
    }
    throw error;
  }
}

test('API exports and absent exact pointer do no Python, scanning, or ancestor lookup', t => {
  const { base, root } = fixture(t);
  fakeState(base);
  writePointer(base, `${STATE}\n`);
  fakeState(root, 'unrelated-a');
  fakeState(root, 'unrelated-b');
  const calls = forbidInit(t);
  const originalReadDir = fs.readdirSync;
  const originalLstat = fs.lstatSync;
  const inspected = [];
  fs.readdirSync = () => { throw new Error('Recursive/flat directory scanning is forbidden.'); };
  fs.lstatSync = function (filename, ...args) {
    inspected.push(filename);
    return originalLstat.call(fs, filename, ...args);
  };
  try {
    assert.equal(POINTER, '.math-research-ledger-link');
    assert.equal(readActivation(root), null);
    assert.deepEqual(inspected, [root, path.join(root, POINTER)]);
    assert.equal(calls.length, 0);
  } finally {
    fs.readdirSync = originalReadDir;
    fs.lstatSync = originalLstat;
  }
});

test('default existing state binds without CLI, preserves data and is idempotent', async t => {
  const { root } = fixture(t);
  const state = fakeState(root);
  const oldData = path.join(state, 'old-ledger.json');
  fs.writeFileSync(oldData, 'historical data');
  const before = fs.statSync(oldData);
  const calls = forbidInit(t);
  const expected = { root, state, ledgerRoot: root, relative: STATE };
  assert.deepEqual(await activate({ sessionRoot: root, existingOnly: true }), expected);
  const pointerBefore = fs.statSync(path.join(root, POINTER));
  assert.deepEqual(readActivation(root), expected);
  assert.deepEqual(await activate({ sessionRoot: root }), expected);
  assert.equal(fs.readFileSync(oldData, 'utf8'), 'historical data');
  assert.equal(fs.statSync(oldData).mtimeMs, before.mtimeMs);
  assert.equal(fs.statSync(path.join(root, POINTER)).mtimeMs, pointerBefore.mtimeMs);
  assert.equal(calls.length, 0);
});

test('custom relative and absolute-inside targets return canonical slash-relative binding', async t => {
  const { root } = fixture(t);
  const state = fakeState(root, path.join('Research Space', 'nested'));
  forbidInit(t);
  const expected = {
    root, state, ledgerRoot: path.dirname(state), relative: `Research Space/nested/${STATE}`,
  };
  assert.deepEqual(await activate({ sessionRoot: root, directory: 'Research Space/nested', existingOnly: true }), expected);
  assert.deepEqual(await activate({ sessionRoot: root, directory: path.dirname(state) }), expected);
  assert.equal(fs.readFileSync(path.join(root, POINTER), 'utf8'), `${expected.relative}\n`);
});

test('an existing target state skips initialization even without existingOnly', async t => {
  const { root } = fixture(t);
  fakeState(root, 'data');
  forbidInit(t);
  const result = await activate({ sessionRoot: root, directory: 'data' });
  assert.equal(result.ledgerRoot, path.join(root, 'data'));
});

test('existingOnly never makes missing parents or guesses among existing states', async t => {
  const { root } = fixture(t);
  fakeState(root, 'a');
  fakeState(root, 'b');
  forbidInit(t);
  await assert.rejects(activate({ sessionRoot: root, existingOnly: true }), expectCode('INVALID_ACTIVATION_PATH'));
  await assert.rejects(activate({ sessionRoot: root, directory: 'missing/deep', existingOnly: true }), expectCode('INVALID_ACTIVATION_PATH'));
  assert.equal(fs.existsSync(path.join(root, 'missing')), false);
  assert.equal(fs.existsSync(path.join(root, POINTER)), false);
  assert.equal(readActivation(root), null);
});

test('reject parent components, outside absolutes and foreign Windows paths before any writes', async t => {
  const { base, root } = fixture(t);
  forbidInit(t);
  const directories = [
    '..', 'inside/../inside', '../outside', 'inside\\..\\inside',
    path.join(base, 'outside'), 'C:\\outside', 'C:relative', '\\\\server\\share\\data',
  ];
  for (const directory of directories) {
    await assert.rejects(activate({ sessionRoot: root, directory, python }), expectCode('INVALID_ACTIVATION_PATH'), directory);
  }
  assert.deepEqual(fs.readdirSync(root), []);
  assert.equal(fs.existsSync(path.join(base, 'outside')), false);
});

test('malformed pointers never fall back to discovery or initialization', async t => {
  const { base, root } = fixture(t);
  fakeState(root);
  forbidInit(t);
  const bad = [
    '', '\n', `${STATE}\nsecond`, `${STATE}\n\n`, `${STATE}\0`,
    `../${STATE}`, `a/../${STATE}`, path.join(base, STATE),
    `C:\\outside\\${STATE}`, `C:relative/${STATE}`, `a\\${STATE}`,
    'not-the-state-directory', `${STATE}/`, Buffer.from([0xc3, 0x28]),
    Buffer.alloc(4097, 97),
  ];
  for (const content of bad) {
    writePointer(root, content);
    assert.throws(() => readActivation(root), expectCode('INVALID_ACTIVATION_POINTER'));
    await assert.rejects(activate({ sessionRoot: root, python }), expectCode('INVALID_ACTIVATION_POINTER'));
    assert.deepEqual(fs.readFileSync(path.join(root, POINTER)), Buffer.from(content));
  }
});

test('a valid-looking pointer to a missing state or regular file is an explicit error', async t => {
  const { root } = fixture(t);
  forbidInit(t);
  writePointer(root, `missing/${STATE}\n`);
  assert.throws(() => readActivation(root), expectCode('INVALID_ACTIVATION_POINTER'));
  fs.writeFileSync(path.join(root, STATE), 'not a directory');
  writePointer(root, STATE);
  assert.throws(() => readActivation(root), expectCode('INVALID_ACTIVATION_POINTER'));
  await assert.rejects(activate({ sessionRoot: root }), expectCode('INVALID_ACTIVATION_POINTER'));
});

test('one pointer binds only one Ledger and is never overwritten', async t => {
  const { root } = fixture(t);
  fakeState(root, 'a');
  fakeState(root, 'b');
  forbidInit(t);
  await activate({ sessionRoot: root, directory: 'a', existingOnly: true });
  const before = fs.readFileSync(path.join(root, POINTER));
  await assert.rejects(activate({ sessionRoot: root, directory: 'b', existingOnly: true }), expectCode('ALREADY_ACTIVATED'));
  assert.deepEqual(fs.readFileSync(path.join(root, POINTER)), before);
});

test('explicit init uses the exact bounded execFile CLI and only then writes pointer', async t => {
  const { root } = fixture(t);
  const controller = new AbortController();
  const calls = mockInit(t, ({ args, callback }) => {
    assert.equal(fs.existsSync(path.join(root, POINTER)), false);
    fakeState(args[4]);
    callback(null, 'ignored bounded output', '');
  });
  const result = await activate({ sessionRoot: root, directory: 'new/nested', python, signal: controller.signal });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].file, python);
  assert.deepEqual(calls[0].args, ['-B', '-m', 'math_research.cli', '--workspace', path.join(root, 'new', 'nested'), 'init']);
  assert.deepEqual(calls[0].options, {
    cwd: result.ledgerRoot, timeout: 60000, maxBuffer: 65536, shell: false, signal: controller.signal,
  });
  assert.deepEqual(readActivation(root), result);
});

test('init failure writes no pointer and never removes user-created state', async t => {
  const { root } = fixture(t);
  mockInit(t, ({ args, callback }) => {
    const state = fakeState(args[4]);
    fs.writeFileSync(path.join(state, 'partial-user-data'), 'keep');
    callback(new Error('synthetic CLI failure'));
  });
  await assert.rejects(activate({ sessionRoot: root, python }), expectCode('ACTIVATION_INIT_FAILED'));
  assert.equal(fs.existsSync(path.join(root, POINTER)), false);
  assert.equal(fs.readFileSync(path.join(root, STATE, 'partial-user-data'), 'utf8'), 'keep');
});

test('Python validation precedes parent creation and an aborted activation makes no files', async t => {
  const { root } = fixture(t);
  forbidInit(t);
  await assert.rejects(activate({ sessionRoot: root, directory: 'missing', python: 'python' }), expectCode('ACTIVATION_INIT_FAILED'));
  const controller = new AbortController();
  controller.abort();
  await assert.rejects(activate({ sessionRoot: root, directory: 'missing', python, signal: controller.signal }), { name: 'AbortError' });
  assert.deepEqual(fs.readdirSync(root), []);
});

test('same-root concurrent activation serializes init and never duplicates the CLI', async t => {
  const { root } = fixture(t);
  let release;
  const calls = mockInit(t, ({ args, callback }) => {
    release = () => { fakeState(args[4]); callback(null); };
  });
  const first = activate({ sessionRoot: root, directory: 'new', python });
  const second = activate({ sessionRoot: root, directory: 'new', python });
  await Promise.resolve();
  assert.equal(calls.length, 1);
  release();
  const results = await Promise.all([first, second]);
  assert.deepEqual(results[0], results[1]);
  assert.equal(calls.length, 1);
});

test('a failed queued init does not poison later activation', async t => {
  const { root } = fixture(t);
  const calls = mockInit(t, ({ args, callback, count }) => {
    if (count === 1) callback(new Error('first attempt failed'));
    else { fakeState(args[4]); callback(null); }
  });
  const first = activate({ sessionRoot: root, python });
  const second = activate({ sessionRoot: root, python });
  await assert.rejects(first, expectCode('ACTIVATION_INIT_FAILED'));
  assert.equal((await second).root, root);
  assert.equal(calls.length, 2);
});

test('exclusive pointer creation honors a same-binding concurrent writer', async t => {
  const { root } = fixture(t);
  fakeState(root);
  forbidInit(t);
  const originalOpen = fs.openSync;
  let raced = false;
  fs.openSync = function (filename, flags, ...args) {
    if (!raced && filename === path.join(root, POINTER) && flags === 'wx') {
      raced = true;
      writePointer(root, `${STATE}\n`);
    }
    return originalOpen.call(fs, filename, flags, ...args);
  };
  try {
    assert.equal((await activate({ sessionRoot: root, existingOnly: true })).relative, STATE);
    assert.equal(raced, true);
  } finally { fs.openSync = originalOpen; }
});

test('exclusive pointer creation refuses a different-binding concurrent writer', async t => {
  const { root } = fixture(t);
  fakeState(root, 'a');
  fakeState(root, 'b');
  forbidInit(t);
  const originalOpen = fs.openSync;
  let raced = false;
  fs.openSync = function (filename, flags, ...args) {
    if (!raced && filename === path.join(root, POINTER) && flags === 'wx') {
      raced = true;
      writePointer(root, `b/${STATE}\n`);
    }
    return originalOpen.call(fs, filename, flags, ...args);
  };
  try {
    await assert.rejects(activate({ sessionRoot: root, directory: 'a', existingOnly: true }), expectCode('ALREADY_ACTIVATED'));
    assert.equal(fs.readFileSync(path.join(root, POINTER), 'utf8'), `b/${STATE}\n`);
  } finally { fs.openSync = originalOpen; }
});

for (const type of process.platform === 'win32' ? ['junction', 'dir'] : ['dir']) {
  test(`target ${type} link escaping root is rejected before any outside files are made`, async t => {
    const { base, root } = fixture(t);
    const outside = path.join(base, 'outside');
    fs.mkdirSync(outside);
    if (!makeLink(t, outside, path.join(root, 'escape'), type)) return;
    forbidInit(t);
    await assert.rejects(activate({ sessionRoot: root, directory: 'escape/new', python }), expectCode('INVALID_ACTIVATION_PATH'));
    writePointer(root, `escape/${STATE}\n`);
    assert.throws(() => readActivation(root), expectCode('INVALID_ACTIVATION_POINTER'));
    assert.deepEqual(fs.readdirSync(outside), []);
  });

  test(`state ${type} link is forbidden even if its target is inside root`, async t => {
    const { root } = fixture(t);
    const actual = path.join(root, 'actual-state');
    fs.mkdirSync(actual);
    if (!makeLink(t, actual, path.join(root, STATE), type)) return;
    forbidInit(t);
    writePointer(root, `${STATE}\n`);
    assert.throws(() => readActivation(root), expectCode('INVALID_ACTIVATION_POINTER'));
    await assert.rejects(activate({ sessionRoot: root, existingOnly: true }), expectCode('INVALID_ACTIVATION_POINTER'));
  });
}

test('pointer file symlinks are rejected instead of followed', t => {
  const { root } = fixture(t);
  fakeState(root);
  const target = path.join(root, 'pointer-target');
  fs.writeFileSync(target, STATE);
  if (!makeLink(t, target, path.join(root, POINTER), 'file')) return;
  forbidInit(t);
  assert.throws(() => readActivation(root), expectCode('INVALID_ACTIVATION_POINTER'));
  assert.equal(fs.readFileSync(target, 'utf8'), STATE);
});

test('sessionRoot aliases canonicalize while target component aliases are rejected', async t => {
  const { base, root } = fixture(t);
  fakeState(root);
  const alias = path.join(base, 'root-alias');
  if (!makeLink(t, root, alias, process.platform === 'win32' ? 'junction' : 'dir')) return;
  forbidInit(t);
  assert.equal((await activate({ sessionRoot: alias, existingOnly: true })).root, root);
  assert.equal(readActivation(alias).root, root);
});

test('pointer directories and Windows pointer junctions are rejected', t => {
  const { root } = fixture(t);
  const target = path.join(root, 'pointer-target');
  fs.mkdirSync(target);
  const pointer = path.join(root, POINTER);
  if (process.platform === 'win32') {
    if (!makeLink(t, target, pointer, 'junction')) return;
  } else fs.mkdirSync(pointer);
  assert.throws(() => readActivation(root), expectCode('INVALID_ACTIVATION_POINTER'));
});

test('pointer FD reads remain bounded even if the file grows after lstat', t => {
  const { root } = fixture(t);
  fakeState(root);
  writePointer(root, STATE);
  const originalRead = fs.readSync;
  const originalFstat = fs.fstatSync;
  let bytesRead = 0;
  fs.fstatSync = function (fd, ...args) {
    const result = originalFstat.call(fs, fd, ...args);
    fs.writeFileSync(path.join(root, POINTER), Buffer.alloc(10000, 97));
    return result;
  };
  fs.readSync = function (fd, buffer, offset, length, position) {
    assert.ok(length <= 4097);
    const count = originalRead.call(fs, fd, buffer, offset, length, position);
    bytesRead += count;
    return count;
  };
  try {
    assert.throws(() => readActivation(root), expectCode('INVALID_ACTIVATION_POINTER'));
    assert.equal(bytesRead, 4097);
  } finally {
    fs.readSync = originalRead;
    fs.fstatSync = originalFstat;
  }
});

test('a synchronous spawn error or CLI success without state never creates a pointer', async t => {
  const { root } = fixture(t);
  const calls = mockInit(t, ({ callback, count }) => {
    if (count === 1) throw new Error('synthetic synchronous execFile error');
    callback(null);
  });
  await assert.rejects(activate({ sessionRoot: root, python }), expectCode('ACTIVATION_INIT_FAILED'));
  await assert.rejects(activate({ sessionRoot: root, python }), expectCode('ACTIVATION_INIT_FAILED'));
  assert.equal(calls.length, 2);
  assert.equal(fs.existsSync(path.join(root, POINTER)), false);
});

test('state created during parent checks is bound without initialization', async t => {
  const { root } = fixture(t);
  forbidInit(t);
  const originalMkdir = fs.mkdirSync;
  let injected = false;
  fs.mkdirSync = function (directory, ...args) {
    const result = originalMkdir.call(fs, directory, ...args);
    if (!injected && directory === path.join(root, 'new')) {
      injected = true;
      originalMkdir.call(fs, path.join(directory, STATE));
    }
    return result;
  };
  try {
    const result = await activate({ sessionRoot: root, directory: 'new', python });
    assert.equal(result.relative, `new/${STATE}`);
    assert.equal(injected, true);
  } finally { fs.mkdirSync = originalMkdir; }
});

test('non-absolute and nonexistent session roots are rejected', t => {
  const { base } = fixture(t);
  assert.throws(() => readActivation('.'), expectCode('INVALID_ACTIVATION_PATH'));
  assert.throws(() => readActivation(path.join(base, 'absent')), expectCode('INVALID_ACTIVATION_PATH'));
});
