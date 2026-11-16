# Statistical-context numerical controls

Distribution-table and synthetic software controls; no whole-paper or human-review validation.

Comparison: MATCHED
Expectations met: 32 / 32
Actual statuses: {"REFUTED": 2, "UNDETERMINED": 6, "VERIFIED": 24}

## Complete cases

| Case | Origin | Expected | Actual |
| --- | --- | --- | --- |
| t_1_greater | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| t_1_less | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| t_1_two_sided | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| t_2_greater | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| t_2_less | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| t_2_two_sided | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| t_3_greater | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| t_3_less | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| t_3_two_sided | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| z_1_greater | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| z_1_less | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| z_1_two_sided | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| z_2_greater | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| z_2_less | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| z_2_two_sided | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| z_3_greater | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| z_3_less | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| z_3_two_sided | NIST table with declared symmetry transformation | VERIFIED | VERIFIED |
| F_1 | NIST upper-tail table | VERIFIED | VERIFIED |
| F_2 | NIST upper-tail table | VERIFIED | VERIFIED |
| F_3 | NIST upper-tail table | VERIFIED | VERIFIED |
| chi2_1 | NIST upper-tail table | VERIFIED | VERIFIED |
| chi2_2 | NIST upper-tail table | VERIFIED | VERIFIED |
| chi2_3 | NIST upper-tail table | VERIFIED | VERIFIED |
| unknown_t | Synthetic unknown-direction control | UNDETERMINED | UNDETERMINED |
| unknown_z | Synthetic unknown-direction control | UNDETERMINED | UNDETERMINED |
| unknown_F | Synthetic unknown-direction control | UNDETERMINED | UNDETERMINED |
| unknown_chi2 | Synthetic unknown-direction control | UNDETERMINED | UNDETERMINED |
| df_t | Synthetic unresolved df-precision control | UNDETERMINED | UNDETERMINED |
| df_F | Synthetic unresolved df-precision control | UNDETERMINED | UNDETERMINED |
| wrong_direction_t | Synthetic intentionally wrong direction/p pair | REFUTED | REFUTED |
| wrong_direction_z | Synthetic intentionally wrong direction/p pair | REFUTED | REFUTED |

## Reproducibility

Engine: 0.10.0
Fixture SHA-256: 8f33fe6b94df7cd1b57b82bc1655a5d88ae844b705711050d25b8d2da74907e6
Protocol SHA-256: 3a6d7bff9091872c162ff010a15a070782ad547af35e5fd1c1b509b27dd77096
Precision clarification SHA-256: 2b7af9f801caf92bf9831e3894f6e17f8a9df0b97ecf49d50b8df3c2da486068
Producer SHA-256: 5385e34d30aac40af95ab95067a270bafcf10de6aa531888f07bb13864474303
Runtime source SHA-256: 8f474a0bc36091139bf85d7531e13ba58674a734c9512e769a73c50c5bb87b3b
Report SHA-256: 1120cd52e91c05721f0f0d3635fb09618418d97d34df296f63b7836927daaee8

- https://www.itl.nist.gov/div898/handbook/eda/section3/eda3671.htm
- https://www.itl.nist.gov/div898/handbook/eda/section3/eda3672.htm
- https://www.itl.nist.gov/div898/handbook/eda/section3/eda3673.htm
- https://www.itl.nist.gov/div898/handbook/eda/section3/eda3674.htm

## Limits

- 24 NIST-derived numerical cases and 8 separately marked synthetic controls.
- Source selection was frozen before implementation; these are software controls, not a held-out paper cohort.
- Expected abstentions are retained. Matched controls do not estimate scientific precision/recall.
- Integer-df NIST tables do not validate all fractional-df calculations; independent analytic unit controls are separate.
- Tail, exact df and correction suitability remain caller declarations.
- Df not exactly representable by the float backend abstain; backend probability error bounds are not formally proven.
- No new human labels, full-paper assessment or independent expert validation.
- The published 0.9.0 historical first result is unchanged and not rescored.
