# Changelog

## 0.11.0 — 2026-11-17

- Read manuscript bytes in bounded 64 KiB pieces to avoid allocating the full input cap for small files under memory pressure; retain the 32 MiB plus-one oversize guard.

- Add an own standalone finite-model/exact-rational-interval proof kernel with counter-worlds, deletion-minimal explanations, source anchors and a separate scalar certificate verifier. Expose Python, CLI, Node and MCP interfaces without external solver/model dependencies.

- Strengthen method audits with explicit quote offsets/ambiguous-occurrence abstention, selected comparator/reference coverage, and optional conservative normal-model confidence bounds for paired measurement limits.

- Add four scoped method audits: supplied contribution-feature comparisons, search-record consistency, paired measurement agreement and question/method target alignment. Preserve overall adequacy abstentions and source evidence; toolkit adapter is bounded-toolkit-5.

- Default unified Markdown reports to concise English with explicit execution states and a compact criteria worksheet. Preserve module evidence, numerical results and uncertainty; retain the full technical presentation as an option.
- Add CLI `--report-style`, Python `review_markdown(..., style=...)`, Node `reportStyle`, and opt-in MCP `report_style` / `readable_report`. JSON calculations and manuscripts are unchanged.
- Raise the npm adapter's Python engine floor to 0.11.0 for the new CLI option. The adapter version is 0.4.0. Calculation rules remain 0.10.1.


All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The Python package (`scientific-reasoning-auditor`) and the Node.js adapter
(`scientific-reasoning-auditor` on npm) are versioned independently.

## [Unreleased]

- `statistic_consistency` now abstains (UNDETERMINED) instead of refuting when a
  discrepancy under the default undeclared two-sided t/z tail or uncorrected F df is
  also consistent with a plausible undeclared analysis choice: a one-tailed test in
  the statistic direction, or a sphericity df correction (Greenhouse-Geisser /
  Huynh-Feldt) reachable within the epsilon lower bound. Caller-declared tails and
  supplied corrected df are unaffected and resolve the abstention; VERIFIED results
  are never overturned. Fail-closed, consistent with the unknown-direction abstention.
- Re-measured on the frozen 1120-result published psychology reference cohort: false
  alarms 20 -> 1, decided precision 63.0% -> 96.4%, selective risk 2.98% -> 0.15%, at a
  documented recall cost (reference-frame recall 34/49 -> 27/49; 7 genuine errors move
  to transparent abstention because they share the undeclared-choice numeric signature).
  Retrospective in-sample tuning on a psychology-only cohort; the frozen 0.9.0 first
  run is preserved unchanged. See benchmarks/reference_abstention_remeasurement_20261120.
- README current status aligned to Python 0.11.0 / Node 0.4.0; prospective blinded
  human validation explicitly marked PENDING (cannot be performed by the software).
  No new human labels, prospective or multi-field accuracy claim is made.

## [0.10.0] - 2026-11-16

Python engine/ruleset 0.10.0 and Node adapter 0.3.0.

- Declared greater/less/two-sided t/z statistic consistency with signed rounding
  intervals; unknown test direction explicitly abstains. F/chi-square remain
  upper-tail only. Defaults for existing structured inputs remain documented.
- Positive decimal df with explicit precision: fractional df require an exact
  caller declaration; unknown/rounded df abstain. No correction method is inferred.
- Df conversion that loses exact decimal values abstains; statistic bounds are
  rounded outward. This closes a software-review counterexample without claiming
  general arbitrary-precision inference or a formal backend error bound.
- Source-prepared statistic candidates require direction/df confirmation and
  recognize fractional df without executing inferred assumptions.
- Frozen NIST-derived numerical controls and separately marked synthetic guards,
  complete separate reports and source/fixture/runtime hashes. Original 0.9.0
  historical results are preserved; no new human or multi-field paper validation.

## [0.9.1] - 2026-11-16

Python engine 0.9.1 and independently versioned Node adapter 0.2.1.

- Publish the historical-reference comparator, protocol, frozen first reports
  and posthoc source notes in the Python source distribution and npm archive.
  The Python wheel remains the engine distribution; the historical comparison
  still requires a separate pinned 0.9.0 engine environment.
- Update current installation/release documentation and citation metadata.
  Numerical decision rules and historical result bytes remain unchanged.
- Source-checkout comparison of unchanged published SRA 0.9.0 with pinned,
  source-declared historical manual labels: 1120 retained psychology results,
  60% decision coverage and 34/49 reference errors flagged. Preserves the first
  completed result, source/wheel/specification hashes, exclusions and abstentions.
  This is not new blinded human review or whole-paper/multi-field validation.

## [0.9.0] - 2026-11-15

Python engine 0.9.0 and independently versioned Node adapter 0.2.0.
The GitHub source release also includes the MCP adapter and offline collection
and replay tools. No independent scientific expert validation is claimed.

### Added

- Generic offline frozen-cohort reviewer packets and pre-adjudication inspection,
  with distinct blank adjudicator packets and no generated human decisions.
  Error evaluation adds four-label Cohen kappa for fixed declared reviewer pairs,
  paper/group strata and descriptive leave-one-group-out sensitivity. These are
  collection/diagnostic tools, not representative scientific-error validation.

- Bounded one-group-intercept REML meta-analysis, exhaustive null-imposed wild
  cluster bootstrap-t and balanced equal-size cluster-mean power/planning.
  Complete sign enumeration is not finite-sample exact inference; fitted-variance
  uncertainty and unsupported cluster designs remain explicit limits.
