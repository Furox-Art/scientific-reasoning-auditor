# Research-method reliability implementation plan

**Goal:** Improve conditional numerical inference and honest reporting without
changing manuscripts or claiming cross-disciplinary scientific correctness.

**Architecture:** Preserve the existing bounded preflight and shared toolkit
execution. Add an opt-in interval method and repair allocation/reporting defects
in the same Python engine used by CLI, Node and MCP. No new dependencies.

## Priorities and design

1. **Power allocation and numerical limits:** Reproduce decimal-to-binary
   allocation errors before fixing them. Compute the ceiling of the declared
   ratio exactly, recompute power using the resulting integer sizes, handle
   minimum feasible sample sizes, and abstain on unusable probabilities. Report
   pooled-variance assumptions for the independent t design explicitly.
2. **Small-study meta-analysis uncertainty:** Keep `ci_method: normal` as the
   default. Add `modified_hksj` for random effects only, using residual scale
   `max(1, sum(w*(y-mu)^2)/(k-1))` and Student t with `k-1` degrees of freedom.
   Report method, scale, critical value and interval standard error. Preserve
   leave-one-out point estimates, including the one-study case.
3. **Incomplete ML manifests:** Check all ordered temporal partition pairs;
   missing validation times must not hide a known train/test violation. Use
   `incomplete` when no violation is found but checks remain unassessed; retain
   `violations_found` when evidence of a violation exists.

Alternative: adding more unsupported method families would widen the surface
before addressing these inference/reporting limitations. Switching the default
meta interval would silently change existing consumers; the opt-in method avoids
that compatibility change. The modified method can be conservative and does not
certify study validity or guarantee nominal coverage.

## Execution and verification

- [x] Establish a clean baseline from PR head `9943158` on this Linux runtime.
- [x] Add failing numerical and incomplete-manifest regression tests.
- [x] Implement each fix and the selected interval method; run targeted tests.
- [x] Exercise CLI, Node and MCP transport and manuscript immutability.
- [x] Update method documentation and a synthetic example in English.
- [x] Run complete Python coverage, Node/MCP, synthetic controls and packaging
      checks; inspect generated report rendering where available.

Delivery procedure: review the diff, commit, push the existing remote branch,
update the draft PR and inspect its checks. Record final remote verification in
the PR description. Do not merge or publish.

### Local evidence

Python 3.12.14 / Node 24.22.1 on Linux: baseline 739 Python, 28 Node and
43 MCP tests passed. Extension: 749 Python, 28 Node and 44 MCP tests passed;
6280 runtime statements, 100% statement coverage. The 10 synthetic controls,
compile checks, dependency consistency, identical independent wheel/normalized
sdist builds, exact package inventories, isolated wheel install and metadata
checks passed. Rendered method documentation and example report were visually
inspected. These are software checks, not independent scientific validation.

## Remaining scientific gaps

Correlated/multilevel meta-analysis, prediction intervals, complex power designs
(Welch, cluster/random-effects, attrition), feature/label content leakage and
independent scientific-error benchmarks remain outside this implementation.
These are limitations to document, not positive validation claims.

## Method references

- Röver, Knapp and Friede (2015), equations 9–11:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC4647507/
- Statsmodels power and meta-analysis API documentation linked in
  `docs/RESEARCH_METHODS.md`.
- Scikit-learn common pitfalls, data leakage:
  https://scikit-learn.org/stable/common_pitfalls.html
