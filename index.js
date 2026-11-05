'use strict';

const { spawn, spawnSync } = require('node:child_process');

const PYTHON_PROBE = [
  '-c',
  "import importlib.util,sys; sys.exit(0 if sys.version_info >= (3,11) and importlib.util.find_spec('sra') else 1)",
];

function pythonCandidates() {
  if (process.env.SRA_PYTHON) {
    return [{ command: process.env.SRA_PYTHON, prefix: [] }];
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

function resolvePython() {
  let pythonFound = false;

  for (const candidate of pythonCandidates()) {
    const probe = spawnSync(candidate.command, [...candidate.prefix, ...PYTHON_PROBE], {
      encoding: 'utf8',
      windowsHide: true,
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

  let python;
  try {
    python = resolvePython();
  } catch (error) {
    return Promise.reject(error);
  }

  const stdio = options.stdio || 'inherit';
  return new Promise((resolve, reject) => {
    const child = spawn(
      python.command,
      [...python.prefix, '-m', 'sra.cli', ...args],
      {
        cwd: options.cwd || process.cwd(),
        env: { ...process.env, ...(options.env || {}) },
        stdio,
        windowsHide: true,
      }
    );

    let stdout = '';
    let stderr = '';
    if (child.stdout) child.stdout.setEncoding('utf8').on('data', (chunk) => { stdout += chunk; });
    if (child.stderr) child.stderr.setEncoding('utf8').on('data', (chunk) => { stderr += chunk; });

    child.once('error', reject);
    child.once('close', (code, signal) => {
      resolve({ code: code === null ? 1 : code, signal, stdout, stderr });
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

function writingAudit(input, options = {}) {
  if (typeof input !== 'string' || input.length === 0) {
    return Promise.reject(new TypeError('input must be a non-empty file path'));
  }
  const genre = options.genre || 'general';
  if (!['general', 'original-research'].includes(genre)) {
    return Promise.reject(new TypeError('genre must be "general" or "original-research"'));
  }
  const args = ['writing-audit', input, '--genre', genre];
  for (const [name, flag] of [
    ['abstractMinWords', '--abstract-min-words'],
    ['abstractMaxWords', '--abstract-max-words'],
  ]) {
    if (options[name] !== undefined) {
      if (!Number.isSafeInteger(options[name]) || options[name] < 0) {
        return Promise.reject(new TypeError(name + ' must be a non-negative integer'));
      }
      args.push(flag, String(options[name]));
    }
  }
  if (options.styleLanguage) {
    if (!['en','tr','none'].includes(options.styleLanguage)) {
      return Promise.reject(new TypeError('styleLanguage must be en, tr or none'));
    }
    args.push('--style-language', options.styleLanguage);
  }
  if (options.design) {
    if (!['clinical-trial','observational','systematic-review','computational'].includes(options.design)) {
      return Promise.reject(new TypeError('unsupported study design'));
    }
    args.push('--design', options.design);
  }
  if (options.discipline !== undefined) {
    if (!['clinical','animal','physics','chemistry','computing','social-science'].includes(options.discipline)) {
      return Promise.reject(new TypeError('unsupported discipline'));
    }
    args.push('--discipline', options.discipline);
  }
  if (options.grammarEngine !== undefined) {
    if (!['rules','local-languagetool'].includes(options.grammarEngine)) {
      return Promise.reject(new TypeError('unsupported grammarEngine'));
    }
    args.push('--grammar-engine', options.grammarEngine);
  }
  if (options.grammarPort !== undefined) {
    if (!Number.isSafeInteger(options.grammarPort) || options.grammarPort < 1024 || options.grammarPort > 65535) {
      return Promise.reject(new TypeError('grammarPort must be in 1024..65535'));
    }
    args.push('--grammar-port', String(options.grammarPort));
  }
  if (options.grammarTimeout !== undefined) {
    if (!Number.isFinite(options.grammarTimeout) || options.grammarTimeout < 0.5 || options.grammarTimeout > 30) {
      return Promise.reject(new TypeError('grammarTimeout must be in 0.5..30'));
    }
    args.push('--grammar-timeout', String(options.grammarTimeout));
  }
  args.push('--out', options.out || 'academic-writing-report');
  return run(args, options);
}

function evaluateLabels(benchmark, labels, options = {}) {
  if (typeof benchmark !== 'string' || !benchmark.length) {
    return Promise.reject(new TypeError('benchmark must be a non-empty file path'));
  }
  if (typeof labels !== 'string' || !labels.length) {
    return Promise.reject(new TypeError('labels must be a non-empty file path'));
  }
  return run(['evaluate-labels', benchmark, labels, '--out',
    options.out || 'expert-validation-report.json'], options);
}

function verifyDoi(input, options = {}) {
  if (typeof input !== 'string' || !input.length) {
    return Promise.reject(new TypeError('input must be a non-empty file path'));
  }
  if (options.limit !== undefined &&
      (!Number.isSafeInteger(options.limit) || options.limit < 1 || options.limit > 200)) {
    return Promise.reject(new TypeError('limit must be an integer from 1 to 200'));
  }
  const args = ['doi-check', input, '--out', options.out || 'doi-check.json'];
  if (options.online === true) args.push('--online');
  if (options.limit !== undefined) args.push('--limit', String(options.limit));
  return run(args, options);
}

function benchmarkPmc(manifest, options = {}) {
  if (typeof manifest !== 'string' || !manifest.length) {
    return Promise.reject(new TypeError('manifest must be a non-empty file path'));
  }
  if (options.online !== true) {
    return Promise.reject(new TypeError('benchmarkPmc requires online: true'));
  }
  if (options.limit !== undefined &&
      (!Number.isSafeInteger(options.limit) || options.limit < 1 || options.limit > 200)) {
    return Promise.reject(new TypeError('limit must be an integer from 1 to 200'));
  }
  const args = ['benchmark-pmc', manifest, '--online', '--out', options.out || 'pmc-benchmark.json'];
  if (options.limit !== undefined) args.push('--limit', String(options.limit));
  return run(args, options);
}

const DISCIPLINES = ['clinical','animal','physics','chemistry','computing','social-science'];

function domainReview(input, options = {}) {
  if (typeof input !== 'string' || !input.length) {
    return Promise.reject(new TypeError('input must be a non-empty file path'));
  }
  if (!DISCIPLINES.includes(options.discipline)) {
    return Promise.reject(new TypeError('a supported discipline is required'));
  }
  return run(['domain-review', input, '--discipline', options.discipline,
    '--out', options.out || 'domain-review.json'], options);
}

function domainTemplate(input, options = {}) {
  if (typeof input !== 'string' || !input.length) {
    return Promise.reject(new TypeError('input must be a non-empty file path'));
  }
  if (!DISCIPLINES.includes(options.discipline)) {
    return Promise.reject(new TypeError('a supported discipline is required'));
  }
  return run(['domain-template', input, '--discipline', options.discipline,
    '--out', options.out || 'domain-template.json'], options);
}

function domainValidate(input, assessments, options = {}) {
  if (typeof input !== 'string' || !input.length || typeof assessments !== 'string' || !assessments.length) {
    return Promise.reject(new TypeError('input and assessments must be non-empty file paths'));
  }
  if (!DISCIPLINES.includes(options.discipline)) {
    return Promise.reject(new TypeError('a supported discipline is required'));
  }
  return run(['domain-validate', input, assessments, '--discipline', options.discipline,
    '--out', options.out || 'domain-adjudication.json'], options);
}

module.exports = {
  run,
  audit,
  createReviewTemplate,
  reviewModel,
  verifyStats,
  writingAudit,
  verifyDoi,
  benchmarkPmc,
  evaluateLabels,
  domainReview,
  domainTemplate,
  domainValidate,
};
