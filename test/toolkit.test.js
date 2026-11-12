'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { mkdtempSync, writeFileSync, readFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { createHash } = require('node:crypto');
const sra = require('../index.js');

test('toolkit Node adapter executes real exact-math backend and validates paths', async () => {
  assert.equal(typeof sra.verifyToolkit, 'function');
  await assert.rejects(sra.verifyToolkit(''), TypeError);
  await assert.rejects(sra.verifyToolkit('spec.json', { manuscript: 1 }), TypeError);
  const dir = mkdtempSync(join(tmpdir(), 'sra-toolkit-'));
  try {
    const spec = join(dir, 'spec.json');
    writeFileSync(spec, JSON.stringify({ schema_version: '1.0', checks: [
      { id: 'math', kind: 'polynomial_identity', variables: ['x'], left: '(x+1)**2', right: 'x**2+2*x+1' }
    ] }));
    const result = await sra.verifyToolkit(spec, { stdio: 'pipe', out: join(dir, 'report') });
    assert.equal(result.code, 0, result.stderr);
    assert.equal(JSON.parse(readFileSync(join(dir, 'report.json'), 'utf8')).checks[0].status, 'VERIFIED');
    const content = '# Proof\nA polynomial identity is proposed.\n';
    const paper = join(dir, 'paper.md');
    writeFileSync(paper, content);
    const bound = JSON.parse(readFileSync(spec, 'utf8'));
    bound.source_sha256 = bound.extracted_text_sha256 = createHash('sha256').update(content).digest('hex');
    writeFileSync(spec, JSON.stringify(bound));
    const standalone = await sra.verifyToolkit(spec, { manuscript: paper, stdio: 'pipe', out: join(dir, 'bound') });
    assert.equal(standalone.code, 0, standalone.stderr);
    const unified = await sra.reviewManuscript(paper, { toolkitSpec: spec, prepareInputs: true, stdio: 'pipe', out: join(dir, 'unified') });
    assert.equal(unified.code, 0, unified.stderr);
    assert.equal(JSON.parse(readFileSync(join(dir, 'unified.json'), 'utf8')).modules.toolkit.status, 'completed');
    assert.equal(JSON.parse(readFileSync(join(dir, 'unified.json'), 'utf8')).modules.preparation.status, 'completed');
    await assert.rejects(sra.prepareInspection(''), TypeError);
    await assert.rejects(sra.reviewManuscript(paper, { prepareInputs: 1 }), TypeError);
    const preparation = await sra.prepareInspection(paper, { stdio: 'pipe', out: join(dir, 'prepared') });
    assert.equal(preparation.code, 0, preparation.stderr);
    assert.equal(JSON.parse(readFileSync(join(dir, 'prepared.json'), 'utf8')).checks_executed, false);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
