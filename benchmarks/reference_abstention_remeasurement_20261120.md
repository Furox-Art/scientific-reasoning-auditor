# Fail-closed abstention remeasurement on the frozen published-reference cohort

**Retrospective, in-sample remeasurement — NOT a new frozen baseline and NOT prospective validation.**

Date: 2026-11-20. Engine: 0.11.0 + unreleased abstention refinement.

Cohort: `benchmarks/pilots/published-reference-20261116/first-run.json` (SHA-256 `e99491bbc0817074b9237fdb129eb192aca49a962bcdff78b03274056c0a92a0`), 1120 retained psychology results, 48 author-key groups. The frozen 0.9.0 first run is preserved unchanged.

## Rule change

A fail-closed **abstention** (not a tolerance loosening): when the *default* undeclared two-sided t/z tail or uncorrected F df refutes the printed p, but the p is also consistent with a plausible undeclared analysis choice, the check returns UNDETERMINED instead of a reporting error.

- **One-tailed (t/z):** the printed p is not refuted by a one-tailed test in the statistic direction.

- **Sphericity df correction (F, numerator df >= 2):** the reported p is above the computed interval and reachable at the Greenhouse-Geisser epsilon lower bound (df -> (1, df2/df1)).

Never fires for caller-declared tails/df, never overturns VERIFIED; declaring the tail or supplying corrected df resolves the abstention.

## Before / after (same cohort, same gold labels)

| Metric | Before | After |
| --- | --- | --- |
| Confusion (TP/FP/FN/TN) | 34/20/0/618 | 27/1/0/618 |
| Abstentions (error / no_error) | 15 / 433 | 22 / 452 |
| decision_coverage | 672/1120 = 0.6000 | 646/1120 = 0.5768 |
| selective_risk | 20/672 = 0.0298 | 1/646 = 0.0015 |
| decided_precision | 34/54 = 0.6296 | 27/28 = 0.9643 |
| decided_false_positive_rate | 20/638 = 0.0313 | 1/619 = 0.0016 |
| reference_frame_recall | 34/49 = 0.6939 | 27/49 = 0.5510 |

## Trade-off (documented recall cost)

False alarms 20->1 and decided precision 63.0%->96.4%, bought with reference-frame recall 34/49->27/49. Seven genuine reference errors move to transparent abstention (not silent false negatives; decided FN stays 0).

The removed false alarms and the lost true positives share the same numeric signature once the tail/correction is undeclared; no rule on the input string alone can separate them. The abstention is the honest fail-closed response to an undeclared analysis choice.

**Fixed false alarms (19):** row_262, row_263, row_266, row_394, row_395, row_396, row_397, row_398, row_399, row_400, row_409, row_418, row_436, row_437, row_703, row_711, row_712, row_713, row_714.

**Lost true positives (7), now transparent abstentions:** row_65, row_98, row_526, row_540, row_656, row_811, row_813.

**Remaining false alarm (1):** row_548 `F(1, 53) = 2.91, p <.05` (F numerator df=1, downward discrepancy; no sphericity correction applies).

## Limitations

- Retrospective, in-sample tuning on the SAME psychology-only cohort used to design the rule; the after numbers are not a held-out or prospective estimate.
- Selected significant psychology results; not representative multi-field or whole-paper accuracy.
- Inputs are third-party (statcheck) strings, not SRA text extraction; missing strings abstain.
- Historical labels/joins and original papers are not independently re-adjudicated or authenticated.
- One-tailed and sphericity-correction explanations are plausible hypotheses, not confirmed causes for any specific row.
- No new human reviews collected; prospective blinded human validation remains PENDING and cannot be performed by this software.
- Case counts are correlated within source author-key groups; no inferential confidence intervals are claimed.

Prospective blinded human validation: **PENDING**. No new human labels; no prospective or multi-field accuracy claim.

