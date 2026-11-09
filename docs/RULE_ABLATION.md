# Rule ablation (synthetic)

A rule that never fires and a rule that fires on everything look the same when a
test only asserts "this finding appeared". This page measures both, on a corpus
whose planted findings are declared up front.

**These numbers are not accuracy.** The corpus is synthetic: it shows whether a
rule is wired and how widely it fires. Precision and recall on real manuscripts
need independent expert labels, which this project does not have.

Reproduce with:

```
python tools/make_ablation_corpus.py
python tools/run_rule_ablation.py
```

`tests/test_rule_ablation.py` runs the same corpus and fails when the committed
report drifts, when a planted rule stops firing, or when the set of rules the
corpus cannot plant changes.

## Result

- cases: 17
- rules: 21
- exercised by the corpus: 21
- planted but missed: none
- never fired: none
- fired where nothing was planted: reasoning.conclusion_without_lexical_candidate, statistics.confidence_interval_p_conflict

## What it says

1. `reasoning.directional_conflicts_truncated` is exercised by a case with six
   independent topics whose results and conclusions point in opposite
   directions: the audit finds more conflicts than it prints and says so. The
   rule was previously the one code with no measured behaviour; rewriting the
   corpus fixed that, so nothing is retired.
2. `reasoning.conclusion_without_lexical_candidate` fires on several fixtures that
   plant nothing. The rule matches words, and a conclusion that paraphrases its
   results has no shared vocabulary: this is the false-positive class its
   inventory row describes, now measured rather than assumed.
3. `statistics.confidence_interval_p_conflict` also fires on the repeated
   rate-ratio case, because one of the two printed intervals contains the null
   while the p-value stays small. Two rules describing one defect is expected;
   the duplicate is worth knowing when reading a report.

## Per-rule table

`tp` = planted and fired, `fp` = fired with nothing planted, `fn` = planted and
silent.

| Rule | tp | fp | fn |
|---|---|---|---|
| `language.absolute_claim` | 1 | 0 | 0 |
| `reasoning.association_and_causal_claims` | 1 | 0 | 0 |
| `reasoning.causal_claim_observational_design` | 1 | 0 | 0 |
| `reasoning.conclusion_without_lexical_candidate` | 1 | 5 | 0 |
| `reasoning.correlation_causation_review` | 1 | 0 | 0 |
| `reasoning.directional_conflicts_truncated` | 0 | 0 | 0 |
| `reasoning.directional_contradiction` | 1 | 0 | 0 |
| `reasoning.mixed_design_causal_review` | 1 | 0 | 0 |
| `statistics.confidence_interval_p_conflict` | 1 | 1 | 0 |
| `statistics.design_test_mismatch` | 1 | 0 | 0 |
| `statistics.group_count_test_mismatch` | 1 | 0 | 0 |
| `statistics.impossible_dispersion` | 2 | 0 | 0 |
| `statistics.impossible_p_value` | 2 | 0 | 0 |
| `statistics.mean_outside_confidence_interval` | 1 | 0 | 0 |
| `statistics.multiplicity_unaddressed` | 1 | 0 | 0 |
| `statistics.repeated_rate_ratio_ci_conflict` | 1 | 0 | 0 |
| `structure.conclusion_missing` | 1 | 0 | 0 |
| `structure.limitations_missing` | 1 | 0 | 0 |
| `structure.methods_missing` | 1 | 0 | 0 |
| `structure.references_missing` | 1 | 0 | 0 |
| `structure.results_missing` | 1 | 0 | 0 |
