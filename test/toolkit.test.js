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
    writeFileSync(spec, JSON.stringify({ schema_version: '1.0', checks: [
      { id: 'power', kind: 'power_analysis', design: 'paired_t', mode: 'calculate', nobs: 34, effect_size: '.5', alpha: '.05' }
    ] }));
    const research = await sra.verifyToolkit(spec, { stdio: 'pipe', out: join(dir, 'research') });
    assert.equal(research.code, 0, research.stderr);
    assert.equal(JSON.parse(readFileSync(join(dir, 'research.json'), 'utf8')).checks[0].status, 'CALCULATED');
    bound.checks = [
      { id: 'meta', kind: 'meta_analysis', model: 'random', ci_method: 'modified_hksj', effect_scale: 'mean_difference',
        studies: [{ id: 'a', effect: '0', variance: '1' }, { id: 'b', effect: '0', variance: '1' }] }
    ];
    writeFileSync(spec, JSON.stringify(bound));
    const interval = await sra.verifyToolkit(spec, { manuscript: paper, stdio: 'pipe', out: join(dir, 'interval') });
    assert.equal(interval.code, 0, interval.stderr);
    const intervalReport = JSON.parse(readFileSync(join(dir, 'interval.json'), 'utf8'));
    assert.equal(intervalReport.checks[0].details.ci_method, 'modified_hksj');
    assert.equal(intervalReport.checks[0].details.interval_degrees_of_freedom, 1);
    assert.ok(intervalReport.checks[0].details.confidence_interval[1] > 8.98);
    assert.equal(readFileSync(paper, 'utf8'), content);
    const evidence = JSON.parse(readFileSync(join(__dirname, '../examples/evidence-checks.json'), 'utf8'));
    writeFileSync(spec, JSON.stringify(evidence));
    const evidenceResult = await sra.verifyToolkit(spec, { stdio: 'pipe', out: join(dir, 'evidence') });
    assert.equal(evidenceResult.code, 1, evidenceResult.stderr);
    const evidenceReport = JSON.parse(readFileSync(join(dir, 'evidence.json'), 'utf8'));
    assert.deepEqual(evidenceReport.checks.map(row => row.status), ['CANDIDATES', 'REFUTED', 'UNDETERMINED']);
    assert.equal(evidenceReport.checks[0].details.sources[0].matched_tokens, 5);
    assert.equal(evidenceReport.checks[1].details.differences, 1);
    assert.deepEqual(evidenceReport.checks[2].details.unassessed_checks, ['recruitment']);
    writeFileSync(spec, readFileSync(join(__dirname, '../examples/dependent-data.json')));
    const dependent = await sra.verifyToolkit(spec, { stdio: 'pipe', out: join(dir, 'dependent') });
    assert.equal(dependent.code, 0, dependent.stderr);
    const dependentReport = JSON.parse(readFileSync(join(dir, 'dependent.json'), 'utf8'));
    assert.deepEqual(dependentReport.checks.map(row => row.status), ['CALCULATED', 'CALCULATED', 'CALCULATED']);
    assert.equal(dependentReport.checks[0].details.inference_df, 3);
    assert.ok(Math.abs(dependentReport.checks[1].details.estimate - 2) < 1e-12);
    assert.equal(dependentReport.checks[2].details.risk_difference_bounds.lower_exact, '-1/8');
  } finally { rmSync(dir, { recursive: true, force: true }); }
});
