# Scientific-writing benchmark: independently annotated research revisions

This repository records a **real, independently annotated scientific-writing
benchmark result**, not a claimed universal editing accuracy or a replacement
for human journal editors.

## Source, provenance and permitted use

- Original research dataset: *arXivEdits: Understanding the Human Revision
  Process in Scientific Writing* (Jiang, Xu and Stevens, EMNLP 2022),
  https://aclanthology.org/2022.emnlp-main.641/
- Download location: https://huggingface.co/datasets/miwytt/arXivEdits_edits
- Mirror revision SHA: `3fdba9ce77468272ed4c32bcf3f9f38983ed57be`
- Split: `edits/test.csv` (all **200** available test rows).
- Source CSV SHA-256:
  `6541dce4c7f82019e8f24dc0259a1a04e20dd853d87b465adeb1febc2cbf0220`
- Distinct arXiv paper identifiers: **69**.
- Evaluation date: **2026-11-05**.
- Original per-article licensing varies. The repository contains **only
  derived aggregate outcomes and source hashes**, not the manuscript
  sentences, corrected versions or full annotation tables.
- Only the built-in, offline English `style_review` rules were measured.
  The optional local LanguageTool integration and Turkish rules were **not**
  evaluated.

## How reference labels were determined

Each original *source → revision* pair contains human-annotated edit
intentions. The positive class means that **at least one edit** was tagged
with an intention beginning with `Lang-` or `Improve-grammar`. The
comparison class consists of revised sentences where no such intention was
tagged; those edits could be about content or formatting.

**These are NOT verified grammar-error-free negatives**: the absence of
an annotated language edit does not establish linguistic correctness.
Likewise, two equally valid grammatical rewrites can differ.
The dataset is *enriched for revised sentences*, not a representative
sample of arbitrary published academic prose.

The benchmark does not tune the rules against the test split.
The evaluation unit is one human-annotated source/revision pair,
not an individual error token, manuscript, journal or correction claim.

## Observed results (frozen report)

| Measure | Observed | Interpretation |
| --- | ---: | --- |
| Total evaluated pairs | 200 | Edited scientific sentence pairs |
| Language-annotated revision pairs | 136 | Human positive label |
| Other-revision pairs | 64 | Imperfect negative proxy |
| TP / FP-proxy / FN / TN-proxy | 4 / 2 / 132 / 62 | Conditional annotation agreement |
| Positive label recall | **2.94% (4/136)** | 95% Wilson CI approx. 1.15%–7.32% |
| Precision *proxy* | 66.67% (4/6) | Very unstable (only 6 positive predictions) |
| Negative *proxy* specificity | 96.88% (62/64) | Not true grammar specificity |
| Literal replacement agreement | 16.67% (1/6) | Not correction adequacy |

The central actionable finding is **very low coverage** of actual
human-annotated language edits. The apparent high negative specificity is
not a substitute for testing on expert-confirmed grammatically clean
sentences. Literal replacement agreement is a deliberately stringent
word-string comparison, not a measure of semantic preservation or
acceptable alternative edits. Confidence intervals shown in the
JSON report are elementary sentence-level Wilson intervals; they do not
account for the grouping of sentences within 69 papers.

The [frozen machine-readable report](../benchmarks/arxivedits_style_test_20261105.json)
includes the complete confusion matrix, intervals, per-rule flag counts,
sha256 and limitations, without redistributing the original human text.

## Reproduce the result

Download the version-pinned test CSV from the original public mirror
to an **external directory** (not inside the repository); review the
dataset's per-paper licenses and terms before storing or reusing it:

```bash
curl --fail --location \
  https://huggingface.co/datasets/miwytt/arXivEdits_edits/resolve/3fdba9ce77468272ed4c32bcf3f9f38983ed57be/edits/test.csv \
  --output /tmp/arxivedits-human-test.csv

python -m sra.cli benchmark-language /tmp/arxivedits-human-test.csv \
  --expected-sha256 6541dce4c7f82019e8f24dc0259a1a04e20dd853d87b465adeb1febc2cbf0220 \
  --max-rows 200 \
  --out /tmp/arxivedits-benchmark.json
```

The program refuses a mismatched SHA-256 or a silently truncated prefix.
Raw source sentences and revised targets are not written into the report.
No external requests occur **during evaluation**; obtaining the dataset
is a separate, intentional download step.

## What is still needed for publication-quality editing validation

1. Obtain a representative, license-compatible scientific-writing corpus
   including *unedited* and edited manuscripts.
2. Blindly obtain two or more professional editorial assessments of:
   error spans, acceptable corrections, unchanged correct spans,
   meaning preservation, and degree of severity.
3. Evaluate the exact correction suggestions, not merely edit-intent
   flags, using independent adjudication and held-out domains.
4. Report annotation agreement, precision/recall with clustered
   confidence intervals, abstention/coverage and error analysis by field.
5. Repeat for Turkish and for a specific version of the local
   LanguageTool model/service, using legitimate licensed data.

**No professional editor was recruited or fabricated for this run.**
