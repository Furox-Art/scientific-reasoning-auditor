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
  assert.equal(typeof sra.writingAudit, 'function');
  assert.equal(typeof sra.verifyDoi, 'function');
  assert.equal(typeof sra.benchmarkPmc, 'function');
  assert.equal(typeof sra.evaluateLabels, 'function');
});

test('rejects invalid arguments before starting Python', async () => {
  await assert.rejects(sra.run('audit'), /array of strings/);
  await assert.rejects(sra.audit(''), /non-empty file path/);
  await assert.rejects(sra.createReviewTemplate('file.md', { mode: 'bad' }), /single.*parallel/);
  await assert.rejects(sra.reviewModel('file.md', {}), /model is required/);
  await assert.rejects(sra.verifyStats(''), /non-empty file path/);
  await assert.rejects(sra.writingAudit(''), /non-empty file path/);
  await assert.rejects(sra.writingAudit('file.md', { genre: 'invalid' }), /genre/);
  await assert.rejects(sra.writingAudit('file.md', { abstractMaxWords: -1 }), /non-negative integer/);
  await assert.rejects(sra.verifyDoi(''), /non-empty file path/);
  await assert.rejects(sra.verifyDoi('file.md', { limit: 0 }), /limit/);
  await assert.rejects(sra.benchmarkPmc(''), /non-empty file path/);
  await assert.rejects(sra.benchmarkPmc('test.json', { online: false }), /online: true/);
  await assert.rejects(sra.evaluateLabels('', 'labels.json'), /benchmark/);
  await assert.rejects(sra.evaluateLabels('benchmark.json', ''), /labels/);
  await assert.rejects(sra.writingAudit('file.md', { styleLanguage: 'unknown' }), /styleLanguage/);
  await assert.rejects(sra.writingAudit('file.md', { design: 'unknown' }), /study design/);
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

test('runs academic writing audit from Node and reads advisory reports', async (t) => {
  const projectRoot = path.resolve(__dirname, '..');
  const outputDir = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-writing-adapter-'));
  t.after(() => fs.rmSync(outputDir, { recursive: true, force: true }));
  const target = path.join(outputDir, 'writing');
  const result = await sra.writingAudit(path.join(projectRoot, 'examples/academic_writing_sample.md'), {
    cwd: projectRoot, out: target, genre: 'original-research',
    abstractMaxWords: 4, stdio: 'pipe',
  });
  assert.equal(result.code, 0, result.stderr);
  const report = JSON.parse(fs.readFileSync(target + '.json', 'utf8'));
  assert.equal(report.tool, 'academic-writing-audit');
  assert.ok(report.findings.some((finding) => finding.code === 'unmatched_numeric_citation'));
  assert.ok(report.findings.some((finding) => finding.code === 'abstract_above_limit'));
  assert.match(fs.readFileSync(target + '.md', 'utf8'), /Review prompts/);
});

test('runs registry identifier scan in offline mode', async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-doi-adapter-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const manuscript = path.join(dir, 'source.md');
  const target = path.join(dir, 'doi.json');
  fs.writeFileSync(manuscript, '# References\nA doi:10.1371/journal.pone.0000217 citation.\n');
  const outcome = await sra.verifyDoi(manuscript, { out: target, stdio: 'pipe' });
  assert.equal(outcome.code, 0, outcome.stderr);
  const result = JSON.parse(fs.readFileSync(target, 'utf8'));
  assert.equal(result.results[0].status, 'NOT_CHECKED_OFFLINE');
});
