# Published statistical-reference comparison

Retrospective, conditional reference agreement. Not whole-paper scientific accuracy.

Execution: complete
Workbook rows: 1211
Manually labeled retained rows: 1120
Source author-key groups: 48
Exclusions: {"no_manual_reference": 63, "source_study_exclusion": 28}

Confusion: {"fn": 0, "fp": 20, "tn": 618, "tp": 34}
Abstentions: {"error": 15, "no_error": 433}

| Metric | Numerator | Denominator | Value |
| --- | --- | --- | --- |
| decision_coverage | 672 | 1120 | 0.6 |
| selective_accuracy | 652 | 672 | 0.970238 |
| selective_risk | 20 | 672 | 0.0297619 |
| decided_precision | 34 | 54 | 0.62963 |
| decided_recall | 34 | 34 | 1 |
| decided_specificity | 618 | 638 | 0.968652 |
| decided_false_positive_rate | 20 | 638 | 0.031348 |
| false_alarms_per_labeled_negative | 20 | 1071 | 0.0186741 |
| reference_frame_recall | 34 | 49 | 0.693878 |

## Abstention reasons

- engine_undetermined: 12
- raw_expression_missing: 408
- unsupported_literal_expression: 28

## Source and reproducibility

Wicherts, Bakker & Molenaar (2011); comparison/codebook curated for Nuijten et al. statcheck validation (2016/2017).

CC BY 4.0, as declared by https://osf.io/yu5wj/; https://creativecommons.org/licenses/by/4.0/

- https://osf.io/axfbn/
- https://osf.io/xqce2/
- https://osf.io/zcysv/

Engine: 0.9.0; wheel SHA-256: 9aaab314b17f4ae311f842f89409f29430451312df493ba1c59510df21cb9e93
Specification SHA-256: db7ebe9e11c4c7e40423f6f694f1c878f603db9b2f881fca117c349a08316808
Parser clarification SHA-256: ceba6273d680d2fd01d00b6d6d3786343a2fb3dc1d04c04920a7fa676c87daef
Producer SHA-256: 4e9a4b63a1106c0a01024c0f6b3e9854156e8fdf9c62d5a398bbceef67d3263c
Report SHA-256: c7d40750a24cb44cf7b5a11414f76efc7260846ae812ff48020d835d8d27d30f

## Limits

- Selected significant psychology results; no representative multi-field or held-out validation.
- Inputs are third-party-extracted strings, not SRA paper extraction. Missing strings abstain.
- Predictions use only statRaw; manually adjusted numbers, comments and other software labels are not inputs.
- The unchanged 0.9.0 method assumes two-sided t or upper-tail F/chi-square with exact integer df.
- Historical labels/joins and original papers are not independently re-adjudicated or authenticated.
- Contextual corrections or one-tailed tests may explain disagreement; no whole-paper truth or author misconduct verdict follows.
- Case counts are correlated within source author-key groups. Omission sensitivity is not a confidence interval.
- Source byte checks support reproducibility, not independent scientific expert validation.

Complete case results, group strata and whole-group omissions are retained in the companion JSON.
