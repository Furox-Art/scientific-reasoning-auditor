# Source-statistic preparation follow-up

Development work began 2026-11-16; verification/publication completed
2026-11-17 (Europe/Istanbul). Engine Python 0.10.1; Node adapter 0.3.1.

## Actual improvement and scope

The frozen 0.10.0 twelve-paper pilot produced zero executable-shape drafts.
The updated preparer recovers three literal statistic/df/p triplets, all from
one ecology paper: DOI [10.1371/journal.pone.0288477](https://doi.org/10.1371/journal.pone.0288477).
Its separately printed df, uppercase P and X^(2) notation were unsupported.
All three were fixed in advance as extraction controls before parser changes.
The same twelve frozen source texts were processed, without changing the
original cohort, replacing a paper or rewriting the original result.

This is post-hoc development reuse, not held-out multi-field error-detection
accuracy. The other eleven papers still receive zero executable-shape drafts.
A source triplet is not a new independent paper or a genuine human error label.

## Observed cases

| Source statistic, df, p | Literal recovered | Unconfirmed draft | Supplied mathematical scenario |
| --- | --- | --- | --- |
| X^(2) = 7.66, df = 2, P = 0.02 | Yes | UNDETERMINED | VERIFIED |
| X^(2) = 11.54, df = 2, P < 0.01 | Yes | UNDETERMINED | VERIFIED |
| X^(2) = 4.72, df = 2, P = 0.10 | Yes | UNDETERMINED | REFUTED |

The scenario explicitly supplies an upper central chi-square reference,
exact df=2 and the existing printed-decimal rounding convention. For the third
case its computed p interval is about [0.0941845, 0.0946566], whereas printing
0.10 under that convention denotes [0.095, 0.105]. The conditional intervals
agree within 1e-14 with a separate 60-digit Decimal evaluation of exp(-x/2).
This is numerical agreement, not a formal numerical error bound.

**None of these is a confirmed scientific-error label.** The paper methods state
Kruskal-Wallis tests and Bonferroni-adjusted Dunn comparisons. The correct
statistic-to-p mapping, asymptotic reference, correction and actual author
rounding convention have not been independently authenticated. Every mapping
confirmation is false and every paper-error label is null. No expert identity,
human review, raw-data replication or misconduct judgment was created.

The organizing assistant read the entire normalized article text, including
methods/results/discussion/references. Linked figure images, supplements, raw
observations and analysis code were not reviewed or executed. Model reading is
not independent human scientific adjudication.

## Implemented safeguards

- Every supported triplet in a paragraph keeps its exact original span/quote.
- Directions and df precision remain unknown until explicitly confirmed;
  unchanged drafts abstain if the caller explicitly executes them.
- Percentages, ranges, uncertainties and expression suffixes remain full,
  unresolved cues. Missing values and statistical semantics are not guessed.
- Additional p mentions in the same paragraph stay visible without a draft.
- Code fences, 200000-character/500-candidate limits and 32-check batching stay
  enforced. A whole-path regression covers 190000 whitespace characters.
- The evaluator uses detached hash-verified source bytes and requires two
  numerical interval endpoints.

The initial implementation/result are preserved at commit 1c0c8f7 and
initial-run.json/.md. The separate agent code review found four issues; its
corrections and the additional heading-parser runtime regression are recorded
in [review-corrections.md](review-corrections.md). Recorded results bind the
actual producer and all runtime source hashes. No old report was overwritten.

## Verification

918 Python tests passed with 100% statement coverage over the runtime package
(7500 statements on Windows/Python 3.15.2); 31 Node and 51 MCP tests passed.
Eleven new focused regressions cover the new parsing and failure cases. Tool
coverage, branch coverage and scientific accuracy are not claimed.
The report and release notes were rendered and visually inspected before
publication. GitHub CI and package publication are separately visible in Actions.

## Reproduce from the source checkout

Install the source with the statistics extra, then use a fresh output prefix:

```bash
python -m pip install -e ".[statistics,research]"
python tools/evaluate_statistic_preparation.py --out /external/new-run
```

The evaluator is a source-checkout tool. It requires the original frozen
multi-field text snapshots and inventories included in the repository; it is
not a standalone npm operation. No network acquisition is performed. Frozen
input hash mismatches and existing outputs are rejected.

The user-facing preparer is available in CLI, Python, Node and MCP:

```bash
sra prepare-inspection examples/statistic-preparation.md --out reports/prepared
```

Inspect source context and explicitly confirm the reference, tail, df precision
and corrections before saving any draft as a numerical toolkit specification.
Preparation itself never executes a check or supplies a scientific verdict.

## Attribution and unchanged evidence

The original article has CC0 permission in its preserved JATS record. Attribution
and the complete source/license record are in
[the original source index](../multifield-20261116/SOURCES.md).
The publisher/author does not endorse this software. The original 0.10.0
multi-field execution pilot and historical psychology comparison remain unchanged.
Representative scientific-error accuracy and genuine independent labels remain
outstanding.

Method references: [SciPy chi-square distribution](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.chi2.html)
and the linked original article. Literal expected values are extraction controls;
they are not externally adjudicated scientific-error gold.
