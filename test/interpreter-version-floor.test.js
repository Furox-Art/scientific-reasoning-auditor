'use strict';

// The npm package and the Python package are versioned independently, so an
// `npm install` can sit next to an old `sra` from PyPI. The probe used to check
// only "is `sra` importable", so an outdated engine answered successfully and
// the failure surfaced later as a CLI command that does not exist.
//
// These tests drive `resolvePython` through a fake interpreter, which has to be
// a POSIX executable, so they are skipped on Windows.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const sra = require('../index.js');

function fakeInterpreter(t, version, status) {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-version-floor-'));
  t.after(() => fs.rmSync(folder, { recursive: true, force: true }));
  const launcher = path.join(folder, 'sra-fake-python');
  fs.writeFileSync(
    launcher,
    '#!/usr/bin/env node\n' +
      'if (process.argv.includes("-c")) {' +
      ` process.stdout.write("${version}\\n"); process.exit(${status}); }\n` +
      'process.exit(0);\n',
  );
  fs.chmodSync(launcher, 0o755);
  return launcher;
}

test('an outdated Python engine is refused with an upgrade instruction', async (t) => {
  if (process.platform === 'win32') return;
  const launcher = fakeInterpreter(t, '0.1.1', 2);
  await assert.rejects(
    sra.run(['--help'], { stdio: 'pipe', env: { SRA_PYTHON: launcher } }),
    (error) => {
      assert.match(error.message, /is 0\.1\.1/);
      assert.match(error.message, /requires at least 0\.5\.2/);
      assert.match(error.message, /pip install --upgrade scientific-reasoning-auditor/);
      return true;
    },
  );
});

test('a Python engine at the floor is accepted', async (t) => {
  if (process.platform === 'win32') return;
  const launcher = fakeInterpreter(t, '0.5.2', 0);
  const out = await sra.run(['--help'], { stdio: 'pipe', env: { SRA_PYTHON: launcher } });
  assert.equal(out.code, 0);
});
