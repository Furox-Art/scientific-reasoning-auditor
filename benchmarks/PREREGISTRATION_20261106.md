# Preregistered pilot: blinded expert adjudication of two finding codes

**Status: FROZEN before any expert label is collected (2026-11-06).**
No reviewer has seen the corpus or produced a label for this study.
This document fixes the corpus, codes, label rules, reviewers, adjudication
procedure and analysis before outcomes are known. Deviations must be recorded
in section 11 and reported with the results.

This is a **pilot**. It estimates agreement between two document-level finding
codes and blinded expert labels on 12 real PMC papers. It is not a
publication-grade estimate of scientific validity, and it cannot certify the
tool or its reviewers.

## 1. Objective

For each of two predeclared finding codes, estimate document-level
precision, recall and specificity against independently adjudicated expert
labels, with Wilson 95% confidence intervals, and report inter-reviewer
agreement. Null denominators are reported as `null`, never as zero.

## 2. Frozen inputs

| Item | Value |
| --- | --- |
| Frozen benchmark | `benchmarks/pmc_smoke_20261105.json` |
| Benchmark SHA-256 | `df0f6e40ddecfc6eada1530698e68d42ebad886f31385ad33fbd4fd9bc1b8bab` |
| Source manifest | `benchmarks/pmc_real_papers.json` |
| Manifest SHA-256 | `639d78a07b9a0c7068ca1699e3d61d008c3a577da6f31697715c010ed3ba6014` |
| Protocol | `benchmarks/VALIDATION_PROTOCOL.md` |
| Protocol SHA-256 | `7134fce52a4cd9c630a11050799a04c93e514dd236e9a9113cf129931a926b02` |
| Reviewer coding manual | `benchmarks/CODING_MANUAL_20261106.md` |
| Coding manual SHA-256 | `3e2954cf82c05ff5d44a8e6d4c75ed673241fbf9a656cc5b902eeb2947d993e0` |
| Source | NIH NCBI PMC BioC API, open-access records |
| Benchmark status | 12 requested, 12 processed, 0 failed |

These hashes are SHA-256 of the committed LF blobs as checked out on
Linux and CI. A Windows checkout with `core.autocrlf=true` can hash a CRLF
working copy differently. Run the pilot from an LF checkout so the pack,
labels and evaluation all bind to the same bytes. The benchmark's internal
`manifest_sha256` must equal the manifest hash above.

The benchmark file must not be modified. Any rerun produces a different
`response_sha256` binding and is a different study.

## 3. Unit of analysis, inclusion and exclusion

- Each unit is one **(PMCID, finding-code)** pair.
- All 12 processed papers and both codes are included: **24 units**, with
  no exclusions and no substitutions.
- All units must be labelled, including negative cases. Incomplete coverage
  is rejected by `sra adjudicate-labels` and `sra evaluate-labels`.
- Truth is judged against the **supplied BioC-derived manuscript text**
  in the review pack, which is exactly the text the frozen benchmark
  processed. It is not a judgement about tables, figures or reference lists
  omitted by BioC extraction, except where a code explicitly targets them.
- External literature searches are out of scope. Support is judged against
  evidence reported inside the supplied text.

## 4. Predeclared finding codes

Only these two codes are evaluated. Both were emitted for at least one paper
in the frozen benchmark, so each has positive and negative cases. No other
code is added after seeing labels.

### 4.1 `potential_overclaim` (primary)

**Code meaning.** The document contains at least one statement that asserts
a stronger scientific conclusion than the evidence reported in the supplied
text supports.

**Label TRUE** if at least one statement in the supplied text:

- claims proof, guarantee, certainty or universality about a biological,
  clinical, physical or social phenomenon ("proves", "guarantees", "always",
  "never", "undeniably", or equivalent), and the supplied evidence does not
  justify that strength; or
- asserts causation from a design that only reports association, without
  adequate qualification; or
