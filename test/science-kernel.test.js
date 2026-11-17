'use strict';
const assert=require('node:assert/strict');
const{test}=require('node:test');
const{mkdtempSync,readFileSync,writeFileSync,rmSync}=require('node:fs');
const{tmpdir}=require('node:os');
const{join}=require('node:path');
const sra=require('../index.js');

test('independent proof kernel Node inputs are validated',async()=>{
  await assert.rejects(sra.proveScience(''),TypeError);
  await assert.rejects(sra.verifyScienceCertificate('', 'proof.json'),TypeError);
  await assert.rejects(sra.verifyScienceCertificate('spec.json',''),TypeError);
});

test('Node drives the native prover and separate certificate interpreter',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'sra-kernel-'));
 try{
  const spec=join(__dirname,'../examples/scientific-proof.json');
  const out=join(dir,'proof');
  const proved=await sra.proveScience(spec,{stdio:'pipe',out});
  assert.equal(proved.code,0,proved.stderr);
  const certificate=out+'.json';
  const report=JSON.parse(readFileSync(certificate,'utf8'));
  assert.equal(report.engine_version,'sra-finite-interval-1');
  assert.deepEqual(report.claims.map(row=>row.status),['ENTAILED','UNRESOLVED','ENTAILED','ENTAILED','CONTRADICTED']);
  const checked=await sra.verifyScienceCertificate(spec,certificate,{stdio:'pipe',out:join(dir,'checked')});
  assert.equal(checked.code,0,checked.stderr);
  assert.equal(JSON.parse(readFileSync(join(dir,'checked.json'),'utf8')).valid,true);
  report.claims[0].status='CONTRADICTED';writeFileSync(certificate,JSON.stringify(report));
  const forged=await sra.verifyScienceCertificate(spec,certificate,{stdio:'pipe',out:join(dir,'invalid')});
  assert.equal(forged.code,1,forged.stderr);
  assert.equal(JSON.parse(readFileSync(join(dir,'invalid.json'),'utf8')).valid,false);
 }finally{rmSync(dir,{recursive:true,force:true});}
});


test('leading-dash proof paths remain literal paths and produce actual reports',async()=>{
 const dir=mkdtempSync(join(tmpdir(),'sra-kernel-flags-'));
 try{
  writeFileSync(join(dir,'--help'),readFileSync(join(__dirname,'../examples/scientific-proof.json')));
  const proved=await sra.proveScience('--help',{stdio:'pipe',cwd:dir,out:'--result'});
  assert.equal(proved.code,0,proved.stderr);
  const certificate=readFileSync(join(dir,'--result.json'),'utf8');
  assert.equal(JSON.parse(certificate).engine_version,'sra-finite-interval-1');
  writeFileSync(join(dir,'--certificate'),certificate);
  const checked=await sra.verifyScienceCertificate('--help','--certificate',{stdio:'pipe',cwd:dir,out:'--checked'});
  assert.equal(checked.code,0,checked.stderr);
  assert.equal(JSON.parse(readFileSync(join(dir,'--checked.json'),'utf8')).valid,true);
 }finally{rmSync(dir,{recursive:true,force:true});}
});
