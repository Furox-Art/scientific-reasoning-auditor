'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const { mkdtempSync, readFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const sra = require('../index.js');

test('error benchmark transport retains abstentions and honest denominators', async () => {
  await assert.rejects(sra.benchmarkErrors(''), TypeError);
  await assert.rejects(sra.errorLabelTemplate(null), TypeError);
  await assert.rejects(sra.evaluateErrors('manifest', '', 'labels'), TypeError);
  const dir = mkdtempSync(join(tmpdir(), 'sra-error-benchmark-'));
  const manifest = join(__dirname, '../examples/error_benchmark/synthetic.json');
  const labels = join(__dirname, '../examples/error_benchmark/synthetic-labels.json');
  try {
    const run = await sra.benchmarkErrors(manifest, { stdio: 'pipe', out: join(dir, 'run') });
    assert.equal(run.code, 0, run.stderr);
    const template = await sra.errorLabelTemplate(manifest, { stdio: 'pipe', out: join(dir, 'template.json') });
    assert.equal(template.code, 0, template.stderr);
    assert.equal(JSON.parse(readFileSync(join(dir, 'template.json'))).cases[0].reviewers[0].label, null);
    const evaluated = await sra.evaluateErrors(manifest, join(dir, 'run.json'), labels,
      { stdio: 'pipe', out: join(dir, 'evaluated') });
    assert.equal(evaluated.code, 0, evaluated.stderr);
    const report = JSON.parse(readFileSync(join(dir, 'evaluated.json')));
    assert.equal(report.summary.metrics.end_to_end_recall.value, 1 / 3);
    assert.deepEqual(report.summary.abstentions, { error: 1, no_error: 1 });
    const exact = await sra.benchmarkErrors(join(__dirname, '../examples/error_benchmark/numeric-boundary.json'),
      { stdio: 'pipe', out: join(dir, 'numeric') });
    assert.equal(exact.code, 0, exact.stderr);
    assert.equal(JSON.parse(readFileSync(join(dir, 'numeric.json'))).cases[0].prediction, 'error');
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
