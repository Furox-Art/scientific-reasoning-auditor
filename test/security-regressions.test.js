'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const sra = require('../index.js');

test('Python adapter does not import a shadow sra package from a caller CWD', async (t) => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-untrusted-cwd-'));
  t.after(() => fs.rmSync(folder, { recursive: true, force: true }));
  const fake = path.join(folder, 'sra');
  fs.mkdirSync(fake);
  fs.writeFileSync(path.join(fake, '__init__.py'), '');
  fs.writeFileSync(path.join(fake, 'cli.py'), 'print("IMPOSTOR_MODULE_EXECUTED")\n');
  const python = execFileSync('python3', ['-c', 'import sys;print(sys.executable)'],
    { encoding: 'utf8' }).trim();
  const out = await sra.run(['--help'], {
    cwd: folder, stdio: 'pipe', env: { SRA_PYTHON: python, PYTHONPATH: '' },
  });
  assert.equal(out.code, 0, out.stderr);
  assert.match(out.stdout, /usage: sra/);
  assert.doesNotMatch(out.stdout, /IMPOSTOR_MODULE_EXECUTED/);
});

test('capture mode imposes an output bound', async (t) => {
  if (process.platform === 'win32') return;
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-output-limit-'));
  t.after(() => fs.rmSync(folder, { recursive: true, force: true }));
  const launcher = path.join(folder, 'sra-fake-python');
  fs.writeFileSync(launcher,
    '#!/usr/bin/env node\n' +
    'if(process.argv.includes("-c"))process.exit(0);\n' +
    'process.stdout.write("x".repeat(9*1024*1024));\n');
  fs.chmodSync(launcher, 0o755);
  await assert.rejects(sra.run(['--help'], {
    stdio: 'pipe', env: { SRA_PYTHON: launcher },
  }), /output exceeded/i);
});

test('interpreter discovery has a finite timeout', async (t) => {
  if (process.platform === 'win32') return;
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'sra-probe-timeout-'));
  t.after(() => fs.rmSync(folder, { recursive: true, force: true }));
  const launcher = path.join(folder, 'sra-hang-python');
  fs.writeFileSync(launcher,
    '#!/usr/bin/env node\n' +
    'if(process.argv.includes("-c"))setTimeout(()=>process.exit(0),10000);\n');
  fs.chmodSync(launcher, 0o755);
  await assert.rejects(sra.run(['--help'], {
    stdio: 'pipe', env: { SRA_PYTHON: launcher },
  }), /Python 3\.11 or newer was not found|not installed/);
});

test('PYTHONPATH via cwd or absolute folder cannot import a shadowed sra module', async (t) => {
  const folder=fs.mkdtempSync(path.join(os.tmpdir(),'sra-shadow-path-'));
  t.after(()=>fs.rmSync(folder,{recursive:true,force:true}));
  const fake=path.join(folder,'sra');fs.mkdirSync(fake);
  fs.writeFileSync(path.join(fake,'__init__.py'),'');
  fs.writeFileSync(path.join(fake,'cli.py'),'print("IMPOSTOR_PYTHONPATH")\n');
  const python=process.env.SRA_PYTHON || execFileSync('python3',
    ['-c','import sys;print(sys.executable)'],{encoding:'utf8'}).trim();
  for (const candidate of ['.',folder]){
    const res=await sra.run(['--help'],{cwd:folder,stdio:'pipe',
      env:{SRA_PYTHON:python,PYTHONPATH:candidate}});
    assert.equal(res.code,0,res.stderr);
    assert.match(res.stdout,/usage: sra/i);
    assert.doesNotMatch(res.stdout,/IMPOSTOR_PYTHONPATH/);
  }
});

test('Python adapter probes and launches in isolated mode, not only safe-path mode', async (t) => {
  if (process.platform==='win32') return;
  const folder=fs.mkdtempSync(path.join(os.tmpdir(),'sra-isolation-'));
  t.after(()=>fs.rmSync(folder,{recursive:true,force:true}));
  const fake=path.join(folder,'fake-interpreter');
  fs.writeFileSync(fake,'#!/usr/bin/env node\n' +
    'if(process.argv.includes("-c"))process.exit(process.argv.includes("-I")?0:1);\n' +
    'process.stdout.write(process.argv.includes("-I")?"ISOLATED\\n":"NOT_ISOLATED\\n");\n');
  fs.chmodSync(fake,0o755);
  const res=await sra.run(['--help'],{stdio:'pipe',env:{SRA_PYTHON:fake,
    PYTHONUSERBASE:folder}});
  assert.equal(res.code,0,res.stderr);
  assert.match(res.stdout,/^ISOLATED/);
});

test('PYTHONUSERBASE fake user-site sra package cannot shadow installed engine', async (t) => {
  const folder=fs.mkdtempSync(path.join(os.tmpdir(),'sra-userbase-'));
  t.after(()=>fs.rmSync(folder,{recursive:true,force:true}));
  const python=process.env.SRA_PYTHON ||
    execFileSync('python3',['-c','import sys;print(sys.executable)'],{encoding:'utf8'}).trim();
  const env={...process.env,PYTHONUSERBASE:folder};
  const userSite=execFileSync(python,['-c','import site;print(site.getusersitepackages())'],
    {env,encoding:'utf8'}).trim();
  const fake=path.join(userSite,'sra');fs.mkdirSync(fake,{recursive:true});
  fs.writeFileSync(path.join(fake,'__init__.py'),'');
  fs.writeFileSync(path.join(fake,'cli.py'),'print("PYTHONUSERBASE_IMPOSTOR")\n');
  const res=await sra.run(['--help'],{stdio:'pipe',env:{SRA_PYTHON:python,PYTHONUSERBASE:folder}});
  assert.equal(res.code,0,res.stderr);
  assert.match(res.stdout,/usage: sra/i);
  assert.doesNotMatch(res.stdout,/PYTHONUSERBASE_IMPOSTOR/);
});
