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
