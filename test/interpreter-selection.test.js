'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const sra = require('../index.js');

test('per-call SRA_PYTHON override is honored by interpreter discovery', async () => {
  await assert.rejects(
    sra.run(['--help'], {
      stdio: 'pipe',
      env: { SRA_PYTHON: '/path-that-must-not-exist/sra-python' },
    }),
    /Python 3\.11 or newer was not found/,
  );
});

test('a per-call Python selection does not mutate process.env', async () => {
  const before = process.env.SRA_PYTHON;
  await assert.rejects(
    sra.run(['--help'], {
      stdio: 'pipe',
      env: { SRA_PYTHON: '/path-that-must-not-exist/sra-python' },
    }),
  );
  assert.equal(process.env.SRA_PYTHON, before);
});
test('per-call PATH is also used during Python probing', async () => {
  await assert.rejects(
    sra.run(['--help'], {
      stdio: 'pipe',
      env: {
        SRA_PYTHON: 'python3',
        PATH: '/path-that-must-not-exist/sra-empty-path',
      },
    }),
    /Python 3\.11 or newer was not found/,
  );
});
