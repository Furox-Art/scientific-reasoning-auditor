'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const sra = require('../index.js');

test('exports the documented Node API', () => {
  assert.equal(typeof sra.run, 'function');
  assert.equal(typeof sra.audit, 'function');
  assert.equal(typeof sra.createReviewTemplate, 'function');
  assert.equal(typeof sra.reviewModel, 'function');
  assert.equal(typeof sra.verifyStats, 'function');
});

test('rejects invalid arguments before starting Python', async () => {
  await assert.rejects(sra.run('audit'), /array of strings/);
  await assert.rejects(sra.audit(''), /non-empty file path/);
  await assert.rejects(sra.createReviewTemplate('file.md', { mode: 'bad' }), /single.*parallel/);
  await assert.rejects(sra.reviewModel('file.md', {}), /model is required/);
  await assert.rejects(sra.verifyStats(''), /non-empty file path/);
});

test('runs the existing Python CLI without installing dependencies', async () => {
  const result = await sra.run(['--help'], { stdio: 'pipe' });
  assert.equal(result.code, 0, result.stderr);
  assert.match(result.stdout, /usage: sra/);
  assert.match(result.stdout, /audit/);
  assert.match(result.stdout, /verify-stats/);
});


test('runs audit, template, and statistics workflows end-to-end', async (t) => {
  const projectRoot = path.resolve(__dirname, '..');
  const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-node-adapter-'));
  t.after(() => fs.rmSync(outputDir, { recursive: true, force: true }));

  const audit = await sra.audit(path.join(projectRoot, 'examples/sample_manuscript.md'), {
    cwd: projectRoot,
    out: path.join(outputDir, 'audit'),
    stdio: 'pipe',
  });
  assert.equal(audit.code, 0, audit.stderr);
  const report = JSON.parse(fs.readFileSync(path.join(outputDir, 'audit.json'), 'utf8'));
  assert.ok(Array.isArray(report.findings));
  assert.ok(report.reproducibility_manifest);
  assert.ok(report.reasoning_graph);

  const template = await sra.createReviewTemplate(path.join(projectRoot, 'examples/sample_manuscript.md'), {
    cwd: projectRoot,
    out: path.join(outputDir, 'template.json'),
    mode: 'single',
    stdio: 'pipe',
  });
  assert.equal(template.code, 0, template.stderr);
  const templateJson = JSON.parse(fs.readFileSync(path.join(outputDir, 'template.json'), 'utf8'));
  assert.ok(Array.isArray(templateJson.assessments));

  const stats = await sra.verifyStats(path.join(projectRoot, 'examples/welch_t_example.json'), {
    cwd: projectRoot,
    out: path.join(outputDir, 'stats.json'),
    stdio: 'pipe',
  });
  assert.equal(stats.code, 0, stats.stderr);
  const statsJson = JSON.parse(fs.readFileSync(path.join(outputDir, 'stats.json'), 'utf8'));
  assert.equal(statsJson.status, 'PASS');
});
