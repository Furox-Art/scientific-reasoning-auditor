# Six-stratum real-paper execution audit — 2026-11-16

**Actual paper processing is complete; representative scientific-error accuracy
validation remains incomplete.** This source-checkout study uses the published,
unchanged SRA 0.10.0 engine. It is not a new Python/npm release.

## Observed results

- Complete publisher metadata frame: **1,022** PLOS ONE Research Articles,
  published January 2024. All response pages and exact URLs/hashes are archived.
- **1,001** records match the six predefined, disjoint subject-tag strata;
  21 remain outside this operational target. A seed fixed before frame capture
  selects **two per stratum**, without viewing auditor decisions.
- **12/12** original publisher JATS sources available with article-specific
  CC BY 4.0 or CC0 permission. No unavailable paper was replaced.
- **12/12** requested text-screening executions complete; **12/12**
  same-environment semantic repeat comparisons agree in the corrected run.
- **78** profile-rule/paper units: 8 textual evidence candidates, 30 partial
  cues and 40 not-detected/manual-review states. None establishes adequate
  reporting, a scientific error or an absent method.
- **230** preparation candidates: 162 figure mentions, 59 statistical cues,
  8 assumption cues and 1 equation cue. These are neither distinct figures
  nor a reference-labelled set of 59 statistical tests.
- **Zero executable checks were automatically proposed. Zero numerical,
  causal or symbolic checks were run in this paper cohort.**
- Across **516** criterion/paper units (43 per paper): 112 screening completed,
  284 not requested, 108 require human review and 12 not implemented. All
  516 scientific verdicts remain **NOT_ASSESSED**. Units within a paper are
  dependent and are not 516 independent validation observations.
- **Zero new human labels; scientific accuracy, precision and recall are not
  estimated.** Historical psychology reference comparisons remain separate.

See [corrected summary](recorded-run/summary.md), [complete machine results](recorded-run/summary.json),
[prospective protocol](protocol.md), [pre-result clarification](normalization-and-replay-clarification.md)
and [all attempts](attempts.md). The failed first run is preserved in
[first-run/](first-run/): output creation changed its own repository provenance.
It is not hidden, overwritten or counted as a scientific disagreement.

## What the sampling represents

This is a reproducible allocation within one publisher/month metadata snapshot,
not representative validation across all scientific fields. The priority rule
and unequal sampling fractions are explicit; pooled counts are descriptive,
not population prevalence or a self-weighted accuracy estimate.

| Subject-tag stratum | Frame records | Selected | Sampling fraction |
| --- | ---: | ---: | ---: |
| Physics | 117 | 2 | 1.71% |
| Chemistry | 94 | 2 | 2.13% |
| Computing | 207 | 2 | 0.97% |
| Animal | 74 | 2 | 2.70% |
| Social science | 255 | 2 | 0.78% |
| Clinical | 254 | 2 | 0.79% |

**Publisher tags do not establish profile applicability.** The computing draw
contains a tef/injera agronomy paper and an MRI measurement paper. The physics
draw includes insect thermal performance and a fuzzy-graph/tsunami paper.
The chemistry draw includes a cell-biology paper. These reflect the frozen
broad taxonomy and priority rule; they were retained without resampling.
Medicine membership does not establish a randomized clinical trial, and
zoology membership does not establish an animal intervention. Thus six
subject-tag strata must not be presented as six independently adjudicated
scientific disciplines. Missing profile cues are not scientific deficiencies.

## Reading and representation limits

Every original JATS source and its normalized title/abstract/body/back text
was processed by software. Inline notation, tables, references and captions
are flattened. The first derivation is preserved in texts/; the corrected
cell/block-separated derivation is texts-v2/. Neither is a faithful visual
reproduction or a validated table/equation extraction.

Front metadata beyond title/abstract (including some publisher data-availability,
funding and competing-interest records) are not part of the engine's text input.
They remain available in the complete original JATS. This source-representation
limit can affect evidence retrieval. Linked figure images, PDFs and supplements
were not reviewed in the primary run. Original papers were not altered.

The organizing assistant inspected the selected titles, abstract/method excerpts
and the complete normalized Cr-Detector text; this is model reading, not human
expert adjudication. The remaining eleven papers were not manually read from
beginning to end. No claim of twelve complete human scientific reviews is made.
No returned human review, identity authentication, external blinded adjudication,
raw-data/code reproduction or reference error label exists for this cohort.

## Reproduce the actual offline run

Use a source checkout and optional dependencies, for example:

```bash
python -m pip install -e ".[pdf,statistics,logic,toolkit,research]"
python tools/audit_multifield_papers.py run --out /absolute/path/outside-checkout/new-run
```

Windows uses the same command with an absolute external output path. The output
directory must be new and **outside this repository**: source provenance includes
offline pilot recipes and reports. Keep the checkout and environment unchanged
throughout the paired run. Platform, dependencies, repository hashes and graph
endpoints are retained; only the enumerated timestamp/display-path fields in the
clarification are excluded from semantic comparison. Raw reports preserve all
fields. Cross-platform byte equality is not claimed.

The metadata/source acquisition commands `capture` and `sources` are explicitly
online, for a new empty capture only. Existing snapshots are not overwritten.
The frozen cohort already includes all required source bytes; do not refresh it
to reproduce. Hash/selection/normalization mismatches fail before auditing.
Each per-paper runtime failure and repeat mismatch is retained without dropping
later papers or replacing failed cases. Blank review forms contain no identities,
decisions, automated predictions or adjudications; no invitations were sent.

## What remains before an accuracy claim

1. Define a wider, multi-publisher target population and validate actual field/
   study-design assignments independently; use an adequately sized sample.
2. Obtain genuine independent source-linked scientific-error labels, keeping
   applicability uncertainty and within-paper dependence in the analysis.
3. Independently verify prose/table/equation mappings and execute appropriate
   checks on eligible negative and positive cases. Automatic candidate absence
   must remain an observed limitation rather than a silent eligibility exclusion.
4. Evaluate source extraction, numerical checking and scientific judgment as
   distinct tasks. Preserve abstentions and all selected-paper denominators.

Attribution and article-specific licenses: [SOURCES.md](SOURCES.md).
No author or publisher endorsement is implied. The project MIT license does
not replace the original articles' CC BY/CC0 terms.
