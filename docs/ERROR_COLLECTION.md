# Independent error-review collection

The offline source-checkout exporter now handles any valid bounded
`error-benchmark/1.0` manifest, rather than only the two-paper feasibility
recipe. It packages supplied snapshots and blank human forms; it does not
select papers, generate human judgments, run the auditor or establish
representative validation. Existing pilot sources, selection and preregistration
remain unchanged. Code and packet reports are English; manuscripts are read-only.

## Freeze and package a cohort

Prepare the manifest described in [ERROR_BENCHMARK.md](ERROR_BENCHMARK.md).
Before collecting labels, record the discrepancy definitions, sampling frame,
inclusion/exclusion criteria, discipline/design strata, group families, split
allocation, expected sample size and handling of mapping uncertainty. A new
cohort needs its own version and prospective protocol; this tool does not
retroactively preregister a convenience sample. Select without auditor outcomes,
retain eligible negatives and record exclusions and missing source evidence.
Inspect source permissions and secure the complete originals needed by reviewers.

```bash
python -m pip install -e .
python tools/error_review_pack.py build-cohort --manifest cohort.json --out collection.zip
```

All existing manifest bounds apply: at most 32 papers, 32 targets, 256 cases,
200000 total source-text characters and 1 MiB input JSON. Preflight validates
source hashes, every quoted passage, split/group consistency and executable
specification structure before writing any output. No optional numerical
backend runs during packaging. JSON decimals retain the manifest's exact
values for hashing. No paths or URLs inside the manifest are fetched.

`collection.zip` contains:

| Entry | Recipient and content |
| --- | --- |
| `reviewer-A.zip` | Only reviewer A: full supplied text snapshots, source/permission declarations, quoted cases, target definitions, instructions and a blank A sheet |
| `reviewer-B.zip` | Only reviewer B: the same context, with a separate blank B sheet |
| `organizer/manifest.json` | Organizer only: the original frozen executable manifest |
| `organizer/unfilled-labels.json` | Organizer only: blank combined label format |
| `SHA256SUMS` | Hash inventory of every other file in that archive |

Reviewer archives omit executable checks, automated predictions, test-kind
identifiers, group/split allocation, organizer files and the other reviewer's
sheet. They retain target IDs/definitions and exact quotes with zero-based,
end-exclusive offsets in the supplied source snapshot. Every snapshot is
preserved in full and byte-equivalent UTF-8 text; this does **not** verify that
it is the complete original article. Original PDFs, figures and supplements
are not bundled by the generic exporter. Supply authorized originals separately
where needed, or reviewers must retain uncertain judgments. The original
two-paper `build --sources ...` command still bundles its hash-pinned PDF/XML
originals under the frozen recipe.

Blinding is procedural. Supplied source text, attribution, identifiers and
target definitions can disclose prior judgments or identities. Inspect the
packet before sending; omitted structured fields do not sanitize arbitrary
caller text. Neither the tool nor pseudonymous IDs authenticate reviewer
qualifications, independence, actual blinding or permissions. No invitations
or external messages are sent by these commands.

ZIP timestamps and ordering are fixed; byte identity is promised only for the
same inputs and Python/zlib environment. Every CLI output uses exclusive file
creation: preexisting files, symlinks and hardlinks are not overwritten. Inputs
are read within their byte bound. Do not place personal identities or returned
human records in the public repository without an appropriate disclosure plan.

## Inspect independently returned sheets

Obtain two genuine completed sheets. Every case needs `error`, `no_error`,
`uncertain` or `not_applicable`, plus a 20-2000 character rationale. Preserve
the assigned reviewer slot, case IDs, schema and manifest hash. Each sheet
uses one pseudonymous reviewer ID, distinct from the other sheet's ID.

```bash
python tools/error_review_pack.py inspect --manifest cohort.json --reviewer-a returned-A.json --reviewer-b returned-B.json --out inspection.zip
```

Blank/incomplete/malformed sheets, altered cohorts, duplicate/unknown cases,
wrong slots, invalid rationales and repeated reviewer IDs are rejected. No
missing decision is inferred. Original sheets remain untouched. The inspection
report binds both complete sheet fingerprints, including their rationales.

Keep `organizer/review-inspection.json` and `.md` private. They show a
four-category contingency table, both marginal counts, raw/expected agreement,
unweighted Cohen kappa and every unresolved case ID, **before adjudication**.
Uncertain and not-applicable judgments remain distinct nominal categories.

For N cases, A exact agreements and marginal counts a_c / b_c, let
E = sum(a_c * b_c). Raw agreement is A/N, expected agreement E/N² and
kappa is (N*A - E)/(N² - E). Integer numerators and denominators are retained;
zero denominators return null, including the all-one-category agreement case.
Negative kappa remains negative. Rows/columns use ascending reviewer IDs so
reversing input review order cannot change column meaning. The definition
matches [scikit-learn's unweighted Cohen kappa documentation](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html).
No kappa quality threshold, standard error or confidence interval is supplied.
Cases may be correlated, and descriptive agreement does not establish accuracy.

If disagreements exist, the outer ZIP also contains `adjudicator.zip`. Give
the adjudicator only that inner ZIP and any necessary authorized originals.
It contains disputed cases, their target definitions, complete corresponding
source snapshots and `adjudications.json` with null decisions/IDs. Neither
reviewer's decisions, IDs, rationales, sheet hashes nor the organizer report
are copied into that packet. Its source text has the same disclosure caveat.
The adjudicator must supply their own judgment and a distinct ID. An absent
adjudicator packet means no label disagreements were found, not that the
judgments are scientifically correct.

```bash
python tools/error_review_pack.py merge --manifest cohort.json --reviewer-a returned-A.json --reviewer-b returned-B.json --adjudications returned-adjudications.json --out frozen-labels.json
```

Omit `--adjudications` only when all cases agree. Merge retains the existing
contract: each disagreement requires explicit third-party adjudication; an
explicit supplied adjudication can also override an agreement. Freeze the
returned sheets, adjudications and final labels before inspecting predictions.
This process cannot be completed honestly until actual humans return decisions.

## Evaluate and inspect dependence

```bash
sra benchmark-errors cohort.json --out results/run
sra evaluate-errors cohort.json results/run.json frozen-labels.json --out results/evaluation
```

The Python evaluator, CLI, existing typed Node `evaluateErrors` and content-only
MCP `evaluate_errors` retain the original metrics and add:

- `reviewer_reliability`: pre-adjudication four-label agreement. A fixed pair
  of declared IDs is required for Cohen kappa; changing pairs gives
  `not_assessed`. Per-case pair order is normalized. The existing
  `reviewer_agreement` raw count is retained for compatibility.
- `by_paper` and `by_group`: the same confusion, exclusion, abstention and
  metric denominators for each paper/trimmed declared group. Each result case
  now includes `group_id`.
- `group_sensitivity`: for at least two groups, recompute the pooled counts
  after removing each whole group, retaining the number of remaining groups.
  One group gives `not_assessed` and an empty omissions list. These are
  leave-one-group-out sensitivity results, **not** confidence intervals,
  resampling inference, independent test-set performance or group weighting.

Unknown/inapplicable gold judgments remain excluded, while abstained gold
errors remain in end-to-end recall denominators in every subset. Development
and test strata remain separate in `by_split`; pooled omission diagnostics
must not be treated as held-out performance. Group IDs are declarations:
undeclared shared authors/data, alias publications and sampling bias cannot be
repaired by these counts. Representative multi-field scientific-error validation
and independently obtained human labels are still outstanding.
