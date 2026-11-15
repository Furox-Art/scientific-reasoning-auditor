# Bounded grouped models, bootstrap and cluster planning

Implement three explicitly defined calculations using existing toolkit, source
binding, Python/CLI/Node/MCP interfaces and abstention conventions. No invented
human labels or representative-corpus accuracy claims. Preserve all pilot inputs.

- Intercept-only Gaussian grouped-effects meta-analysis: supplied fixed sampling
  covariance plus one estimated nonnegative group-intercept variance. Bounded
  scalar REML search, convergence/domain diagnostics, plug-in normal intervals.
  No random slopes, arbitrary variance components or small-sample certification.
- Null-imposed wild cluster bootstrap-t: all 2^G Rademacher sign vectors for
  3..10 clusters; CR1 studentization and an explicit conservative numerical tie
  band. No random seed/Monte Carlo, dropped unresolved draws or exact-test claim.
- Balanced, equal-size two-arm Gaussian cluster-mean t-test power and integer
  cluster-count search. Individual-SD effect, common ICC, df=2k-2. Unequal cluster
  sizes, unequal variances, binary outcomes and stepped wedges remain unsupported.

Validate against analytical balanced cases, independent dense restricted
likelihood calculations, direct Statsmodels bootstrap enumeration and noncentral
t power. Test failed/unstable inputs and all transport paths. Obtain separate
read-only agent review after implementation, resolve findings, verify Windows
and Linux, push existing branch and update draft PR 8. Do not merge/publish.
