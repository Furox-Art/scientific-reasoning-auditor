# Research-method inspection

Seven additional structured checks run through the existing Python, CLI, Node
and MCP toolkit interfaces. Reports remain English and separate from read-only
manuscripts. These are unreleased source features; no UI, merge or package
publication is included.

```bash
py -3.15 -m venv .venv
.venv/Scripts/python -m pip install -e ".[toolkit,research]"
.venv/Scripts/sra verify-toolkit examples/research-methods.json --out reports/research
```

The example is synthetic, including a supplied bias concern, an ML preprocessing
violation and a synthetic correction record. It is not a real study assessment.
All kinds also work in source-bound unified review via `--toolkit-spec`.
Discover supported kinds with `sra capabilities`. The base install is still
dependency-free; missing optional backends remain explicit.

## Causal graph checking

`causal_graph` requires distinct `nodes` (2..10), directed `edges` (<=32),
`treatment`, `outcome`, `observed`, and `adjustment`. Graphs must be acyclic.
All adjustment variables must be observed and exclude treatment/outcome.
NetworkX checks the backdoor criterion: no treatment descendants in the selected
set and d-separation after removing outgoing treatment edges. It also enumerates
smallest observed backdoor sets with a bounded search (<=256 subsets).

VERIFIED/REFUTED refers only to this selected graph criterion. The actual
causal graph, measurement assumptions and absence of hidden confounders are not
confirmed; no causal effect is estimated. Frontdoor/instrumental-variable and
other identification strategies are not assessed, so no backdoor set does not
mean every causal identification method fails. Optional `sensitivity_edges`
add declared edges in a second acyclic scenario and expose whether the same
adjustment remains valid. This is graph sensitivity, not data-driven validation.

## Evidence-linked bias review

`bias_assessment.domains` contains exactly `randomization`,
`allocation_concealment`, `blinding`, `missing_outcomes`, `selective_reporting`.
Each row has `judgment`: `concern`, `no_concern` or `unknown`, and `source_quote`
(null is allowed only for unknown). Optional `note` explains the caller's view.
Quotes/notes are <=2000 characters; bound quotes must occur in the manuscript.

All judgments are explicitly caller-supplied. The report lists concerns and
unknowns as CANDIDATES, never automatically certifies low bias or expert review.
This is an independent evidence worksheet, not a reproduction or conformance
claim for the licensed RoB2 instrument.

## Prospective power and sample size

`power_analysis` supports `design`: `independent_t` or `paired_t`; `mode`:
`calculate` (integer `nobs`) or `sample_size` (`target_power`). Both need positive
standardized `effect_size` <10 and `alpha` in (0,.5). Independent samples may
declare `ratio` in [.01,100]; paired analysis requires ratio 1. `nobs` represents
group 1 observations or paired observations. Results use two-sided t-test power.
For paired tests the effect must be standardized by the SD of paired differences.

Statsmodels computes power/continuous sample size. Group sizes are rounded up
and recomputed with the actual integer allocation (at least two/group), with a
one-million/group ceiling. Target power must exceed alpha and be <.9999. Failure
to solve or achieve the target is explicit. Optional `reported_power` is checked
with absolute tolerance 1e-6. This is prospective analysis on supplied design
assumptions, not a post-hoc p-value restatement or study-design certification.

## Meta-analysis

`meta_analysis` needs `model` fixed/random, common `effect_scale`
(`mean_difference`, `standardized_mean_difference`, `log_risk_ratio`,
`log_odds_ratio`) and 2..50 `studies` with unique IDs, effect and variance.
Variances must be in [1e-12,1e12], effects within +/-1e6. Independent comparable
estimands and correct log scales are caller declarations, not inferred facts.

Random effects use `tau_method`: `paule_mandel` (default, Statsmodels with
convergence checks) or nonnegative-truncated `dersimonian_laird`. Results include
pooled estimates, normal-approximation CIs (`alpha` .001.. .2, default .05), Q,
I-squared, tau-squared and leave-one-out point estimates. One remaining study in
a leave-one-out calculation has tau=0; no study-level validity follows.