- generalises a clinical or biological benefit beyond the studied
  population, intervention or setting without support in the text.

**Label FALSE** if no such statement exists, or if every candidate is one of:

- an absolute word used non-claimingly (for example, a procedural statement
  such as "samples were always stored at 4 °C");
- negated, hedged or explicitly limited ("we do not prove", "may",
  "in this sample");
- a quotation or a description of another author's claim;
- a definition, mathematical condition or methodological constraint; or
- directly supported by the design and results reported in the text.

**Unit of decision.** One justified overclaiming statement is enough for
TRUE. The reviewer does not count occurrences and does not judge writing
style, grammar or whether the claim is ultimately correct in the literature.

### 4.2 `references_section_missing` (secondary, extraction-sensitive)

**Code meaning.** The supplied text contains recognizable in-text citations
but no references section with at least one recognizable reference entry.

**Label TRUE** if both hold in the supplied text:

- at least one recognizable citation marker appears in the body
  (bracketed numeric citation, or an author-year citation such as
  "Smith, 2020" / "Smith (2020)"); and
- no section headed References, Bibliography or Literature Cited contains
  at least one reference entry.

**Label FALSE** otherwise, including papers with no citation markers and
papers whose supplied text includes a references section with entries.

**Known extraction caveat.** The frozen BioC rendering intentionally keeps
only Abstract, Introduction, Methods, Results, Discussion and Conclusion
passages. It can omit the published reference list. A TRUE label therefore
may reflect BioC extraction rather than a deficiency in the published
manuscript. This code is secondary and must not be reported as evidence that
the publisher's article lacks references.

## 5. Reviewer qualifications and blinding

Two real reviewers are required, both:

- holding a PhD, MD or equivalent research training in a biomedical,
  health-science or adjacent empirical discipline;
- having at least two years of active peer-review or research-ethics
  experience;
- fluent in English;
- declaring no authorship, employment, funding or personal relationship
  connected to any of the 12 papers; and
- working independently: no discussion of cases, labels or the tool before
  both worksheets are submitted.

Each reviewer receives only:

- the review pack texts (`papers/<PMCID>.md`);
- the separate reviewer coding manual
  (`benchmarks/CODING_MANUAL_20261106.md`), which contains the definitions
  and instructions but not the benchmark, this analysis plan or automated
  results; and
- one personal worksheet (`reviewer_1.json` or `reviewer_2.json`).

Reviewers must not run the auditor, inspect automated reports, view the frozen
benchmark's `writing_finding_codes`, or see the other reviewer's worksheet.
A worksheet marked `blinded` is a procedural claim; software cannot verify
that blinding, identity, qualification or independence actually occurred.
Reviewer IDs in the label file are pseudonyms. Signed declarations are kept
by the study organizer, outside the repository.

## 6. Label collection and adjudication

1. Each reviewer independently sets `verdict` to JSON `true` or `false` for
   all 24 cases. Blank, `null`, string or missing verdicts are rejected.
2. Both completed worksheets and the adjudication file are supplied to
   `sra adjudicate-labels`. It verifies benchmark hashes, code sets, complete
   coverage, source hashes and distinct reviewer IDs.
3. A third qualified adjudicator, distinct from both reviewers and with the
   same qualification and conflict rules, resolves **every disagreement**.
   The adjudication file records `expert_label` and a rationale of at least
   20 characters for each disagreement. Decisions on agreed cases are
   rejected to keep the independent record intact.
4. If both reviewers agree on every case, the adjudicator still ratifies the
   file by providing an `adjudicator_id`; no per-case rationale is required.
5. The merged labels are frozen before `sra evaluate-labels` is run.

## 7. Reproducible procedure

