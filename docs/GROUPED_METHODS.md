# Grouped-effects models, enumerated bootstrap and cluster planning

Three additional bounded calculations use the existing Python/CLI/Node/MCP
toolkit and source-bound unified review. Install the existing SciPy extra; no
new dependency or network request is introduced. All results are conditional
`CALCULATED` or explicit abstentions. They do not award scientific validity and
remain abstentions in the discrepancy evaluator because they do not compare
reported values. Original sources remain read-only.

```bash
sra verify-toolkit examples/grouped-methods.json --out reports/grouped
```

The example is synthetic software-control data, not an assessment of a real
paper. The real-paper pilot and blank human-review forms remain unchanged.

## One grouped random-intercept variance

`multilevel_meta_analysis` requires 3..30 `studies`, each with distinct simple
`id`, trimmed `group` (1..64 characters), and `effect` within +/-1e6. At least
three groups are required. `effect_scale` is `mean_difference`,
`standardized_mean_difference`, `log_risk_ratio` or `log_odds_ratio`. A supplied
fixed sampling `covariance` must match study order, be exactly symmetric with
positive bounded diagonal, and be numerically positive definite/usable.
These are the same preflight covariance constraints as correlated common-effect
pooling; covariance authenticity is not established.

The model is `y = 1*mu + Z*b + e`, with one Gaussian group intercept per group,
`Var(b) = tau_squared * I`, and **known** `Var(e) = V`. Thus the total covariance
is `Sigma = V + tau_squared * Z*Z'`. This is one variance component and one fixed
intercept, not an arbitrary mixed-model engine or a fit of residual variances,
random slopes, meta-regression or several nested variance components.

The caller must supply `tau2_max` in [1e-12,1e12], in squared effect units.
The implementation minimizes the restricted objective (up to constants)
`log|Sigma| + log(1' Sigma^-1 1) + (y-mu)' Sigma^-1 (y-mu)` on [0,tau2_max].
It centers outcomes and evaluates restricted likelihood/score in orthonormal
Helmert contrasts perpendicular to the fixed intercept. This avoids cancellation
between log determinants, intercept information and score traces when the mean
direction of the supplied covariance is nearly singular. Mean/SE/BLUP calculations
use triangular whitening, rather than forming a full inverse.
The search samples 129 equally
spaced points in `log1p(tau_squared / median(diag(V)))`. Bounded local searches
refine both boundary-adjacent intervals and every sampled local minimum.
Stable contrast-score sign changes are refined with bracketed root searches.
Objective-indistinguishable candidates prefer feasible/stationary score values;
the score resolution guard accounts for contrast/projection arithmetic conditioning.
The selected candidate is checked for convergence/stationarity. A search
touching the upper variance bound is unresolved, not silently accepted as an
unconstrained estimate. The lower zero-variance boundary is valid when the
one-sided stationarity condition is satisfied. Finite multistart search does
not certify a global optimum for every possible supplied covariance.
An upper endpoint whose objective is indistinguishable from the best candidate
within `128 * eps64 * max(1, abs(best_objective), abs(upper_objective))` is also
unresolved, even if a rounded local search selected a point just inside it.
The report exposes that objective gap/band and the unresolved boundary flag;
the band is an arithmetic guard, not a likelihood interval or error bound.

Returned values include the mean, fitted variance, restricted objective/score,
study order, condition number and **conditional BLUPs**
`tau_squared * Z' Sigma^-1 (y-mu)`. BLUPs are not independent group estimates or
fully integrated posterior summaries. The normal mean interval uses the fitted
variance as a plug-in; uncertainty in that variance component is **not
propagated**. No heterogeneity significance test, variance-component interval,
prediction interval or small-sample coverage guarantee is supplied.
`alpha` is [.001,.2], default .05.

Collapsed float64 values, unusable covariance, condition number >1e10, failed
optimization, unresolved stationarity/upper boundary or an unrepresentable mean
interval are explicit. Usable fitted values are retained where possible.
The model and source comparability assumptions remain unverified.

## Exhaustive null-imposed wild cluster bootstrap-t

`wild_cluster_bootstrap` accepts the regression `x`, `y`, `clusters` and optional
`terms` used by cluster regression, with stricter limits: 6..500 observations,
1..4 predictors, 3..10 clusters and more clusters than fitted coefficients.
Declare `term` as one predictor name; intercept tests are outside this operation.
`null_value` defaults to 0 and is bounded to +/-1e6.

