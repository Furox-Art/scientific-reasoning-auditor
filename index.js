'use strict';

const { spawn, spawnSync } = require('node:child_process');

const PYTHON_PROBE = [
  '-I',
  '-c',
  "import importlib.util,sys; sys.exit(0 if sys.version_info >= (3,11) and importlib.util.find_spec('sra') else 1)",
];

function pythonCandidates(env = process.env) {
  if (env.SRA_PYTHON) {
    return [{ command: env.SRA_PYTHON, prefix: [] }];
  }

  const candidates = [
    { command: 'python3', prefix: [] },
    { command: 'python', prefix: [] },
  ];
  if (process.platform === 'win32') {
    candidates.push({ command: 'py', prefix: ['-3'] });
  }
  return candidates;
}

function resolvePython(env = process.env, cwd = process.cwd()) {
  let pythonFound = false;

  for (const candidate of pythonCandidates(env)) {
    const probe = spawnSync(candidate.command, [...candidate.prefix, ...PYTHON_PROBE], {
      encoding: 'utf8',
      windowsHide: true,
      env,
      cwd,
      timeout: 2000,
      maxBuffer: 64 * 1024,
    });

    if (probe.error) continue;
    pythonFound = true;
    if (probe.status === 0) return candidate;
  }

  if (!pythonFound) {
    throw new Error(
      'Python 3.11 or newer was not found. Install Python 3.11+ and ensure it is on PATH, or set SRA_PYTHON to its executable.'
    );
  }

  const installCommand = process.platform === 'win32'
    ? 'py -3 -m pip install "scientific-reasoning-auditor[statistics]"'
    : 'python3 -m pip install "scientific-reasoning-auditor[statistics]"';
  throw new Error(
    `The Python package "scientific-reasoning-auditor" is not installed for the detected interpreter. Install the Python engine separately with: ${installCommand}. The npm package does not install or download Python packages automatically. If it is installed in another environment, set SRA_PYTHON to that interpreter.`
  );
}

/** Run the installed Python engine with the supplied sra CLI arguments. */
function run(args, options = {}) {
  if (!Array.isArray(args) || args.some((arg) => typeof arg !== 'string')) {
    return Promise.reject(new TypeError('args must be an array of strings'));
  }

  const childEnv = { ...process.env, ...(options.env || {}) };
  // Python -P does not ignore PYTHONPATH; block import shadowing from caller CWD.
  delete childEnv.PYTHONPATH;
  const childCwd = options.cwd || process.cwd();
  let python;
  try {
    python = resolvePython(childEnv, childCwd);
  } catch (error) {
    return Promise.reject(error);
  }

  const stdio = options.stdio || 'inherit';
  return new Promise((resolve, reject) => {
    const child = spawn(
      python.command,
      [...python.prefix, '-I', '-m', 'sra.cli', ...args],
      {
        cwd: childCwd,
        env: childEnv,
        stdio,
        windowsHide: true,
      }
    );

    let stdout = '';
    let stderr = '';
    let outputBytes = 0;
    let outputExceeded = false;
    const MAX_CAPTURED_OUTPUT_BYTES = 8 * 1024 * 1024;
    const collect = (stream, chunk) => {
      if (outputExceeded) return;
      outputBytes += Buffer.byteLength(chunk, 'utf8');
      if (outputBytes > MAX_CAPTURED_OUTPUT_BYTES) {
        outputExceeded = true;
        child.kill();
        reject(new Error('Python CLI captured output exceeded the 8 MiB limit.'));
        return;
      }
      if (stream === 'stdout') stdout += chunk;
      else stderr += chunk;
    };
    if (child.stdout) child.stdout.setEncoding('utf8').on('data', chunk => collect('stdout', chunk));
    if (child.stderr) child.stderr.setEncoding('utf8').on('data', chunk => collect('stderr', chunk));

    child.once('error', reject);
    child.once('close', (code, signal) => {
      if (!outputExceeded) resolve({ code: code === null ? 1 : code, signal, stdout, stderr });
    });
  });
}

function withOutput(args, out) {
  return out ? [...args, '--out', out] : args;
}

function audit(input, options = {}) {
  if (typeof input !== 'string' || input.length === 0) {
    return Promise.reject(new TypeError('input must be a non-empty file path'));
  }
  let args = ['audit', input];
  if (options.semanticReview) args.push('--semantic-review', options.semanticReview);
  args = withOutput(args, options.out || 'audit-report');
  return run(args, options);
}

function createReviewTemplate(input, options = {}) {
  if (typeof input !== 'string' || input.length === 0) {
    return Promise.reject(new TypeError('input must be a non-empty file path'));
  }
  const mode = options.mode || 'single';
  if (!['single', 'parallel'].includes(mode)) {
    return Promise.reject(new TypeError('mode must be "single" or "parallel"'));
  }
  const args = ['review-template', input, '--mode', mode, '--out', options.out || 'semantic-review-template.json'];
  return run(args, options);
}

function reviewModel(input, options = {}) {
  if (typeof input !== 'string' || input.length === 0) {
    return Promise.reject(new TypeError('input must be a non-empty file path'));
  }
  if (typeof options.model !== 'string' || options.model.length === 0) {
    return Promise.reject(new TypeError('options.model is required'));
  }
  const args = ['review-model', input, '--model', options.model];
  if (options.baseUrl) args.push('--base-url', options.baseUrl);
  if (options.apiKeyEnv) args.push('--api-key-env', options.apiKeyEnv);
  if (options.timeout !== undefined) args.push('--timeout', String(options.timeout));
  args.push('--out', options.out || 'semantic-review-completed.json');
  return run(args, options);
}

function verifyStats(input, options = {}) {
  if (typeof input !== 'string' || input.length === 0) {
    return Promise.reject(new TypeError('input must be a non-empty file path'));
  }
  const args = ['verify-stats', input, '--out', options.out || 'stats-verification.json'];
  return run(args, options);
}

module.exports = {
  run,
  audit,
  createReviewTemplate,
  reviewModel,
  verifyStats,
};
