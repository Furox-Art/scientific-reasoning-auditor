# Bounded evidence checks

Three dependency-free operations use the existing toolkit interfaces. Results
are English, separate from read-only manuscripts. No network or arbitrary code
execution occurs. The examples are synthetic controls, not real-study findings.

```bash
sra verify-toolkit examples/evidence-checks.json --out reports/evidence
```

All three kinds require `id` and `kind`. Standalone requests supply `text`;
source-bound requests omit it and use the manuscript snapshot. Bound specs must
carry the exact `source_sha256` and `extracted_text_sha256` as described in
`DETERMINISTIC_TOOLKIT.md`. Alternate bound text is rejected. Manuscript and
source text are nonempty and at most 100000 characters per snapshot. Existing
1 MiB spec and 32-check limits apply. Record IDs are distinct ASCII identifiers
starting with a letter, at most 32 characters. Unknown fields are rejected.
The MCP bridge also bounds complete reports to 2 MiB; sufficiently large batches
can be rejected without a partial report. Split such requests explicitly.

## Supplied-source lexical overlap

`source_overlap` accepts 1..8 `sources`, each with `id`, `text` and its UTF-8
`sha256`. Optional `min_tokens` is an integer from 5..20 (default 8). Total text
including the manuscript is at most 200000 characters; each snapshot is at most
20000 tokens. Tokens are Python Unicode `\w+` runs, casefolded for comparison.
Punctuation and whitespace separate tokens. No stemming, Unicode normalization,
quotation/reference exclusion or semantic matching occurs.

For each source, an index maps each fixed-length token window to its earliest
occurrence. Every matching manuscript window contributes to a union token
count. Overlapping windows are counted once per manuscript token in that count;
different sources have separate counts that must not be summed as a unique
total. `matching_windows` counts windows, not distinct passages. Up to 100
examples per source contain original manuscript/source quote previews (at most
240 characters each) and half-open codepoint offsets `start`/`end` for that exact
preview. `window_end` retains the complete matching token window's end;
`quote_truncated` indicates a shortened preview. `examples_truncated` identifies omitted examples. Repeated
source alignments are not exhaustively enumerated. Work is bounded by the token
counts and window length, avoiding all-pairs comparison of repeated text.

The result is CANDIDATES, including zero matches between sufficiently long
snapshots. Any manuscript/source shorter than `min_tokens` yields UNDETERMINED
with the affected source IDs in `unassessed_checks`; other source results remain
available. Each source records `compared` or `insufficient_tokens`.
It is not a plagiarism
or novelty percentage. Common language, quotations and proper attribution need
human review. No unseen literature or paraphrased copying is checked.

## Protocol field comparison

`protocol_consistency` accepts a `protocol` snapshot (`text`, UTF-8 `sha256`)
and 1..100 `fields`. Each field has `id`, `protocol`, `manuscript`. Each mapping
is either null (unavailable) or `{ "value": "...", "quote": "..." }`.
Values and quotes are nonempty strings up to 2000 characters. Each quote must
occur exactly in its corresponding snapshot. The report anchors the first exact
occurrence with half-open codepoint offsets; ambiguous semantic mappings are not
resolved automatically. Values are caller-mapped strings, not extracted facts.

Comparison is case-sensitive literal string equality, without numeric/unit/list
normalization. All supplied mappings equal yields VERIFIED; any difference with
complete mappings yields REFUTED. Any null mapping yields UNDETERMINED while
preserving all proved literal differences. The report lists each comparison,
snapshot identities, `differences` and `unassessed_checks`. These statuses refer
only to the supplied string comparison. Complete field selection, mapping
semantics, authorized amendments, timestamps, ethics approval, authentic registry
records and prospective registration are not verified.

## Checklist evidence record audit

`checklist_evidence` requires `checklist` with `name` (<=200 characters), `version`
(<=100), and 1..100 `items` (`id`, `requirement`, <=2000 characters). The checklist
is caller-supplied; no claim of official completeness or licensed reproduction
is made. The report fingerprints the exact declared checklist using sorted UTF-8
JSON. `assessments` contains 0..100 unique records referencing existing item IDs:

| Status | Required evidence | Interpretation |
| --- | --- | --- |
| `reported` | `quote`, <=2000 characters, present in manuscript | The caller selected a passage. |
| `not_applicable` | `rationale`, <=2000 nonempty characters | The caller declared an exclusion. |
| `unknown` | No additional fields | No assessment supplied. |

Omitted IDs become `unmapped`; unknown and unmapped items are listed in
`unassessed_checks`. Any such gap yields UNDETERMINED; otherwise CANDIDATES.
Counts distinguish recorded statuses. The report retains requirement text,
quoted evidence/offsets or exclusion rationale in checklist order. Quote presence
does not establish relevance or sufficiency. Exclusions, checklist authenticity,
study appropriateness and complete official guideline compliance remain human
review questions; no compliance or quality score is produced.

## Unified coverage

Source-bound `sra review --toolkit-spec` links actual results to novelty/integrity,
registration/protocol and reporting-guideline rows. Overlap and checklist records
remain screening; literal protocol comparisons are bounded structured checks.
Missing mappings/records remain partial. Every criterion-level scientific verdict
stays NOT_ASSESSED. Code reexecution, data/image authenticity, ethics-document
authentication, exhaustive originality and full scientific adequacy remain open.
