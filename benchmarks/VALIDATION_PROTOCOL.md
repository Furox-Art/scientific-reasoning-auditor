# Pre-registered independent validation protocol

The 12-paper PMC BioC corpus tests external-source integration and robustness.
It does NOT provide expert ground truth, scientific accuracy, sensitivity,
specificity, false-positive rate or claim-support verification.

## Required independent evaluation

1. Preregister finding-code definitions, inclusion/exclusion criteria,
   study designs, stratification, target sample size and paper sources.
2. Obtain full text via authorized, license-compliant PMC or publisher APIs.
   Preserve the immutable BioC response SHA-256, PMCID and DOI per article.
3. Recruit two qualified *blinded* independent reviewers, who cannot see
   the system's finding codes during labeling. Document their qualifications,
   conflicts, independent decisions and an adjudication process.
4. Adjudicate each selected **document-level finding code** to true/false
   for EVERY paper/code combination, including negative cases. Make sure
   coding guidance defines what constitutes a finding and false positive.
5. Freeze the benchmark JSON and the adjudicated label JSON separately
   before evaluating model predictions. Retain both source SHA-256 values.
6. Run `sra evaluate-labels`, report confusion matrices by finding code,
   precision, recall, specificity and Wilson 95% intervals. Report missing
   categories as null, not zero.
7. Reproduce the results on held-out papers. Report blinding, inter-rater
   agreement, representativeness, uncertainty and discipline differences.
   Wilson intervals here do not adjust for sampling bias or paper clustering.

## Label schema

The following is an illustrative **format only**, not real expert evidence.
Each processed paper and `finding_codes` combination requires exactly one
case with two distinct reviewer IDs and final adjudication. The
`source_sha256` must match the raw BioC `response_sha256` recorded in
the frozen benchmark (not the rendered Markdown hash).

    {
      "finding_codes": ["unmatched_numeric_citation"],
      "cases": [
        {
          "pmcid": "PMC1790863",
          "code": "unmatched_numeric_citation",
          "source_sha256": "<copy SHA-256 from frozen report>",
          "expert_label": false,
          "reviewer_ids": ["independent_assessor_A", "independent_assessor_B"],
          "adjudicated": true
        }
      ]
    }

Do not use the example's sample label as actual evidence. Software can
validate the format, source hash and two declared IDs, but cannot verify
expert identity or independence. Full systematic independent scientific
validation is still outstanding until a representative corpus is genuinely
adjudicated.

Source use rules: https://pmc.ncbi.nlm.nih.gov/tools/openftlist/
PMC BioC: https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/
