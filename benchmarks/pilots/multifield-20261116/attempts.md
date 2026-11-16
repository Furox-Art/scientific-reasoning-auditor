# Execution attempts

## Attempt 1 — preserved initial result

Protocol commit: 00ba827. Complete frame/draw commit: 317022e.
Pre-result normalizer/replay corrections and source capture: fad947c.
Output: `first-run/`. All 12 sources were available and all requested text
screening modules completed. All 12 repeat comparisons failed: the output was
placed inside the repository's provenance inventory, so saving the first report
changed `source_code_sha256` and `environment_fingerprint` before the second.
This is an audit-harness failure, not 12 scientific disagreements or invalid
papers. Both original raw reports and the full original summary remain intact.
The original summary's completed=0 reflects its repeat-mismatch execution
status; it must not be read as zero completed manuscript screening modules.

## Correction before attempt 2

No paper, selection, original source, criterion, engine algorithm or scientific
verdict was changed. The offline runner now refuses an output directory within
its source repository. The next complete run writes to a fresh external
directory, so output creation cannot change the source tree being fingerprinted.
After the run is complete, a copy may be committed as evidence. Repository,
platform and dependency provenance are retained in semantic comparison, so
repeat equality applies to that fixed environment only.

The runner now reports requested module completion separately from repeat
comparison completion. Eleven focused tests include a regression asserting
that an in-repository output is rejected before auditing.

## Attempt 2

Pending execution at the time this correction was committed. Its actual summary
will be archived as `recorded-run/`; this entry is not a predicted success.
The original first run must remain available alongside the corrected result.
