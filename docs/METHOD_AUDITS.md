# Scoped scientific-method audits

Four toolkit checks (dependency-free by default) support parts of novelty, search reporting,
measurement agreement and question/method alignment. They do not decide global
scientific adequacy. Existing `source_overlap` remains a separate lexical screen.
The toolkit now exposes 35 check kinds; not all kinds produce mathematical proofs.
These checks are included in Python 0.11.0 / npm 0.4.0.

```bash
sra verify-toolkit examples/method-audits.json --out reports/method-audits
```

The example is synthetic. Its database, searches, measurements and study are
fictional. No database query is run. Python uses `verify_toolkit_spec(spec)`;
Node uses `verifyToolkit(specPath, options)`; MCP uses
`verify_toolkit(spec_json)`. Unified review accepts a source-bound toolkit spec.
All interfaces leave the manuscript unchanged and return a separate report.

## Contribution comparison

`novelty_comparison` requires `dimensions` (1..16 distinct simple identifiers),
`contribution` and 1..100 `comparators`. Each comparator has `id`, `text`, verified
`sha256`, and `features`. Contribution/features have exactly the declared keys.
Every value is either null or `{ "value": "literal string", "quote": "evidence" }`.
The value must occur literally in the quote and the quote must occur in its
snapshot. Optional integer `start` selects an exact codepoint offset in the extracted text.
Without it, a quote must have a unique occurrence to support a determinate record
comparison. Ambiguous matches retain their first offset but abstain; overlapping
occurrences are detected. Explicit offsets verify location, not semantic role.
All snapshots together are bounded to 200,000 characters; manuscript text is
bounded to 100,000. No external corpus is silently searched.

The check compares strings case-sensitively, preserves field-level differences
and lists sources with the same declared features. Fully mapped comparisons
return CANDIDATES, never VERIFIED novelty. Missing mappings or ambiguous unselected quotes return UNDETERMINED. Optional
`required_comparator_ids` (1..1000 distinct simple IDs) lists selected comparison
sources expected by the caller. Missing comparators remain visible and abstain;
providing the selected set does not establish corpus completeness.
Different selected features do not establish novelty. Feature choice, historical
priority, semantic equivalence, source selection and corpus recall require
review. `scientific_novelty` and `corpus_recall` remain NOT_ASSESSED.

## Search-record audit

`literature_search_audit` requires caller-selected `required_sources` (1..32
identifiers), `as_of` (a frozen YYYY-MM-DD date), `max_age_days` (0..36500),
`searches` (0..100 records), and `deduplication`. No current clock is used.

Each search has a distinct `id`, a source identifier, `platform`, exact `query`,
`searched_on`, `coverage_start`, `coverage_end`, and `records_found`. These fields
must be supplied; null records missing information. Dates use YYYY-MM-DD; counts
are integers in [0,100000000]. Multiple searches per source and extra sources
are allowed. The check reports missing required sources/fields, a search dated
after `as_of`, age above the caller's threshold, and reversed coverage periods.
`deduplication` has `records_before`, `duplicates_removed`, `records_after`,
each a bounded count or null. Only before - removed = after is checked; counts
from overlapping queries are not assumed additive.

VERIFIED means supplied record fields and declared consistency conditions pass.
REFUTED means an explicit condition fails. Missing records yield UNDETERMINED,
while observed discrepancies remain visible. Neither result establishes
literature adequacy, query sensitivity, relevant database selection, recall,
screening validity, authentic execution or PRISMA-S compliance.
Optional `reference_coverage` has `required` (1..1000) and `retrieved` (0..1000)
record ID lists. IDs are exact, case-sensitive strings (1..256 characters, no
whitespace/control characters), with no duplicates. The report lists missing
required IDs and matched/required counts. A missing required record refutes only
the declared retrieval requirement. This is a supplied reference-set check, not
an estimate of overall search recall. Source selection, ID aliases and actual
retrieval authenticity are unverified. In particular, DOI normalization must be
performed consistently by the caller before this generic identifier comparison.
`literature_adequacy` remains NOT_ASSESSED.

## Paired measurement agreement

`measurement_agreement` requires 3..1000 paired `reference` and `measured` values,
a caller-declared common `unit`, and `acceptable_difference` (ordered `lower` /
`upper` bounds, or null). Decimal numeric values are bounded to +/-1e12.
Differences are measured - reference. An explicit 160-digit decimal context, independent of ambient precision, rounding,
exponent limits and traps, preserves
decimal differences before float calculation. The output includes original
pairs, differences, mean difference, sample SD, RMSE, and estimated normal limits
of agreement: mean difference +/- 1.96 sample SD.

The caller must explicitly set `independent_pairs`, `normal_differences`, and
`constant_bias_and_variance` to true to receive a bound-comparison verdict.
False/null assumptions, absent acceptance bounds, zero observed dispersion, or
an endpoint within 16 local float ULPs of its acceptance bound yield
UNDETERMINED. Numerical estimates are retained. VERIFIED/REFUTED concerns only
whether the estimated limits fall inside caller-selected bounds.

