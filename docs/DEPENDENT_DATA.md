# Dependent-data calculations and missing-outcome sensitivity

Three bounded toolkit kinds use supplied structured data. Python, CLI, Node,
MCP and source-bound unified review use the existing toolkit contract. Sources
are read-only and results stay in separate reports. No model selection, source
mapping, cluster independence, outcome authenticity or scientific adequacy is
automatically verified. These calculations do not certify causal effects.

```bash
sra verify-toolkit examples/dependent-data.json --out reports/dependent
```

## Cluster-robust linear regression

`cluster_robust_regression` requires `x` (6..5000 rows, 1..8 numeric columns),
`y` and `clusters` of the same row count. Numeric magnitudes are at most 1e12;
missing/nonfinite values are rejected. Cluster IDs are nonempty strings <=64
characters; there must be at least three clusters and more clusters than fitted
coefficients. An intercept is always included. Optional `terms` gives distinct
simple names for predictors (default x1, x2, ...); `intercept` is reserved.
`alpha` is in [.001,.2], default .05. `leave_one_cluster_out` is boolean,
default false, permitted only with at most 50 clusters.

Rows can represent repeated measurements when `clusters` identifies subjects.
The model is a caller-specified marginal linear mean model with one-way CR1
cluster-robust covariance. It is not a fitted random-effects model, repeated
measures ANOVA, GEE, two-way cluster procedure, CR2/CR3 estimator or wild-cluster
bootstrap. Between-cluster independence and a correctly specified mean model
remain assumptions. More observations inside a cluster do not establish more
independent clusters. Small-cluster inference can be unreliable even when the
calculation completes; the report always retains this limitation.

The implementation centers/scales predictors, uses QR least squares and maps
coefficients/covariance back to original units. With N observations, K fitted
coefficients and G clusters, the CR1 factor is
`G/(G-1) * (N-1)/(N-K)`. For residual scores `s_g = X_g' u_g`, covariance is
`factor * (X'X)^-1 sum(s_g s_g') (X'X)^-1`. Individual coefficient tests and CIs
use Student t with G-1 degrees of freedom. No joint hypothesis test is produced.

Rank-deficient/ill-conditioned normalized designs (condition number >1e8),
distinct decimal values collapsing in float64, zero coefficient uncertainty or
unusable tail probabilities abstain explicitly. Valid coefficients/other
inferences are retained where possible. Optional cluster omissions refit the
mean model and return coefficient changes; an unidentified omission remains
unknown rather than being silently dropped. They do not refit CR1 inference.
Residual L2 norms at or below `32 * eps64 * max(N,K) *
(norm(centered_y) + norm(fitted_centered_y))` cannot resolve uncertainty;
coefficients remain available but covariance, SEs, intervals and p-values are
null. This conservative numerical-resolution rule prevents exact affine fits
from turning floating-point residual noise into apparent statistical evidence.
Likewise, the absolute score accumulation resolution
`32 * eps64 * max(N_g,K) * (abs(X_g)' abs(u_g))`, plus each normalized predictor
column's cluster L2 norm times the residual L2 resolution bound, is propagated
through the absolute bread/unit transformation into a coefficient
SE resolution bound. SEs at or below that conservative arithmetic bound remain
null, with no inference for that coefficient. A covariance matrix containing
unresolved entries is not reported. These are numerical guard policies, not
confidence bounds or additional statistical estimators.
Intervals that cannot be represented with a distinct lower/upper endpoint
around their estimate in float64 remain null, with explicit unknown markers.

## Correlated common-effect meta-analysis

`correlated_meta_analysis` requires 2..30 `studies` (`id`, `effect`) and a
symmetric square `covariance` in exactly that study order. Supported
`effect_scale` values are `mean_difference`, `standardized_mean_difference`,
`log_risk_ratio`, `log_odds_ratio`. Effects have magnitude <=1e6; diagonal
variances are in [1e-12,1e12], off-diagonal magnitudes <=1e12. Symmetry and
pairwise covariance bounds are checked exactly before backend use. Positive
definiteness and condition number <=1e10 are checked numerically.

