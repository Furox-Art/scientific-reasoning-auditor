# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The Python package (`scientific-reasoning-auditor`) and the Node.js adapter
(`scientific-reasoning-auditor` on npm) are versioned independently.

## [Unreleased]

## [0.7.0] - 2026-11-08

### Added

- Synthetic rule ablation: `benchmarks/rule_ablation/` plants one condition per case and `docs/RULE_ABLATION.md` records which rules fired, which stayed silent and which fired where nothing was planted (20/21 exercised, 1 unexercisable, 2 firing off-target).
- `docs/CHECK_INVENTORY.md`: every finding code with what it detects, what it cannot detect and where its false positives come from, enforced by a test that derives the rule ids from the syntax tree and compares the two directions.
- An end-to-end test of the expert-validation pipeline: two synthetic reviewers, one adjudicator, inter-reviewer agreement and Cohen's kappa, then per-code and micro-average precision/recall/specificity with Wilson intervals. It protects the machinery, not the accuracy: synthetic labels are not evidence.
- `statistics.impossible_p_value`: a printed p-value that cannot be a probability (`p = 0.000`, `p = 1.4`, `p > 1`, negative p). Values are parsed and judged numerically, so `p = 0.03` and `p < 0.001` stay silent.
- `statistics.impossible_dispersion`: a negative standard deviation or standard error, or a sample size of zero.
- Table values: PDF text is read in layout mode, and a row whose header names n, mean, SD, SE or p is turned into the statements the plausibility rules read, with the table row and column recorded as evidence.
- `statistics.group_count_test_mismatch`: three or more groups compared with pairwise tests only, with no omnibus test and no adjusted contrast named.
- `statistics.confidence_interval_p_conflict`: a sentence whose 95% CI contains the null while p < 0.05, or excludes it while p >= 0.05 (ratios use 1 as the null).
- `statistics.mean_outside_confidence_interval`: a reported mean that lies outside its own 95% CI.

All five are sentence-scoped: a descriptive interval is never compared with a p-value, numbers spread across sentences, tables or figures are not compared, and a group count is judged against the tests named in its own sentence.

## [0.6.0] - 2026-11-08

### Added

- `statistics.multiplicity_unaddressed`: three or more reported p-values with no
  mention of a correction, a test family or a procedure that corrects by itself.
- `statistics.design_test_mismatch`: an independent-samples test quoted for a
  design described as paired, matched, repeated-measures or before/after, unless
  a paired test is also named.

Both are wording checks that point at the sentences and ask for adjudication;
neither decides which analysis was run.

## [0.5.4] - 2026-11-08

### Fixed

- One commit now means one set of bytes, and one file means one extracted text.
  `load_document` normalises line endings once, so a manuscript saved with
  Windows CRLF produces the same extracted-text digest as the same manuscript
  with LF; before this, `sra audit paper.md` followed by
  `sra review-template paper.md` rejected its own audit on Windows. The exact
  bytes remain covered by `input.sha256`.
- `.gitattributes` pins `* text=auto eol=lf`. A checkout with
  `core.autocrlf=true` used to give the tracked files CRLF, which changed raw
  source digests and failed a published-fingerprint test on files nobody had
  edited.
- Test fixtures write UTF-8 explicitly and keep the bytes they hash; the symlink
  and POSIX bash-guard cases skip where the platform cannot run them. Windows
  now runs the suite clean (499 tests, 3 skipped) instead of 50 failures.

## [0.5.3] - 2026-11-08

### Fixed

- Release pipeline unblocked: the repository provenance inventory is sorted by the
  recorded posix name instead of by `Path` (whose comparison is case-insensitive,
  so `bin/sra.js` sorted before `LICENSE` and the distribution verifier rejected
  the order), and `src/sra/py.typed` is part of the provenance, wheel and
  installed-package inventories, which previously disagreed with the artifact by
  exactly that file (`c8fdd4b`, `65617a5`, `fa28693`). The verifier fixtures now
  ship the same marker instead of failing before their own assertions
  (`a4a9211`).
- `test_run_pmc_sleeps_between_multiple_articles` patched the shared `time`
  module, so any unrelated sleep in the audit path counted as the benchmark's
  pause; it now replaces `sra.benchmark.time` and pins the exact 0.38 s pause
  (`c8fdd4b`).

### Added

- Verify two-sided two-proportion z-tests from 2x2 event counts, comparing the
  reported proportions, difference, z statistic and p-value within explicit
  tolerances (`d6ac1a5`).
- Blinded expert-validation pack: prediction-free PMC worksheets bound to frozen
  source hashes, two independent reviewer sheets merged with a third
  adjudicator, and a preregistered pilot protocol. No expert labels are
  generated by the tooling; quality metrics stay unavailable until real
  reviewers complete the pack (`771bf4b`).

### Changed

- npm adapter released as 0.1.2: it refuses to drive a Python engine older than
  0.5.2, naming the version it found, the floor and the upgrade command instead
  of failing later on a CLI command that version lacks. An importable `sra`
  without distribution metadata keeps the old behaviour. It remains versioned
  independently of the Python package (`1e37267`, `16d9f8d`).
- npm adapter released as 0.1.1; it is versioned independently of the Python
  package (`1e37267`).

## [0.5.2] - 2026-11-05

### Added

- Academic writing checks with source-located citation review (`8e5bbf0`).
- Statistical, DOI, writing and PMC validation tools in the science audits
  (`89aba15`).
- Academic language review and discipline evidence adjudication (`2abb353`).
- Measurement of scientific language edit coverage, plus a strengthened blinded
  expert assessment (`c3d6d09`).

### Fixed

- Indented manuscript fences are handled correctly, and duplicate statistics
  keys are rejected (`7ea5976`).

### Changed

- Release tests install the package in editable mode (`dc835a5`).

[Unreleased]: https://github.com/Furox-Art/scientific-reasoning-auditor/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.7.0
[0.6.0]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.6.0
[0.5.4]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.5.4
[0.5.3]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.5.3
[0.5.2]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.5.2
