#!/usr/bin/env node
'use strict';

const { run } = require('../index.js');

run(process.argv.slice(2), { stdio: 'inherit' })
  .then(({ code }) => {
    process.exitCode = code;
  })
  .catch((error) => {
    console.error(`sra: ${error.message}`);
    process.exitCode = 1;
  });
