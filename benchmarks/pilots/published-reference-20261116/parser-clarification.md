# Source-format clarification before first predictions

2026-11-16. The original specification remains unchanged. A read-only code
review inspected the actual pinned workbook before any SRA reference predictions
and found that `plosErrorLogical` is a cached spreadsheet formula derived from
the literal manual `plosError` column. Other unused columns contain formulas and
spreadsheet error values. This is a source-format clarification, not a change
of labels, cohort, prediction inputs, numerical settings or performance targets.

Read the historical cached logical values, never execute or recalculate Excel
formulas, and verify the complement against the literal manual label. Require
literal author keys, `statRaw` predictors and `plosError` manual source values.
Reject formulas or error cells in those fields and reject error cells in the
logical labels. Ignore unused derived/manual-number columns entirely. The
reference consists of historical manual coding, not two independent human
reviewers created by this workflow.

Both specification and clarification hashes are recorded in each result.
The JSON metric is named `reference_frame_recall`; it does not measure SRA
paper-text extraction or whole-paper end-to-end performance.
