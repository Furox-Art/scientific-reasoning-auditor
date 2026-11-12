'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { mkdtempSync, writeFileSync, readFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const sra = require('../index.js');

test('unified API exposes capability discovery and typed input validation', async () => {
  assert.equal(typeof sra.reviewManuscript, 'function');
  assert.equal(typeof sra.capabilities, 'function');
  for (const options of [{ studyType: 'fiction' }, { disciplines: 'physics' },
    { disciplines: ['unsupported'] }, { online: 1 }, { sendToModel: 1 },
    { model: 'fake' }, { sendToModel: true }, { styleLanguage: 'auto' },
    { timeout: 0 }, { chunkChars: 1 }, { visualPages: true }]) {
    await assert.rejects(sra.reviewManuscript('paper.md', options), TypeError);
  }
  await assert.rejects(sra.reviewManuscript(''), TypeError);
});

test('unified Node wrapper executes real Python engine and preserves module identity', async () => {
  assert.equal(typeof sra.reviewManuscript, 'function');
  const dir = mkdtempSync(join(tmpdir(), 'sra-unified-'));
  try {
    const paper = join(dir, 'paper.md');
    writeFileSync(paper, '# Proof\nAssume an exact identity.\n');
    const options = { stdio: 'pipe', out: join(dir, 'report'), studyType: 'theoretical',
      disciplines: ['physics', 'computing'], styleLanguage: 'none', timeout: 30,
      chunkChars: 2000, ocrMode: 'off', ocrLanguages: 'eng' };
    const result = await sra.reviewManuscript(paper, options);
    assert.equal(result.code, 0, result.stderr);
    const report = JSON.parse(readFileSync(join(dir, 'report.json'), 'utf8'));
    assert.deepEqual(report.configuration.disciplines, ['physics', 'computing']);
    assert.equal(report.modules.model.status, 'not_requested');
    const catalog = await sra.capabilities({ stdio: 'pipe' });
    assert.equal(catalog.code, 0, catalog.stderr);
    assert.equal(JSON.parse(catalog.stdout).schema_version, 'cross-disciplinary-review/1.0');
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