Optional `asymmetry: true` requests an Egger intercept diagnostic, available only
with >=10 studies and differing precisions. Small-study asymmetry is not proof
of publication bias. Designs with condition number >1e8 and zero/nonfinite tail
probabilities abstain explicitly. An unavailable/unstable requested diagnostic
marks the check UNDETERMINED while retaining valid pooled results.
HKSJ/robust intervals, correlated/multilevel effects and
automated study inclusion decisions are not provided. Numerical warnings or
nonfinite results cannot be presented as successful numerical agreement.

## Bayesian chain diagnostics

`bayesian_diagnostics` accepts 2..8 equal-length `chains`, 20..5000 draws/chain,
<=20000 draws total; decimal values are bounded to +/-1e100. It computes
rank-normalized R-hat and bulk/tail ESS (tail probabilities .05/.95). Thresholds
`rhat_max` (default 1.01, range 1..2) and `ess_min` (default 400, range 1..20000)
produce diagnostic flags; they never prove convergence, model adequacy or a
correct posterior. Constant/nonfinite problematic chains abstain explicitly.
No model fitting, sampling or random-seed selection is performed.

## ML experiment manifest inspection

`ml_validation` accepts 2..5000 unique `samples` (`id`, optional `group` and
numeric `time` in a common declared unit), and nonempty `splits.train/test`
(optional validation), all referring to declared sample IDs. It checks overlap.
Optional `preprocessing_fit_ids` describe train-only preprocessing used during
model selection; IDs outside train are flagged. This is not a final-model fit
protocol where fitting on train+validation after selection may be legitimate.

`group_exclusive: true` checks shared groups between partitions.
`temporal: true` checks strictly increasing partition ranges in train,
validation, test order. Timestamps must share a meaning/unit; missing requested
group/time metadata stays unassessed. Reports are CANDIDATES with observed
violations, never a proof that actual preprocessing code is leak-free or that
generalization is valid. Feature/label content, transductive evaluation and
arbitrary code execution are not inspected.

## Publication update metadata

`publication_status` works offline on `doi` and a supplied Crossref `message`.
The message DOI must match. Bounded `updated-by` and `update-to` lists (<=64 each)
must have valid related DOIs and explicit update types. Duplicate events are
deduplicated, and the supplied snapshot is hashed with decimal-preserving sorted
JSON (numbers remain distinct from strings; at most 64 nesting levels).
Known incoming full/partial retraction,
withdrawal, removal, concern and correction types are distinguished; outgoing
notice links do not mean the notice itself was retracted. Unknown incoming types
remain generic updates. Bad collections fail instead of looking clear.

The existing opt-in `doi-check --online` and unified `review --online` now include
Crossref update status in the same response, without an extra registry request.
Offline remains default. DataCite fallback does not add a Crossref assessment.
NO_UPDATES_REPORTED means only no links in these fields: completeness and
independent authenticity are unproven. Retraction/correction metadata is an
editorial observation, not a misconduct allegation or a scientific truth verdict.

## Runtime and compatibility

Python 3.11 or newer is required. The research-method suite was tested locally
in a clean Python 3.15.2 environment; CI also covers Python 3.11 and 3.12.
On Windows, `py -3.15` explicitly selects the upgraded runtime when installed.

Modern runtime backends: NetworkX 3.7, Statsmodels 0.15.0, ArviZ Stats 1.3.3.
Python 3.11 retains NetworkX 3.6.1 and ArviZ 0.22.0 via conditional extras.
DoWhy 0.14 excludes Python >=3.14 and restricts SciPy, so its constraints were
not bypassed; graph checks use NetworkX directly. Toolkit reports now record
Python/platform and installed numerical dependency versions, plus existing
input/report hashes. Algorithms are deterministic for fixed inputs and their
recorded environment; numeric warnings/limits remain explicit partial results.

## Primary method sources

- [NetworkX d-separation](https://networkx.org/documentation/stable/reference/algorithms/d_separation.html)
- [Cochrane risk-of-bias methodology](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-08)
- [Statsmodels power](https://www.statsmodels.org/stable/stats.html)
- [Statsmodels meta-analysis](https://www.statsmodels.org/stable/generated/statsmodels.stats.meta_analysis.combine_effects.html)
- [ArviZ Stats array interface](https://python.arviz.org/projects/stats/en/latest/array_stats_only.html)
- [Scikit-learn leakage pitfalls](https://scikit-learn.org/stable/common_pitfalls)
- [Crossref versioning and updates](https://www.crossref.org/documentation/principles-practices/best-practices/versioning/)
