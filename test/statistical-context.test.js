'use strict';
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const sra = require('../index.js');

test('declared direction and fractional df survive the real Node transport', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-context-'));
  try {
    const spec = path.join(root, 'spec.json');
    const base = {kind:'statistic_consistency', test:'t', df:[1], statistic:'2.000000000000', reported_p:'.147584'};
    fs.writeFileSync(spec, JSON.stringify({schema_version:'1.0', checks:[
      {...base,id:'one_sided',alternative:'greater'},
      {...base,id:'unknown',alternative:'unknown'},
      {...base,id:'fractional',test:'F',df:['2','.5'],df_precision:'exact',reported_p:'.577350'}
    ]}));
    const before = fs.readFileSync(spec);
    const result = await sra.verifyToolkit(spec, {stdio:'pipe',out:path.join(root,'report')});
    assert.equal(result.code,1,result.stderr); // Explicit unknown is partial execution.
    const report = JSON.parse(fs.readFileSync(path.join(root,'report.json'),'utf8'));
    assert.deepEqual(report.checks.map(row=>row.status),['VERIFIED','UNDETERMINED','VERIFIED']);
    assert.equal(report.checks[0].details.alternative,'greater');
    assert.equal(report.checks[2].details.correction_method_verified,false);
    assert.deepEqual(fs.readFileSync(spec),before);
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});

test('source statistic preparation retains separate df and every literal result', async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-preparation-'));
  try {
    const paper = path.join(root, 'paper.md');
    const content = 'X^(2) = 7.66, df = 2, P = 0.02; X²(2) = 11.54, P < .01';
    fs.writeFileSync(paper, content);
    const response = await sra.prepareInspection(paper, {stdio:'pipe', out:path.join(root, 'prepared')});
    assert.equal(response.code, 0, response.stderr);
    const report = JSON.parse(fs.readFileSync(path.join(root, 'prepared.json'), 'utf8'));
    const rows = report.candidates.filter(row => row.suggested_check);
    assert.deepEqual(rows.map(row => row.suggested_check.statistic), ['7.66', '11.54']);
    assert.equal(report.checks_executed, false);
    for (const row of rows) {
      assert.equal(content.slice(row.start, row.end), row.source_quote);
      assert.equal(row.suggested_check.alternative, 'unknown');
      assert.equal(row.suggested_check.df_precision, 'unknown');
    }
    assert.equal(fs.readFileSync(paper, 'utf8'), content);
  } finally { fs.rmSync(root, {recursive:true, force:true}); }
});