```bash
# 1. Build the blinded pack outside the repository (network consent required).
sra validation-pack benchmarks/pmc_smoke_20261105.json \
  --reviewer reviewer_1 --reviewer reviewer_2 \
  --code potential_overclaim --code references_section_missing \
  --manual benchmarks/CODING_MANUAL_20261106.md \
  --out-dir /external/validation-20261106 --online

# 2. Two reviewers independently fill reviewer_1.json and reviewer_2.json.

# 3. Adjudicate disagreements in adjudications.json.

# 4. Merge independent decisions into final labels.
sra adjudicate-labels benchmarks/pmc_smoke_20261105.json \
  reviewer_1.json reviewer_2.json adjudications.json \
  --out final-labels.json

# 5. Compute confusion matrices, metrics and Wilson intervals.
sra evaluate-labels benchmarks/pmc_smoke_20261105.json \
  final-labels.json --out validation-report.json
```

`validation-pack` refetches every paper and refuses to continue if the
`response_sha256` differs from the frozen benchmark. The pack stores texts
outside the repository and must not be redistributed.

## 8. Metrics and analysis

For each code and for the micro-average over all 24 units:

- confusion matrix: TP, FP, FN, TN;
- precision = TP / (TP + FP);
- recall = TP / (TP + FN);
- specificity = TN / (TN + FP);
- two-sided Wilson 95% confidence intervals for each proportion;
- any zero denominator yields `null` for that metric and interval.

Inter-reviewer agreement is reported as raw exact agreement and Cohen's
kappa over binary verdicts; kappa is `null` when expected agreement is 1.
No threshold for "success" is preregistered. Results are descriptive.

## 9. Sample size and precision

The pilot uses all 12 available papers: 24 units. The frozen benchmark
contains six `potential_overclaim` positives and four
`references_section_missing` positives, with the remainder negative. With
such small positive counts, Wilson intervals will be wide (a 4/6 recall has
an interval roughly 30%–90%). The pilot is intended to test feasibility,
reveal gross error modes and produce a defensible protocol for a larger
study, not to establish stable performance.

A full study requires a separate preregistration with at least 60 papers
stratified by discipline and design, a justified sample-size calculation,
and a representative sampling frame rather than an allowlist of convenience.

## 10. What the software verifies and what it cannot

The tools verify: frozen source hashes, complete paper/code coverage, valid
boolean verdicts, two distinct declared reviewer IDs, a distinct declared
adjudicator, and a rationale for every disagreement. They also compute the
declared metrics.

The tools cannot verify: reviewer identity, qualifications, conflicts,
independence, actual blinding, scientific judgement, or whether a label is
correct. A structurally accepted file is not an expert certificate.

## 11. Deviations

Record every deviation here before running the final evaluation, with date,
reason and effect. Permitted examples: a source hash no longer matches and
the frozen benchmark cannot be reproduced; a reviewer withdraws before
labelling. Forbidden: changing code definitions, dropping negative units,
adding codes, or altering labels after seeing the confusion matrix.

_No deviations recorded as of 2026-11-06._

## 12. Data handling and licensing

Full texts are retrieved through the authorized PMC BioC API and stored only
in the external review pack. They are not committed to this repository and
must not be redistributed. The repository stores derived labels, hashes and
aggregate outcomes only. Review each publisher's license and the PMC terms
before any separate storage or reuse.

## 13. Preregistered limitations

- Twelve papers are a convenience allowlist, not a representative sample;
  estimates do not generalize to all scientific manuscripts.
- BioC extraction omits tables, figures and possibly reference lists; the
  evaluation is conditional on the supplied text.
- The corpus mixes disciplines and study designs; two general reviewers may
  lack field-specific expertise for some claims.
- `potential_overclaim` requires scientific judgement and may have legitimate
  disagreement even after adjudication.
- Wilson intervals assume independent units and do not adjust for clustering
  within papers or the small number of papers.
- Only two finding codes are evaluated; other audit codes remain unmeasured.
- Reviewer identity, independence and blinding are declared, not verified.

Source use rules: https://pmc.ncbi.nlm.nih.gov/tools/openftlist/
PMC BioC: https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/
