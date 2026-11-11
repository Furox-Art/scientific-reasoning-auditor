'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const sra = require('../index.js');

test('paperReview is exposed by the npm adapter', () => {
  assert.equal(typeof sra.paperReview, 'function');
});

test('paperReview requires a file and an explicit model', async () => {
  await assert.rejects(sra.paperReview('', { model: 'mock' }), /non-empty file path/);
  await assert.rejects(sra.paperReview('paper.md', {}), /model is required/);
  await assert.rejects(sra.paperReview('paper.md', { model: ' ' }), /model is required/);
});

test('paperReview refuses invalid chunk sizes before starting Python', async () => {
  for (const chunkChars of [0, 1999, 20001, 3.14, true]) {
    await assert.rejects(
      sra.paperReview('paper.md', { model: 'mock', chunkChars }),
      /chunkChars must be an integer/,
    );
  }
});

test('paperReview validates OCR languages and vision flags before Python starts', async () => {
  for (const ocrMode of ['invalid', '', null]) {
    await assert.rejects(sra.paperReview('paper.pdf', { model: 'mock', ocrMode }), /ocrMode/);
  }
  for (const ocrLanguages of ['eng;echo bad', 'EN', 'eng+badlanguage', '']) {
    await assert.rejects(sra.paperReview('paper.pdf', { model: 'mock', ocrLanguages }), /ocrLanguages/);
  }
  await assert.rejects(sra.paperReview('paper.pdf', { model: 'mock', visualPages: 'true' }), /visualPages/);
});
