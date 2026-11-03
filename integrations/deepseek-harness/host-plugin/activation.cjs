'use strict';

// Host path metadata only. Core initialization is an explicit, separate CLI call.
// Before/after path checks and bounded FD reads reduce ordinary races; Node has
// no portable openat2, so this is not protection from arbitrary hostile local
// filesystem mutation (including mutation while the external CLI is running).
const fs = require('node:fs');
const path = require('node:path');
const childProcess = require('node:child_process');
const { TextDecoder } = require('node:util');

const POINTER = '.math-research-ledger-link';
const STATE = '.math-research-ledger';
const POINTER_LIMIT = 4096;
const queues = new Map();

function failure(code, message, cause) {
  const error = new Error(`${code}: ${message}`, cause ? { cause } : undefined);
  error.code = code;
  return error;
}

function invalid(code, message, cause) {
  throw failure(code, message, cause);
}

function inside(root, candidate, strict = false) {
  const relative = path.relative(root, candidate);
  return (!strict || relative !== '') && !path.isAbsolute(relative)
    && relative !== '..' && !relative.startsWith(`..${path.sep}`);
}

function canonicalRoot(sessionRoot) {
  if (typeof sessionRoot !== 'string' || !path.isAbsolute(sessionRoot)
      || sessionRoot.includes('\0')) {
    invalid('INVALID_ACTIVATION_PATH', 'sessionRoot must be an absolute directory.');
  }
  try {
    const root = fs.realpathSync(sessionRoot);
    const metadata = fs.lstatSync(root);
    if (metadata.isSymbolicLink() || !metadata.isDirectory()) throw new Error('Not a real directory.');
    return root;
  } catch (error) {
    invalid('INVALID_ACTIVATION_PATH', 'sessionRoot must exist as a real directory.', error);
  }
}

function pathParts(value, code, pointer = false) {
  if (typeof value !== 'string' || !value || /[\0\r\n]/u.test(value)) {
    invalid(code, 'Expected one nonempty path without NUL or newlines.');
  }
  if (value.split(/[\\/]/u).includes('..')) {
    invalid(code, 'Parent (..) path components are not allowed.');
  }
  // Do not reinterpret Windows drives, UNC or device paths as Unix-relative names.
  if ((process.platform !== 'win32' && (path.win32.isAbsolute(value) || /^[a-z]:/iu.test(value)))
      || (process.platform === 'win32' && /^[a-z]:[^\\/]/iu.test(value))) {
    invalid(code, 'Foreign or drive-relative Windows paths are not allowed.');
  }
  if (!pointer && process.platform !== 'win32' && value.includes('\\')) {
    invalid(code, 'Backslash path separators are not portable on this platform.');
  }
  if (pointer && (path.isAbsolute(value) || path.win32.isAbsolute(value)
      || value.includes('\\') || /^[a-z]:/iu.test(value))) {
    invalid(code, 'The pointer must contain a portable relative path.');
  }
  return value;
}

// Check every existing component. Target links (including Windows junctions) are
// deliberately rejected, even if their destination is inside the trusted root.
function checkPath(root, candidate, { code, allowMissing = false } = {}) {
  if (!inside(root, candidate)) invalid(code, 'The target must remain inside sessionRoot.');
  const relative = path.relative(root, candidate);
  const components = relative ? relative.split(path.sep) : [];
  let current = root;
  for (const component of ['', ...components]) {
    if (component) current = path.join(current, component);
    let metadata;
    try {
      metadata = fs.lstatSync(current);
    } catch (error) {
      if (allowMissing && error.code === 'ENOENT') return false;
      invalid(code, 'An activation directory is missing or inaccessible.', error);
    }
    if (metadata.isSymbolicLink() || !metadata.isDirectory()) {
      invalid(code, 'Activation paths must be real directories, not links or files.');
    }
    let canonical;
    try {
      canonical = fs.realpathSync(current);
    } catch (error) {
      invalid(code, 'Cannot resolve an activation directory.', error);
    }
    if (!inside(root, canonical) || path.relative(current, canonical) !== '') {
      invalid(code, 'An activation path changed or escaped the canonical sessionRoot.');
    }
  }
  return true;
}

