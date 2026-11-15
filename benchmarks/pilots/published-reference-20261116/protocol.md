# Published-reference comparison: analysis specification 1.0

Prepared on 2026-11-16 after inspecting the public data/codebook and before the
first SRA predictions. This is a retrospective development comparison, not a
preregistered or held-out multi-field validation. Do not overwrite this file
after execution; record deviations separately and retain its SHA-256.

## Sources and scope

- Comparison workbook: https://osf.io/axfbn/ (version 1),
  SHA-256 `74a91b05cd738a2cccccfe7ec6dfb8aa5ed46b248b3d1a7d76bd67513bdf6f80`.
- Codebook: https://osf.io/xqce2/ (version 1),
  SHA-256 `b2d88b9bc4edf06e4d9228ba358b4e295f5e4f2824d26c6c7720e32e4d7f0c36`.
- Public OSF component: https://osf.io/yu5wj/; source metadata declares
  CC BY 4.0, https://creativecommons.org/licenses/by/4.0/.
- Original manual coding: Wicherts, Bakker and Molenaar (2011),
  DOI 10.1371/journal.pone.0026828. Comparison/codebook curated for Nuijten and
  colleagues' statcheck validation work (2016/2017),
  DOI 10.3758/s13428-015-0664-2 and DOI 10.31234/osf.io/tcxaj.
- Follow the source-study exclusion of the author key containing `Stapel`, as
  specified in `01CleanManuallyCodedComparisonData.R`,
  https://osf.io/zcysv/, SHA-256
  `4b3a414143422da38c995cc77c88bed18025c33165b7a7b63677aa600bf7115e`.
  This repeats a documented cohort rule, not a new finding about authors.

The workbook contains 1211 comparison rows: 1148 with manual labels and 63
without. The source-study exclusion removes 28 manually labeled rows, leaving
1120 rows in 48 source author-key groups. These are selected significant
reported results from psychology, not a representative sample of all tests or
scientific fields. Full original papers are not supplied here or claimed to
have been read. The data/codebook attribution is retained; no source endorsement
or independent authentication of labels, joins or reviewer identity is claimed.

## Freeze the engine and prevent label leakage

Evaluate the published Python **0.9.0** wheel, SHA-256
`9aaab314b17f4ae311f842f89409f29430451312df493ba1c59510df21cb9e93`.
Compare every installed SRA Python module and typing marker with that wheel
before execution. Record Python/platform/numerical dependency versions, producer
source SHA-256, specification SHA-256 and all source hashes. Do not change the
engine or tune tolerances after inspecting comparison results.

Prediction inputs come **only from `statRaw`**, preserving the printed decimal
precision. Do not use `plosValue`, `plosComputed`, manual comments, source error
flags or automatic statcheck decisions to construct checks. The codebook states
that some manual numeric values were adjusted after rounding inspection; using
them as predictors could leak adjudication into the calculation.

Use complete literal t/F/chi-square expressions with equality test statistics,
exact positive integer degrees of freedom and p-value relations =, < or >.
Normalize Unicode minus and whitespace only. Unsupported/missing symbols,
fractional degrees of freedom, inexact statistic comparisons, unsupported p
relations, malformed inputs and missing raw expressions abstain. Never infer
missing test identifiers from manual labels or other spreadsheet columns.
The existing 0.9.0 two-sided t and upper-tail F/chi-square rounding-aware check
runs unchanged. All nondecisive/backend-failure statuses abstain.

## Reference labels and accounting

Use `plosErrorLogical` exactly as the codebook defines it: 1 = error,
0 = no_error. Verify consistency with the complementary `plosError` column.
Missing manual labels are excluded from binary metrics and separately counted;
invalid or contradictory label encodings stop the run. Retain all workbook
rows and the source-study exclusions in the output. No human IDs or decisions
are created. Historical manual coding is not a new two-reviewer exercise.

Report TP/FP/TN/FN, abstentions by reference label, missing/excluded records,
input/decision coverage, selective precision/recall/specificity/accuracy and
reference-frame recall counting abstained reference errors. Retain exact
numerators/denominators and null undefined ratios. Provide source author-key
group strata and whole-group omission sensitivity, without inferential intervals.

Do not call source-string availability an SRA text-extraction measurement:
the strings were supplied by another extractor. Do not call reference agreement
whole-paper scientific accuracy. Contextual corrections and one-tailed tests
may explain disagreement; source papers/joins are not independently re-adjudicated.
Keep the first frozen result even if later analysis discovers adapter or engine
issues. Genuine new human review and representative multi-field validation remain
outstanding.
