# Check inventory

Every finding the audit can emit, what it actually detects, what it cannot
detect, and where its false positives come from. `tests/test_check_inventory.py`
parses this file and the source: a rule that exists without a row here fails the
build, and a row without a rule fails it too.

A row is a promise about wording, not about science. None of these checks decides
whether a manuscript is correct.

| Check id | What it detects | What it cannot detect | Where a false positive comes from |
|---|---|---|---|
| `structure.methods_missing` | No heading recognisable as Methods. | A methods section under another name, or methods folded into another section. | Non-English headings outside the alias list; a paper whose method lives in a supplement. |
| `structure.results_missing` | No heading recognisable as Results. | Results reported inside Discussion, or in tables only. | German/French headings; a results section named after the analysis. |
| `structure.conclusion_missing` | No heading recognisable as Discussion/Conclusion. | A closing argument written without a heading. | Papers that end with "Limitations" or "Future work". |
| `structure.limitations_missing` | No heading recognisable as Limitations. | Limitations stated in the discussion prose. | Short reports and letters that never use such a heading. |
| `structure.references_missing` | No heading recognisable as References. | An unheaded bibliography, or citations managed in a footnote. | Numbered bibliography without a heading; preprint templates. |
| `language.absolute_claim` | Absolute or conclusive wording ("proves conclusively", "definitively"). | Hedged near-synonyms that are not in the lexicon. | A quotation of someone else's overclaim, or a negated sentence ("does not prove"). |
| `reasoning.causal_claim_observational_design` | Causal conclusion wording while Methods describe an observational or non-randomised design. | Whether the causal claim is identified by design (instrument, adjustment set, natural experiment). | Observational wording describing related literature rather than this study; models that justify causation without randomised design. |
| `reasoning.correlation_causation_review` | Association wording somewhere plus causal language in the conclusion. | Whether the association and the causal claim concern the same exposure, outcome or population. | A paper that reports both an association and a justified causal analysis for a different outcome. |
| `reasoning.association_and_causal_claims` | Both association and causal claim sentences extracted from the same manuscript. | Which sentence belongs to which study question. | Reviews that summarise several studies, some associational, some causal. |
| `reasoning.directional_contradiction` | A result sentence and a conclusion sentence share topic terms but use opposite direction wording. | Whether the two sentences describe the same comparison, subgroup or endpoint. | Subgroup analyses where opposite directions are both true; sentences about different time points. |
| `reasoning.directional_conflicts_truncated` | The same directional conflict when the extracted text was truncated. | Anything beyond the truncation point. | Long manuscripts cut at the extraction limit; the pairing is then incidental. |
| `reasoning.mixed_design_causal_review` | Causal claim in a manuscript that mentions both randomised and observational wording. | Which design the causal claim rests on. | Methods that describe a randomised trial plus a cited observational cohort. |
| `reasoning.conclusion_without_lexical_candidate` | A conclusion sentence with no lexically overlapping evidence sentence. | Paraphrase, negation or evidence stated in a table or figure. | Short conclusions that restate the abstract; evidence expressed with different vocabulary. |
| `statistics.repeated_rate_ratio_ci_conflict` | The same displayed rate ratio and p-value printed with different 95% confidence intervals. | Whether the two intervals belong to different models, endpoints or populations. | Adjusted and unadjusted analyses of the same effect reported in one table. |
| `statistics.multiplicity_unaddressed` | Three or more reported p-values and no statement of a correction, test family or self-correcting procedure. | Whether those p-values belong to one family of hypotheses; whether a correction was applied but never described. | Pre-specified single tests in a results section that also quotes p-values from the literature; Turkish or other-language phrasings outside the vocabulary. |
| `statistics.design_test_mismatch` | An independent-samples test named in a manuscript that describes a paired, matched or repeated-measures design. | Which analysis was actually run; whether a paired test was used without being named. | Methods that describe both designs, or a citation of someone else's unpaired test. |
| `statistics.confidence_interval_p_conflict` | One sentence whose 95% CI and p-value disagree about the null. | Intervals and p-values printed in different sentences, tables or figures; intervals for a different model than the p-value. | Descriptive intervals compared by mistake are excluded, but an interval for an adjusted estimate printed next to an unadjusted p-value still looks like a conflict. |
| `statistics.mean_outside_confidence_interval` | A mean that lies outside its own 95% CI in the same sentence. | Numbers spread across sentences, tables or figures. | A sentence reporting the mean of one variable and the CI of another; a CI for a difference printed beside a mean. |
| `statistics.impossible_p_value` | A p printed as 0.000, above one, bounded above one, or negative. | Whether a p of 0.000 is a rounding convention rather than an error. | Journals that require "p = 0.000"; texts that report p-values of other statistics in the same sentence. |
| `statistics.impossible_dispersion` | A negative SD/SE, or a sample size of zero, in one sentence. | Whether the number belongs to the SD column at all. | Sentences that list a change and a dispersion ("from SD 1.2 to SD -0.4" describing a delta); tables parsed as prose. |
| `statistics.group_count_test_mismatch` | Three or more groups named with only a pairwise test in the same sentence. | Whether an omnibus test appears in another sentence; whether the pairwise test was adjusted. | A sentence stating the design and the post-hoc test separately; a citation of a pairwise test from another study. |

## Table values

Numbers read out of a table (`sra.tabular_values`) are fed into
`statistics.impossible_p_value` and `statistics.impossible_dispersion`, so a cell
can raise one of those two findings. The evidence names the column and the table
row; the rest of the table, its caption and its footnotes are not read.