- Optional identity-working-model CR2 and unscaled CR3 cluster covariance, with
  explicit t(G-1), numerical leverage guards and unchanged CR1 defaults.
- Explicit source-checkout Docker analysis replay with exact frozen inputs,
  pinned local images, two-run numeric comparison, bounded output/resources and
  verified container cleanup. It never executes automatically during review.
- Offline real-paper feasibility packet recipe: two licensed full papers, four
  manually mapped statistic cases, separate blank reviewer sheets and strict
  returned-sheet/adjudication merging. No human labels or accuracy estimates.
- Seven bounded research-method kinds: declared-DAG backdoor checks, caller bias
  evidence, prospective power/sample size, meta-analysis/sensitivity, Bayesian
  chain diagnostics, ML split manifests and offline Crossref update snapshots.
- Directional Crossref updates in existing opt-in DOI requests, without extra
  requests; numerical environment metadata; Python 3.15 CI with older-runtime
  conditional optional dependencies. Reports remain separate and manuscripts read-only.

- Source-located inspection preparation across CLI, Python, Node and MCP; proposed
  equations/statistic inputs require confirmation and never execute automatically.
- Domain-aware bounded symbolic operations in isolated workers; regression,
  missingness, multiple-testing and rounding-aware reported-statistic checks;
  local citation context, keyed table/supplement comparisons and inert SVG review.
- Frozen SciFact real-paper sentence-retrieval evaluation with released human
  rationale labels, explicit overlap metrics and semantic abstentions. This does
  not supply new multi-field expert-validated scientific-error accuracy estimates.

- Optional local inspection toolkit: SymPy exact polynomial/calculus checks,
  Pint conversions, SciPy raw-data replay, spaCy sentence candidates and RapidFuzz
  passage ranking. Bounded non-executable specifications, per-check backend
  versions, explicit partial execution and separate source-bound user reports.
- `verify-toolkit` CLI, Python API, typed Node `verifyToolkit`, MCP `verify_toolkit`
  and additive unified-review inputs. Base runtime remains dependency-free;
  candidate retrieval never awards a truth or semantic citation-support verdict.

- Optional MIT-licensed Z3 formal-verification integration with a pinned `logic`
  extra, restricted Boolean/linear-arithmetic input, consistency checks,
  conditional VERIFIED/REFUTED/UNDETERMINED findings and stable report identities.
- Read-only `sra verify-logic`, Node `verifyLogic`, MCP `verify_logic` and an optional
  source-bound logic module in unified review. Findings go to separate reports.

- Source-bound `sra review` and `sra capabilities` commands with multi-profile
  composition, declared study-type applicability, explicit module execution
  states, coverage gaps, JSON schema and Markdown reports.
- Typed Node `reviewManuscript`/`capabilities` wrappers with feature-contract probes,
  plus bounded MCP tools with existing caller/host network and model consent gates.
- Six synthetic cross-field workflow controls; they are not scientific accuracy
  or independent expert-validation evidence.

### Fixed

- Both registry release workflows install all optional method/test backends and
  run the MCP regression suite before publishing the exact tagged source.

- Git provenance subprocesses now detach standard input, avoiding consumption of
  or waits on MCP stdio protocol input on Windows.
- MCP temporary-path scrubbing handles both native and forward-slash spellings.
- Unified model findings follow declared study-type exclusions; PDF source
  changes are hard errors, and optional vision uses prevalidated source bytes.
- Extended statistical input validation precedes optional SciPy imports and
  outbound requests. Failed DOI lookups preserve results and yield partial execution.
- Distribution verification accepts generated metadata CRLF/LF differences while
  retaining byte-exact source inventory checks and rejecting changed content.

## [0.8.0] - 2026-11-08

### Added

- Multilingual vocabulary: section headings, direction wording, absolute claims, association and causal verbs, multiplicity corrections, group counts, rate measures, paired designs and test names for es, pt, fr, de, it, nl, ru, pl, id, ar, hi, zh, ja and ko, with a test per term that the rule actually receives it.

## [0.7.1] - 2026-11-08

### Added

- Synthetic rule ablation: `benchmarks/rule_ablation/` plants one condition per case and `docs/RULE_ABLATION.md` records which rules fired, which stayed silent and which fired where nothing was planted (20/21 exercised, 1 unexercisable, 2 firing off-target).
- `docs/CHECK_INVENTORY.md`: every finding code with what it detects, what it cannot detect and where its false positives come from, enforced by a test that derives the rule ids from the syntax tree and compares the two directions.
- An end-to-end test of the expert-validation pipeline: two synthetic reviewers, one adjudicator, inter-reviewer agreement and Cohen's kappa, then per-code and micro-average precision/recall/specificity with Wilson intervals. It protects the machinery, not the accuracy: synthetic labels are not evidence.

## [0.7.0] - 2026-11-08

### Added

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

[Unreleased]: https://github.com/Furox-Art/scientific-reasoning-auditor/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.9.0
[0.8.0]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.8.0
[0.7.1]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.7.1
[0.7.0]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.7.0
[0.6.0]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.6.0
[0.5.4]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.5.4
[0.5.3]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.5.3
[0.5.2]: https://github.com/Furox-Art/scientific-reasoning-auditor/releases/tag/v0.5.2
