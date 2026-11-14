# Dependent Data Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task by task. Implement natively; request a separate read-only review after writing the code.

**Goal:** Add bounded one-way CR1 regression, known-covariance common-effect GLS pooling and exact binary missing-outcome sensitivity.

**Architecture:** Dependency-independent preflight in `dependent_spec.py`;
numerical/exact calculations in `dependent_checks.py`; existing toolkit and
source-bound criteria interfaces. No arbitrary analysis code or new runtime
dependency. SciPy/NumPy numerical results remain conditional on declared inputs.

**Tech Stack:** Python >=3.11, existing SciPy/NumPy; Fraction, unittest and
existing Python/CLI/Node/MCP transports.

**Spec:** `docs/DEPENDENT_DATA.md`.

## Constraints and review focus

- Read-only sources and separate English reports; no scientific validity or
  independent expert certification. No merge or package publication.
- Rank/conditioning, unknown covariance scenarios, zero uncertainty and tail
  underflow must abstain without hiding valid retained results.
- Exact decimal source differences must not silently collapse in float64.
- Omission sensitivity must retain dependent covariance/cluster units.
- Missing-outcome threshold equality and unreachable counts require exact math.
- Strict input bounds, source identities and no extra fields before imports.

### Task 1: Clustered/regression and GLS calculations

Create `src/sra/dependent_spec.py`, `src/sra/dependent_checks.py` and
`tests/test_dependent_data.py`; integrate toolkit dispatch/capabilities.

- [x] Write failing tests against independent Statsmodels CR1, analytical GLS,
  covariance permutations, singular data and partial sensitivity scenarios.
- [x] Implement strict preflight, stabilized calculations and explicit unknowns.
- [x] Verify all focused tests and preserve old toolkit behavior.

### Task 2: Missing-outcome exact sensitivity

- [x] Write failing tests against exhaustive small count grids, strict threshold
  equality, zero missingness and million-participant bounded execution.
- [x] Implement exact bounds/frontiers with Fraction and verify GREEN.

### Task 3: Delivery and review

- [x] Integrate criteria scopes, synthetic examples, docs and actual CLI/Node/MCP
  transport tests; calculation-only kinds must abstain in error evaluation.
- [x] Run complete Python/Node/MCP tests, 100% statement coverage, synthetic
  controls, reproducible builds, inventories and rendered report/document QA.
- [x] Obtain separate post-implementation review and resolve reproduced bugs.

Delivery results (Windows tests, existing feature-branch push and CI) are recorded
in draft PR #8 after validation, without merging or publishing.


## Implementation verification

- Implemented one-way CR1 OLS, fixed supplied-covariance common-effect GLS and
  exact binary missing-outcome bounds/frontiers through the existing toolkit,
  criteria and Python/CLI/Node/MCP interfaces. No new dependency or model-fitting
  claim beyond these documented methods.
- Independent software cross-checks use Statsmodels CR1, analytical/direct GLS
  solves, dependency-preserving omissions and exhaustive small binary tables.
- A separate read-only post-implementation reviewer reproduced perfect-fit
  residual-roundoff inference and high-slope cancellation requiring upstream
  residual error propagation. RED/GREEN regressions cover these and additionally
  centered GLS Q/location stability and unrepresentable confidence intervals.
  The reviewer rechecked the final guards, slopes through1e9 and all17 focused
  tests, with no remaining demonstrated actionable finding. This was software/
  numerical review, not independent scientific expert validation.
- Final Linux Python3.12.14:806 Python tests passed,7168/7168 runtime statements
  covered (100% statement coverage). Node24.22.1:29 tests passed; MCP47 tests
  passed. Compile/dependency/whitespace and10 synthetic controls passed.
- Two wheel/normalized-sdist builds matched byte for byte; exact inventories
  (183 source files,64 runtime modules), isolated install/CLI/audit and package
  metadata checks passed. No package was published.
- Final report/contract were rendered, inspected visually and checked for text
  overflow. Windows and remote CI results are tracked separately in draft PR#8.
