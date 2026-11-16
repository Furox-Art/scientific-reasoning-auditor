# Frozen statistical-context reference protocol

Freeze this specification and cases before running the new implementation.
Purpose: test conditional distribution-table arithmetic and abstention behavior,
not whole-paper accuracy, independent human review or representative field coverage.

## Fixed selection

Use three printed upper-tail critical values from each of four NIST Engineering
Statistics Handbook tables: t (df 1, 10, 20; alpha .05), standard normal
(alpha .05, .025, .005), F (df 1/10, 2/10, 5/10; alpha .05), and chi-square
(df 1, 2, 10; alpha .05). Retain their printed three decimal places.
For symmetric t/z, derive lower-tail negative and two-sided positive cases using
symmetry; use the table's alpha or twice alpha, printed to three p-value decimals.
This gives 24 reference cases. No backend-produced quantiles select the inputs.

Add eight separately marked synthetic controls: four unknown directions, two
unresolved/rounded fractional-df declarations, and two intentionally wrong
direction/p-value pairs. These are not historical errors or fabricated humans.
Expected outcomes are fixed in cases.json and never enter the numerical check.

## Input and decision rules

All decisions are conditional on caller-supplied central reference distribution,
signed statistic, tail and exact degrees of freedom. Existing integer-df inputs
retain their default conventions. t/z allow two-sided, greater, less or unknown;
F/chi-square allow greater or unknown. Unknown direction abstains. Positive df
within [1e-6, 1e6] may be decimal strings; fractional df require an explicit exact
precision declaration to be calculated. Unknown/rounded df abstain because df
rounding intervals are not implemented. No correction method or test direction
is inferred from manuscript prose or historical source notes.

Preserve statistic/p rounding intervals and numerical underflow/warning guards.
For signed one-sided t/z, use SF for greater and CDF for less at the appropriate
interval endpoints. Two-sided t/z use the absolute-statistic range, including
zero when crossed. Invalid tail/distribution combinations fail preflight.

## Reporting and limits

Report all 32 cases, origin, declared assumptions, actual/expected statuses,
fixture/producer/source hashes and numerical environment. Do not drop a failed
or abstaining case, tune inputs after outcomes or headline a general accuracy
percentage. Record any source transcription correction as a separate version.
The old published-reference 0.9.0 results remain unchanged and are not rescored.
Fractional-df behavior also needs independent analytic/reference unit controls;
the selected NIST tables themselves contain integer df only.

New independent human evaluation and representative multi-field paper validation
remain outstanding. Software cannot manufacture those decisions or identities.

## Sources

- https://www.itl.nist.gov/div898/handbook/eda/section3/eda3671.htm
- https://www.itl.nist.gov/div898/handbook/eda/section3/eda3672.htm
- https://www.itl.nist.gov/div898/handbook/eda/section3/eda3673.htm
- https://www.itl.nist.gov/div898/handbook/eda/section3/eda3674.htm

Source consultation: 2026-11-16. Values are transcribed numerical facts;
original source pages are not bundled. No NIST endorsement is implied.
