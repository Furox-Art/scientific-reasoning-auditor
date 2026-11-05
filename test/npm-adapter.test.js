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
  assert.equal(typeof sra.domainReview, 'function');
  assert.equal(typeof sra.domainTemplate, 'function');
  assert.equal(typeof sra.domainValidate, 'function');
  assert.equal(typeof sra.languageBenchmark, 'function');
  assert.equal(typeof sra.domainAggregate, 'function');
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
  await assert.rejects(sra.writingAudit('file.md', { discipline: 'unknown' }), /discipline/);
  await assert.rejects(sra.writingAudit('file.md', { grammarEngine: 'external' }), /grammarEngine/);
  await assert.rejects(sra.writingAudit('file.md', { grammarPort: 99 }), /grammarPort/);
  await assert.rejects(sra.writingAudit('file.md', { grammarTimeout: 99 }), /grammarTimeout/);
  await assert.rejects(sra.domainReview('file.md', { discipline: 'wrong' }), /discipline/);
  await assert.rejects(sra.domainTemplate('', { discipline: 'clinical' }), /non-empty file path/);
  await assert.rejects(sra.domainValidate('file.md', '', { discipline: 'physics' }), /non-empty file paths/);
  await assert.rejects(sra.languageBenchmark('', { expectedSha256: '0'.repeat(64) }), /non-empty CSV/);
  await assert.rejects(sra.languageBenchmark('file.csv', {}), /expectedSha256/);
  await assert.rejects(sra.languageBenchmark('file.csv', { expectedSha256: '0'.repeat(64), maxRows: 0 }), /maxRows/);
  await assert.rejects(sra.domainAggregate(['one.json']), /at least two/);
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

test('runs grounded domain review and exports expert template via Node', async (t) => {
  const projectRoot = path.resolve(__dirname, '..');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-domain-adapter-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const manuscript = path.join(dir, 'article.md');
  fs.writeFileSync(manuscript, '# Methods\nWe calibrated the instrument with a NIST reference.\n'
    + '# Results\nA measured field was 1.5 ± 0.2 mT.\n');
  const review = path.join(dir, 'review.json');
  const outcome = await sra.domainReview(manuscript, {
    discipline: 'physics', out: review, stdio: 'pipe', cwd: projectRoot,
  });
  assert.equal(outcome.code, 0, outcome.stderr);
  const result = JSON.parse(fs.readFileSync(review, 'utf8'));
  assert.equal(result.summary.textual_candidates, 2);
  const template = path.join(dir, 'template.json');
  const templateOutcome = await sra.domainTemplate(manuscript, {
    discipline: 'physics', out: template, stdio: 'pipe', cwd: projectRoot,
  });
  assert.equal(templateOutcome.code, 0, templateOutcome.stderr);
  const draft = JSON.parse(fs.readFileSync(template, 'utf8'));
  assert.equal(draft.kind, 'manual_domain_expert_assessment_template');
  assert.equal(draft.assessments.length, result.items.length);
});


test('runs human-annotation benchmark from Node without downloading raw texts', async (t) => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-human-benchmark-js-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const csv = path.join(dir, 'edits.csv');
  const fields = 'id,sentence-1,sentence-2,arxiv-id,edits-combination-0,edits-combination-1,edits-combination-2';
  const rows = [
    '1,"This is a analysis.","This is an analysis.",1901.00001,"{\'0\': {\'intention\': \'Improve-grammar-Typo\'}}",{},{}',
    '2,"A dataset was used.","A large dataset was used.",1901.00002,"{\'0\': {\'intention\': \'Content\'}}",{},{}',
  ];
  fs.writeFileSync(csv, fields + '\n' + rows.join('\n') + '\n');
  const sha = require('node:crypto').createHash('sha256').update(fs.readFileSync(csv)).digest('hex');
  const out = path.join(dir, 'benchmark.json');
  const runResult = await sra.languageBenchmark(csv, {
    expectedSha256: sha, out, stdio: 'pipe',
  });
  assert.equal(runResult.code, 0, runResult.stderr);
  const report = JSON.parse(fs.readFileSync(out, 'utf8'));
  assert.equal(report.rows_evaluated, 2);
  assert.equal(report.split, 'unverified');
  assert.equal(report.confusion_matrix_against_revision_intents.tp, 1);
  assert.equal(report.confusion_matrix_against_revision_intents.tn_proxy, 1);
});
