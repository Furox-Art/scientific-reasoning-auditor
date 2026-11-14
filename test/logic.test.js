'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const sra = require('../index.js');

test('formal logic wrapper rejects invalid paths', async () => {
  await assert.rejects(sra.verifyLogic(''), TypeError);
  await assert.rejects(sra.verifyLogic('spec.json', { manuscript: 2 }), TypeError);
});

test('formal logic Node wrapper invokes real Z3 and writes separate results', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-logic-'));
  try {
    const result = await sra.verifyLogic(path.join(__dirname, '../examples/logic_boolean.json'),
      { stdio: 'pipe', out: path.join(dir, 'report') });
    assert.equal(result.code, 0, result.stderr);
    const report = JSON.parse(fs.readFileSync(path.join(dir, 'report.json'), 'utf8'));
    assert.deepEqual(report.claims.map(x => x.status), ['VERIFIED','REFUTED','UNDETERMINED']);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