The null is imposed by fitting the reduced nuisance model after subtracting the
null predictor contribution. Outcomes are centered before this restriction.
Every one of the `2^G` vectors of
Rademacher -1/+1 cluster weights is enumerated; weights are shared by every
observation in a cluster. The implied bootstrap outcome is the restricted fitted
value plus its signed restricted residual. Equivalent refits use cached fixed
QR projection of the signed residuals, computing the target coefficient change
directly. This avoids numerically reconstructing nuisance fitted outcomes.
Each refit uses CR1 studentization with
factor `G/(G-1)*(N-1)/(N-K)`, testing the same null. There is no RNG, seed,
Monte Carlo subsampling or joint hypothesis/confidence-interval inversion.

The two-sided exceedance rule is
`abs(t_bootstrap) >= abs(t_observed) - numerical_tie_band`, where the explicit
band is `1e-10 * max(1, abs(t_observed))`. This conservatively includes numerical
near-ties rather than letting recomputation of the original/global sign-flipped
sample exclude theoretical ties. The p-value is `exceedance_count / 2^G`, with
no Monte Carlo +1 adjustment. The report retains numerator, full denominator,
unresolved draw count, observed statistic and a fingerprint of all enumerated
statistics (including unresolved entries).
The original/global-minus repetitions must reproduce the observed absolute t
within that band, and every global sign pair must be symmetric. Failed invariants
abstain instead of returning an artificially small p-value. A resolved two-sided
enumerated p-value therefore cannot be below `2/2^G`; few clusters can impose
coarse p-value resolution even when every numerical calculation succeeds.

**Complete sign enumeration does not make this a finite-sample exact test.**
It is a conditional bootstrap approximation, not a randomization test. Cluster
independence, null-model suitability, symmetry and reliability with few clusters
are not authenticated. Numerical tie handling may conservatively increase p.
If the observed studentization or any bootstrap repetition is unresolved, no
p-value is issued: undefined repetitions are never dropped to improve a result.
Existing regression numerical/rank/residual/score safeguards are reused.

## Balanced cluster-mean t-test power

`cluster_power_analysis` models a prospective balanced two-arm comparison of
independent Gaussian cluster means with equal cluster sizes and common variance.
`cluster_size` is an integer in [1,100000], `icc` is [0,1], `effect_size` is [0,10]
and is standardized by the **individual marginal population SD**. `alpha` is
[.001,.2], default .05. The ICC is supplied, not estimated or validated.

With k clusters per arm, m members per cluster and ICC rho, the cluster mean
variance divided by individual variance is `rho + (1-rho)/m`; the design effect
is `1+(m-1)*rho`. The noncentrality is
`effect_size * sqrt(k / (2*(rho+(1-rho)/m)))`. Two-sided power uses noncentral t
with **2*k-2 degrees of freedom**, not degrees of freedom based on all members.
This is the pooled cluster-mean t model; it is not obtained by substituting an
effective individual sample size into an individual-level t test.

`mode: calculate` requires integer `clusters_per_arm` in [2,10000].
`mode: sample_size` requires `target_power` above alpha and at most .9999;
optional `max_clusters_per_arm` is [2,10000], default 10000. A doubling bracket
and integer bisection select a sufficient count, checking the preceding count
when available. Failure to attain the target within the bound is explicit.
The report states counts, participants, design effect, df and numerical
minimality within the supported count range. Saturated/unusable float64 power
does not become a claim of certain power or a verified design.
Targets collapsing onto alpha in float64, or selected/preceding powers within
`64 * ulp(1.0)` of the target, remain unresolved. This is a numerical guard
policy, not a proved tail-probability error bound. Null-effect power is alpha.
If the direct noncentral-t left-tail CDF is nonfinite or outside [0,1], the equivalent positive
survival tail with negated noncentrality is tried. An unusable result still
abstains; no nonfinite probability is interpreted as zero.

Unequal cluster sizes, unequal variances, binary/count/time-to-event outcomes,
attrition, covariate adjustment and stepped-wedge/crossover designs require
different models and are not supported here. This is prospective model-based
planning, not post-hoc power, a fitted ICC or trial-design certification.

## Method references

- [metafor grouped-effects model context](https://www.metafor-project.org/doku.php/analyses:konstantopoulos2011)
- [Wild cluster bootstrap construction](https://s3alfisc.github.io/fwildclusterboot/articles/wild_bootstrap.html)
- [Cluster trial sample-size/df considerations](https://academic.oup.com/ije/article/52/5/1648/7172835)
- [Independent noncentral-t implementation used for controls](https://www.statsmodels.org/stable/generated/statsmodels.stats.power.TTestIndPower.html)

Analytic balanced cases, independent dense restricted likelihood, direct
Statsmodels bootstrap refits and independent t-power checks are software/
numerical validation. They do not supply genuine external reviewer labels or
representative scientific-error accuracy evidence.
