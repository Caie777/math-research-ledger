'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const childProcess = require('node:child_process');

const PYTHON_FLAGS = ['-I', '-B'];
const executableName = process.platform === 'win32' ? 'python.exe' : 'python3';
const probe = [
  'import sys',
  "if sys.version_info < (3, 11): sys.exit('Python 3.11 or newer is required')",
  'import math_research.cli.main, math_research.mcp.server, mcp.server',
  "print('MRL_RUNTIME_READY')",
].join('\n');

function runtimeError(reason, cause) {
  const error = new Error(`MRL_RUNTIME_UNAVAILABLE: ${reason} `
    + 'Install the matching math-research-ledger wheel with [mcp] in a working Python environment '
    + 'and set the Host plugin’s python setting to its absolute executable path, '
    + 'or clear the setting to use the DSH Host PATH. Recreate a moved venv instead of copying it.', { cause });
  error.code = 'MRL_RUNTIME_UNAVAILABLE';
  return error;
}

function absolute(filename) {
  return path.isAbsolute(filename) && !/[\0\r\n]/u.test(filename)
    && (process.platform !== 'win32' || !/^[\\/](?![\\/])/u.test(filename));
}

async function fromPath(signal) {
  for (const entry of (process.env.PATH || '').split(path.delimiter)) {
    signal?.throwIfAborted();
    const directory = entry.replace(/^"(.*)"$/u, '$1');
    // Never resolve relative entries or use the Agent's cwd as an executable search path.
    if (!absolute(directory)) continue;
    const filename = path.join(directory, executableName);
    try {
      if (!(await fs.stat(filename)).isFile()) continue;
      await fs.access(filename, fs.constants.X_OK);
      return filename; // Do not realpath a venv executable to its base interpreter.
    } catch (error) {
      if (!['ENOENT', 'ENOTDIR', 'EACCES', 'EPERM'].includes(error.code)) throw error;
    }
  }
  throw runtimeError(`No ${executableName} found in the DSH Host PATH.`);
}

async function resolvePython(configured, signal) {
  signal?.throwIfAborted();
  if (configured && !absolute(configured)) {
    throw runtimeError('The configured python setting must be an absolute executable path.');
  }
  // An explicit local choice is authoritative; a stale setting never silently
  // falls through to a different environment. Do not cache success or failure.
  const filename = configured || await fromPath(signal);
  try {
    await new Promise((resolve, reject) => {
      childProcess.execFile(filename, [...PYTHON_FLAGS, '-c', probe], {
        cwd: __dirname, timeout: 15000, maxBuffer: 16 * 1024, shell: false, windowsHide: true, signal,
      }, (error, stdout) => {
        if (error) reject(error);
        else if (stdout.trim() !== 'MRL_RUNTIME_READY') reject(new Error('Unexpected probe output'));
        else resolve();
      });
    });
  } catch (error) {
    signal?.throwIfAborted();
    const source = configured ? 'Configured Python' : 'Python on the DSH Host PATH';
    throw runtimeError(`${source} (${filename}) could not start or import the Ledger CLI and MCP dependencies.`, error);
  }
  return filename;
}

exports.PYTHON_FLAGS = PYTHON_FLAGS;
exports.resolvePython = resolvePython;
