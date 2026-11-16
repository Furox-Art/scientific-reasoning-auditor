# Prospective finite-frame multi-field execution audit

Protocol v1, frozen before frame capture, article selection and auditor outputs.
This is a local prospective protocol, not an externally registered study.
Engine: published SRA 0.10.0, repository baseline 73717b13af0cde3b18c8840c60e2d02ec439a8bb.
No tuning to the selected papers is allowed in this first run.

## Target, sampling and estimands

The target population is the PLOS Search API snapshot of PLOS ONE Research
Articles published 2024-01-01 through 2024-01-31 UTC, doc_type full. The DOI-
ascending complete response (all pages, numFound reconciled, no duplicate IDs)
will be archived. A one-record availability probe found 1022 records; it did
not inspect any auditor result. Index omissions and later metadata changes are
not repaired by this design. This single publisher/month cannot represent all
journals, languages, fields, years or scientific study designs.

Assign each record to the FIRST matching subject-prefix stratum in this order:
1. physics: /Physical sciences/Physics
2. chemistry: /Physical sciences/Chemistry
3. computing: /Computer and information sciences
4. animal: /Biology and life sciences/Zoology
5. social-science: /Social sciences
6. clinical: /Medicine and health sciences
A prefix matches only the complete path or its slash-delimited descendants.
Retain unmatched records and all original subject tags in the frame; unmatched
records are outside the six-stratum target. Priority makes strata disjoint and
must not be interpreted as an authoritative discipline classification. Broad
taxonomy membership does not prove that a profile or individual rule applies
(e.g. zoology is not necessarily an animal intervention, medicine not a trial).

Publish a cryptographically generated seed now, before capturing the frame:
85908ff2a73ec626b0b63caa6adf0199bc94be9bd5c89bd79f5fed6872471590

Within each stratum sort by SHA-256(UTF-8(seed + "\n" + stratum + "\n" + DOI)),
then by DOI to break ties. Select the first min(2, N_h) records: a reproducible
pseudorandom priority sample, up to 12 papers. Equal allocation deliberately
overrepresents smaller strata. Report N_h, n_h and n_h/N_h. Do not report an
unweighted pooled population prevalence or claim a formal sampling interval.
No outcome-based eligibility and no replacement for inaccessible full text,
license failure, extraction failure, unsupported designs, absent numerical
triplets or unfavourable results. Record every selected paper and failure.
Preserve the complete ranked frame and exact raw response hashes. A source-
availability failure is an observed denominator, never a silent exclusion.
Any prior development exposure is reported, not resolved by reselection.
This is a prospective execution sample, not a held-out labelled accuracy set.

## Source handling and execution

Retrieve original publisher JATS XML and article-specific permission records
for the selected papers. Store exact XML bytes, source URL, SHA-256, DOI, title,
authors, dates and explicit license. Redistribute only under a confirmed
Creative Commons Attribution/CC0 permission; otherwise retain the failure.
Normalize title/abstract, all body sections (including tables/captions) and
back matter to Markdown. Archive originals separately and describe flattened
equations, linked figures and supplements as limits. Original articles are
read-only. No external model receives their contents.

Run unified offline review on each normalized full-text snapshot with only its
assigned profile, study_type unknown, style_language none, prepare_inputs true.
Do not infer experimental design, test sidedness, exact df or code inputs.
Record complete reports, all source/text hashes, engine and producer source
hashes, dependency versions, profile rule states, preparation candidates,
module failures and the complete 43-criterion execution matrix. All scientific
criterion verdicts must remain NOT_ASSESSED. Repeat with the same source/
environment and compare semantic output (exclude source path only, not findings).

Primary endpoints: source/full-text availability; requested module completion;
profile candidate retrieval counts; criteria execution/applicability coverage;
explicit unassessed/unsupported work and repeat-run agreement.
None is a scientific quality score or error-detection sensitivity/specificity.
No model-generated label is a human label. Gold accuracy, true errors,
precision and recall are null/not estimated until real independent reference
labels exist. A negative keyword search is not evidence an article omits an item.

## Reading, review and deviations

Make the complete normalized texts and original licensed XML available for
review. Machine ingestion of every text is not a complete human scientific
reading; record the actual manual reading/figure/supplement status separately.
Do not claim complete paper review, data replication, expert validation or
that the papers have no errors. Collect blank source-bound human forms only;
do not fill reviewer identities, labels or adjudications.
Do not contact external people without separate explicit recipient authorization.
Preserve this protocol and the first run even if they expose implementation
defects. Record corrections as dated deviations/new versions, not replacements.
All final limitations and failures must be reported alongside successes.