These are approximate normal limits, not confidence intervals or a guarantee of
95% population coverage. Small samples leave substantial estimation uncertainty.
Normality, independent subjects, lack of proportional bias, constant variance,
reference accuracy, common units and suitable acceptance bounds are unverified.
Repeated observations per subject require a different model. No conversion of
units or general construct-validity assessment is performed.
`measurement_validity` remains NOT_ASSESSED.

## Question/method target alignment

`question_method_alignment` requires `question` and `method`, each containing
exactly `population`, `outcome`, `contrast`, `timepoint`, `effect_measure`, and
`analysis_unit`. Each entry is a literal value/evidence-quote record or null,
with the same quote, value and optional `start` checks as contribution comparison.
The fixture explicitly selects separate question and method occurrences.

This is a deliberately narrow comparison of declared targets, useful when these
six fields apply. VERIFIED means all mapped strings agree; REFUTED means at
least one differs and none is missing. Any null or ambiguous unselected quote yields UNDETERMINED, with known
differences retained. Non-comparative questions or other study types may leave
fields unresolved. This is not a complete estimand specification. It does not
check whether the analysis identifies a causal effect, uses an appropriate
model, has enough data or answers the scientific question. Equal words may hide
different concepts and different words may be equivalent.
`method_appropriateness` remains NOT_ASSESSED.

## Source identity and report interpretation

For text checks, use `text` when unbound. With manuscript binding, omit `text`
and supply top-level `source_sha256` and `extracted_text_sha256`; the engine uses
the manuscript snapshot. Hashes and exact quotes establish identity, not source
authenticity or correct annotation. Role assignment to question, method or
contribution is caller-supplied. Explicit offsets verify exact occurrence, but do not independently establish
a quotation's intended section or semantic role.

Unified criteria include evidence pointers with explicitly limited scopes.
All criterion scientific verdicts remain NOT_ASSESSED even after record audits
or numerical agreement. No overall scientific-quality score, independent expert
validation, human reference labels or multi-field accuracy estimate is added.

## Method references

- [Crossref: interpreting Similarity Check reports](https://www.crossref.org/documentation/similarity-check/similarity-report-understand/): similarity requires interpretation and is not an automatic plagiarism/novelty verdict.
- [PRISMA-S checklist, Cochrane copy](https://work.cochrane.org/sites/work.cochrane.org/files/uploads/checklist_searches_for_editors_cochrane_work.pdf): source/platform, exact strategies, dates and record reporting. This implementation checks only the subset stated above.
- [Bland and Altman (1999), PubMed abstract](https://pubmed.ncbi.nlm.nih.gov/10501650/), DOI 10.1177/096228029900800204: paired differences and normal limits of agreement. The formula is supported by the abstract; the complete article has not been independently audited here.


## Optional confidence-aware measurement decision

Add `confidence_level` in [.5,.999] to `measurement_agreement` to request a
confidence-based decision. This option needs SciPy (`pip install
"scientific-reasoning-auditor[statistics]"`). Without it, base calculations remain
dependency-free and the decision concerns estimated limits only. With it, missing
SciPy or numerical failures retain estimates but abstain on the requested decision.

Under the three explicitly affirmed measurement assumptions, let `c` be the
requested confidence coefficient and `alpha = 1-c`. Build a two-sided Student-t
interval for the mean difference and a chi-square interval for its SD, each at
confidence `1-alpha/2`. Each tail uses `alpha/4`; df is `n-1`. Bonferroni gives
simultaneous coverage at least `c` for this mean/SD rectangle. Monotonic propagation
to `mu +/- 1.96 sigma` gives two conservative population-limit confidence
intervals. This is a construction from standard component intervals, not an exact
joint Bland-Altman interval or a prediction interval.

VERIFIED requires the entire outer confidence bounds to lie inside the caller's
acceptance band. REFUTED requires confidence-supported violation of at least one
boundary: the lower-limit interval is entirely below the acceptable lower bound,
or the upper-limit interval entirely above the acceptable upper bound. Overlap,
touching/near boundaries (16 local float ULPs plus a conservative 1e-10
construction-scale margin for quantile/roundoff sensitivity), unaffirmed assumptions and zero
observed dispersion abstain. The construction-scale guard accounts for cancellation of large terms into
small endpoints; it is a numerical safety margin, not a certified error enclosure.
Confidence describes repeated-sampling coverage
under the model, not the probability that assumptions or scientific validity
are true. All general validity fields remain NOT_ASSESSED.

`examples/method-audits-advanced.json` deliberately omits a selected comparator
and a required reference, and has insufficient measurement precision to establish
confidence-based agreement. Its partial execution status is intentional. Records
and measurements are synthetic; no real database search was executed.

Component references:

- [NIST confidence limits for the mean](https://www.itl.nist.gov/div898/handbook/eda/section3/eda352.htm).
- [NIST confidence interval for SD](https://www.itl.nist.gov/div898/handbook/prc/section2/prc231.htm).
- [NIST Bonferroni method](https://www.itl.nist.gov/div898/handbook/prc/section4/prc473.htm).