function binding(root, state) {
  if (!inside(root, state, true) || path.basename(state) !== STATE) {
    invalid('INVALID_ACTIVATION_PATH', 'The state directory must be a strict sessionRoot descendant.');
  }
  return { root, state, ledgerRoot: path.dirname(state), relative: path.relative(root, state).split(path.sep).join('/') };
}

function pointerText(root) {
  const filename = path.join(root, POINTER);
  let before;
  try {
    before = fs.lstatSync(filename);
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    invalid('INVALID_ACTIVATION_POINTER', 'Cannot inspect the activation pointer.', error);
  }
  if (before.isSymbolicLink() || !before.isFile() || before.size > POINTER_LIMIT) {
    invalid('INVALID_ACTIVATION_POINTER', 'The pointer must be a regular file of at most 4096 bytes, never a link.');
  }
  let fd;
  try {
    const nofollow = fs.constants.O_NOFOLLOW || 0;
    fd = fs.openSync(filename, fs.constants.O_RDONLY | nofollow);
    const opened = fs.fstatSync(fd);
    if (!opened.isFile() || opened.size > POINTER_LIMIT
        || opened.dev !== before.dev || opened.ino !== before.ino) {
      throw new Error('Pointer changed while opening.');
    }
    // Read at most limit+1 even if the file grows after fstat.
    const bytes = Buffer.alloc(POINTER_LIMIT + 1);
    let length = 0;
    while (length < bytes.length) {
      const count = fs.readSync(fd, bytes, length, bytes.length - length, null);
      if (count === 0) break;
      length += count;
    }
    const after = fs.lstatSync(filename);
    if (length > POINTER_LIMIT || after.isSymbolicLink() || !after.isFile()
        || after.dev !== opened.dev || after.ino !== opened.ino
        || fs.fstatSync(fd).size !== length) {
      throw new Error('Pointer changed or exceeded the size limit.');
    }
    let text = new TextDecoder('utf-8', { fatal: true }).decode(bytes.subarray(0, length));
    // One optional final line ending is allowed, never another logical line.
    text = text.replace(/\r?\n$/u, '');
    return pathParts(text, 'INVALID_ACTIVATION_POINTER', true);
  } catch (error) {
    if (error.code === 'INVALID_ACTIVATION_POINTER') throw error;
    invalid('INVALID_ACTIVATION_POINTER', 'Cannot safely read the UTF-8 activation pointer.', error);
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

function readAtRoot(root) {
  const text = pointerText(root);
  if (text === null) return null;
  if (text.split('/').at(-1) !== STATE) {
    invalid('INVALID_ACTIVATION_POINTER', `The pointer must end in ${STATE}.`);
  }
  const state = path.resolve(root, text);
  if (!inside(root, state, true)) {
    invalid('INVALID_ACTIVATION_POINTER', 'The pointer must name a strict sessionRoot descendant.');
  }
  checkPath(root, state, { code: 'INVALID_ACTIVATION_POINTER' });
  // checkPath has already required every component to equal its realpath.
  return binding(root, state);
}

function readActivation(sessionRoot) {
  return readAtRoot(canonicalRoot(sessionRoot));
}

function requestedBinding(root, directory) {
  pathParts(directory, 'INVALID_ACTIVATION_PATH');
  const ledgerRoot = path.resolve(root, directory);
  if (!inside(root, ledgerRoot)) {
    invalid('INVALID_ACTIVATION_PATH', 'The requested directory is outside sessionRoot.');
  }
  const state = path.join(ledgerRoot, STATE);
  const result = binding(root, state);
  checkPath(root, state, { code: 'INVALID_ACTIVATION_PATH', allowMissing: true });
  return result;
}

function sameBinding(actual, wanted) {
  if (!actual) invalid('INVALID_ACTIVATION_POINTER', 'The activation pointer disappeared during activation.');
  if (path.relative(actual.state, wanted.state) !== '') {
    invalid('ALREADY_ACTIVATED', 'This exact sessionRoot is already bound to another Ledger directory.');
  }
  return actual;
}

function mkdirChecked(root, directory) {
  checkPath(root, root, { code: 'INVALID_ACTIVATION_PATH' });
  let current = root;
  for (const component of path.relative(root, directory).split(path.sep).filter(Boolean)) {
    current = path.join(current, component);
    // Check the parent immediately before each mkdir; never mkdir recursively.
    checkPath(root, path.dirname(current), { code: 'INVALID_ACTIVATION_PATH' });
    try {
      fs.mkdirSync(current);
    } catch (error) {
      if (error.code !== 'EEXIST') {
        invalid('INVALID_ACTIVATION_PATH', 'Cannot create the activation directory.', error);
      }
    }
    checkPath(root, current, { code: 'INVALID_ACTIVATION_PATH' });
  }
}

function initialize(wanted, python, signal) {
  if (typeof python !== 'string' || !path.isAbsolute(python) || python.includes('\0')) {
    invalid('ACTIVATION_INIT_FAILED', 'Initialization requires an absolute persistent Python executable.');
  }
  return new Promise((resolve, reject) => {
    const failed = error => reject(failure('ACTIVATION_INIT_FAILED', 'The explicit Ledger initialization CLI failed; no activation pointer was written.', error));
    try {
      childProcess.execFile(python, ['-B', '-m', 'math_research.cli', '--workspace', wanted.ledgerRoot, 'init'], {
        cwd: wanted.ledgerRoot, timeout: 60000, maxBuffer: 64 * 1024, shell: false, signal,
      }, error => {
        if (error) failed(error);
        else resolve();
      });
    } catch (error) {
      failed(error);
    }
  });
}

function writePointer(wanted) {
  checkPath(wanted.root, wanted.state, { code: 'INVALID_ACTIVATION_PATH' });
  let fd;
  try {
    fd = fs.openSync(path.join(wanted.root, POINTER), 'wx', 0o600);
  } catch (error) {
    if (error.code === 'EEXIST') return sameBinding(readAtRoot(wanted.root), wanted);
    invalid('INVALID_ACTIVATION_POINTER', 'Cannot exclusively create the activation pointer.', error);
  }
  try {
    fs.writeFileSync(fd, `${wanted.relative}\n`, { encoding: 'utf8' });
    fs.fsyncSync(fd);
  } catch (error) {
    invalid('INVALID_ACTIVATION_POINTER', 'Cannot write the activation pointer.', error);
  } finally {
    fs.closeSync(fd);
  }
  return sameBinding(readAtRoot(wanted.root), wanted);
}

async function activateAtRoot(root, { directory, python, signal, existingOnly }) {
  signal?.throwIfAborted();
  // A corrupt existing pointer is never ignored, even for another target.
  const existing = readAtRoot(root);
  const wanted = requestedBinding(root, directory);
  if (existing) return sameBinding(existing, wanted);
  const present = checkPath(root, wanted.state, { code: 'INVALID_ACTIVATION_PATH', allowMissing: true });
  if (!present) {
    if (existingOnly) invalid('INVALID_ACTIVATION_PATH', 'existingOnly requires an existing real .math-research-ledger directory.');
    // Validate Python before creating even the requested parent directories.
    if (typeof python !== 'string' || !path.isAbsolute(python) || python.includes('\0')) {
      invalid('ACTIVATION_INIT_FAILED', 'Initialization requires an absolute persistent Python executable.');
    }
    mkdirChecked(root, wanted.ledgerRoot);
    checkPath(root, wanted.ledgerRoot, { code: 'INVALID_ACTIVATION_PATH' });
    signal?.throwIfAborted();
    // Recheck after parent creation: do not initialize a state that appeared
    // meanwhile (the in-process queue also prevents duplicate same-root init).
    const concurrentPointer = readAtRoot(root);
    if (concurrentPointer) return sameBinding(concurrentPointer, wanted);
    if (!checkPath(root, wanted.state, { code: 'INVALID_ACTIVATION_PATH', allowMissing: true })) {
      await initialize(wanted, python, signal);
      checkPath(root, wanted.state, { code: 'ACTIVATION_INIT_FAILED' });
    }
  }
  signal?.throwIfAborted();
  return writePointer(wanted);
}

async function activate({ sessionRoot, directory = '.', python, signal, existingOnly = false }) {
  const root = canonicalRoot(sessionRoot);
  const previous = queues.get(root) || Promise.resolve();
  const current = previous.then(() => activateAtRoot(root, { directory, python, signal, existingOnly }));
  // A settled, non-rejecting tail keeps failure from poisoning later requests.
  const tail = current.then(() => undefined, () => undefined);
  queues.set(root, tail);
  void tail.then(() => { if (queues.get(root) === tail) queues.delete(root); });
  return current;
}

exports.POINTER = POINTER;
exports.readActivation = readActivation;
exports.activate = activate;