The supplied sampling covariance is treated as fixed/known. Cholesky solves
compute `w = V^-1 1`, normalized weights `w/(1'w)`, common estimate
`(1'V^-1 y)/(1'V^-1 1)` and variance `1/(1'V^-1 1)`. The interval is the normal
interval at `alpha` [.001,.2], default .05. Negative normalized weights can be
valid with correlated estimates; they are not probabilities. Generalized
residual Q uses K-1 degrees of freedom under the declared common-effect normal
model. Its interpretation and nominal interval coverage are unverified.
Effects are centered before whitening so a large common location does not
needlessly degrade residual Q. Unrepresentably narrow confidence intervals
remain unknown while the point estimate and standard error are retained.

This is a common-effect GLS calculation, not an estimated multilevel/random
effects model, REML heterogeneity fit or general robust meta-analysis. Sampling
covariance validity, study comparability, correct effect scales and source
independence assumptions cannot be inferred. No I-squared is inferred from an
independent-study formula. Leave-one-estimate-out results retain the appropriate
covariance submatrix; dropping one estimate need not drop an entire study.

Optional `covariance_scenarios` contains at most five named (`id`, `covariance`)
alternative matrices with unchanged diagonal variances. It evaluates declared
cross-covariance assumptions. An invalid/ill-conditioned scenario remains
unassessed while valid baseline/other results are retained. The baseline itself
must be numerically usable. Underflowed Q probabilities remain unknown.

## Binary missing-outcome bounds and tipping thresholds

`missing_binary_sensitivity` requires `treatment` and `control` objects, each
with integer `events`, `observed`, `missing`. Observed is >=1, missing >=0,
events is in [0,observed], and observed+missing is <=1000000 per arm.
The outcome is a single binary event per participant at a common declared
endpoint. Optional `threshold` in [-1,1] defaults to 0. The direction is strictly
`risk_difference > threshold`, where risk difference is treatment minus control;
event desirability is not inferred.

For T/C totals N and event counts E, all possible binary missing assignments
bound the risk difference by
`E_T/N_T - (E_C+M_C)/N_C` and
`(E_T+M_T)/N_T - E_C/N_C`. Exact rational arithmetic preserves bounds, strict
threshold equality and minimum imputed event counts. Complete-case and extreme
assignment results are reported without imputing a missingness mechanism.

Optional `control_missing_events_grid` supplies up to 100 distinct counts from
0..M_C; default is the distinct sorted values 0, floor(M_C/2), M_C. For each b,
the minimum feasible treatment missing-event count a satisfying the strict
threshold is `max(0, floor(N_T*(threshold+(E_C+b)/N_C)-E_T)+1)`, or null when
unreachable within 0..M_T. This is a bounded analytic frontier, not enumeration
of every missing assignment.

Results are conditional deterministic point-estimate sensitivity, not sampling
intervals, significance tests, multiple imputation, MAR/MNAR identification,
survival analysis or proof of treatment benefit. No missing assignments means
the bounds coincide. Completion returns CALCULATED, never a scientific verdict.
The exact count calculation uses the standard library and needs no backend extra.

## Methods and limits

- [Statsmodels CR1 covariance](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_cluster.html)
- [Cameron: clustered inference, correction and G-1 reference distribution](https://faculty.econ.ucdavis.edu/faculty/cameron/research/slidesrobustsurvey.pdf)
- [metafor: GLS with correlated sampling covariance](https://www.metafor-project.org/doku.php/tips:weights_in_rma.mv_models)
- [Cochrane missing-data methods discussion](https://training.cochrane.org/sites/training.cochrane.org/files/public/uploads/resources/downloadable_resources/Missing%20data%20SMG%20Webinar.pdf)

Numerical operations require the existing SciPy extra and use NumPy/SciPy
float64. Warnings and nonfinite calculations cannot earn a successful numerical
result. Exact input checks and rational sensitivity counts run before optional
imports. Reports record the existing numeric environment and source hashes.
These new kinds remain abstentions in the discrepancy evaluator because no
reported-value agreement check is requested by these calculation contracts.
