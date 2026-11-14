# Deterministic Error Benchmark Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task by task. Native implementation, followed by a separate read-only review after the code is written.

**Goal:** Run source-bound checks and evaluate their discrepancies, abstentions and false alarms against frozen, separately supplied labels.

**Architecture:** Pure bounded JSON contracts, actual toolkit execution and an independent label evaluator. CLI, Node and MCP expose the same Python core. No automatic labels or semantic claim mapping.

**Tech Stack:** Python standard library and existing optional toolkit backends; unittest, Node test runner, existing MCP adapter.

**Spec:** `docs/ERROR_BENCHMARK.md`.

## Global Constraints

- English code/docs/reports; read-only source snapshots; no network or arbitrary code.
- Python >=3.11; existing dependency-free base remains supported.
- Explicit synthetic versus real origins; no reviewer or all-field accuracy certification.
- Preserve the current draft PR/branch; never merge or publish.

## Review Focus

- Candidate-only results must abstain even when no candidate is returned.
- Group/source duplication must not leak into development and test denominators.
- Undefined and excluded outcomes must not silently become true negatives.
- Altered imports, incomplete case sets and mismatched quotes must fail before scoring.
- Output paths must not overwrite any imported input, including hard-link aliases.

### Task 1: Frozen manifest and runner

Create `src/sra/error_benchmark.py`; test `tests/test_error_benchmark.py`.
Interfaces: `prepare_manifest(value)`, `run_error_benchmark(value)`,
`error_label_template(value)` accept dict or bounded JSON strings.

- [x] Write failing tests for source identities, split leakage, duplicates,
  actual agreement/disagreement and abstention; run them and observe failure.
- [x] Implement bounded validation and actual toolkit execution with recorded
  source/runtime/result fingerprints; rerun the tests.

### Task 2: Label comparison and reports

Create `src/sra/error_evaluation.py`; extend the same test file.
Interfaces: `evaluate_errors(manifest, predictions, labels)` and
`error_benchmark_markdown(report)`.

- [x] Write RED tests for exact denominators, all-abstained/all-excluded data,
  tampered predictions, complete negatives and third-party adjudication.
- [x] Implement explicit counts/ratios and target/discipline/split strata.
  Reject synthetic labels for real-paper manifests. Verify GREEN.

### Task 3: Deliverable interfaces and verification

Create `src/sra/error_benchmark_cli.py`, synthetic examples and transport tests;
modify CLI dispatch, capabilities, Node typings/wrapper and MCP adapters.

- [x] Pin source-overwrite guards and real CLI/Node/MCP result delivery in tests.
- [x] Implement commands `benchmark-errors`, `error-label-template`,
  `evaluate-errors` and corresponding content-based MCP/Python functions.
- [x] Run full Python/Node/MCP checks, 100% statement coverage, package inventories,
  reproducible builds and rendered report/document QA.
- [x] Obtain a separate read-only code review after implementation; reproduce and
  fix demonstrated findings, then verify the final code.
Delivery gate: commit, validate Windows with module-isolated tests if memory
pressure persists, push only the existing feature branch, update draft PR and
verify CI. Actual delivery/Windows/CI results are recorded in draft PR #8.


## Verification record

- Completed frozen manifests, actual toolkit execution, separate unfilled
  labels, adjudication validation and exact abstention-aware metrics/strata.
- A separate read-only post-implementation reviewer reproduced three issues:
  early binary-float conversion could erase a numeric discrepancy; repeated
  declared source URIs could cross groups/splits; extreme decimal exponents
  could escape as InvalidOperation. RED/GREEN regressions fixed all three.
  The same reviewer reran the original reproductions, 14 core tests and the
  focused MCP test and confirmed closure with no remaining demonstrated issue.
  This was software review, not independent scientific expert validation.
- Final Linux Python 3.12.14: 789 tests passed, 6906/6906 runtime statements
  covered (100% statement coverage). Node24.22.1: 29 tests passed. MCP46 tests
  passed. Compile/dependency/whitespace and 10 synthetic controls passed.
- Repeated wheel/normalized-sdist builds were byte-identical; exact inventories
  (179 source files,62 runtime modules), isolated installation/CLI/audit and
  metadata checks passed. Nothing was published.
- Run/evaluation reports and the operation contract were rendered, visually
  inspected and checked for text overflow. Synthetic labels remain explicitly
  fabricated software controls; no actual external labels were collected.
