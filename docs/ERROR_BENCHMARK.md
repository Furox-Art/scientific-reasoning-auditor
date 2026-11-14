# Deterministic scientific-error evaluation

This tool evaluates bounded structured-check discrepancies on caller-supplied
text snapshots. It does not establish that a manuscript is scientifically
correct. A real-paper performance estimate still needs genuine, separately
obtained labels and an appropriate corpus. Synthetic examples are software
controls only. Reviewer identity, independence and qualifications are not
authenticated.

## Frozen inputs

A manifest declares `schema_version: error-benchmark/1.0`, `dataset_id`,
`dataset_kind` (`synthetic` or `real_papers`), `papers`, `targets`, and `cases`.
Each paper has `id`, `group_id`, `split` (`development` or `test`), `discipline`,
`source_uri`, `license_note`, UTF-8 `text`, and its `sha256`. Text snapshots are
caller-supplied; no network retrieval, automatic prose mapping, PDF extraction
or manuscript modification occurs. Citation/permission declarations are not
verified. Full text must be available to actual reviewers, not just a quote.

Each target has `id`, a precise `definition` of the discrepancy, and toolkit
`kind`. Each case has `id`, `paper_id`, `target_id`, an exact `source_quote`,
and a toolkit `check` whose ID equals the case ID. Target kind and check kind
must match. Mapping prose to structured inputs remains a caller judgment.
All sources, quotes and check specifications validate before any backend runs.

The manifest is limited to 1 MiB of JSON, 32 papers, 32 targets, 256 cases,
200000 total text characters, 100000 characters per paper, 2000 per quote,
and 32 checks per paper. IDs are simple ASCII identifiers of at most 32
characters. Every paper and target must be used. Duplicate source hashes and
duplicate checks on the same quoted target are rejected. A `group_id` must not
cross development/test splits. Repeated trimmed source URIs must share a group;
the software cannot detect URI aliases, undeclared paper
families or semantic duplicates.

Fingerprints use sorted, compact UTF-8 JSON with finite numbers; dictionary
ordering and whitespace do not affect them. List order and text bytes do.
JSON decimal tokens retain their exact decimal value/precision; Python callers
can supply `Decimal` or numeric strings. Values already rounded by a caller's
binary float parser cannot be recovered. Numbers remain distinct from strings.
The run records manifest, source, runtime-source and result fingerprints and
backend/numerical environment versions. Hashes detect changes, not authenticity
or proof that a caller ran the claimed software.

## Run and label

```bash
sra benchmark-errors examples/error_benchmark/synthetic.json --out reports/error-run
sra error-label-template examples/error_benchmark/synthetic.json --out reports/unfilled-labels.json
sra evaluate-errors examples/error_benchmark/synthetic.json reports/error-run.json examples/error_benchmark/synthetic-labels.json --out reports/error-evaluation
```

Use genuine `real_papers` manifests for real evaluation. Freeze definitions,
selection and splits before running the tool; the software cannot establish
that preregistration or blinding actually took place. The label template has
null decisions/identities and cannot be evaluated until completed. Give each
reviewer the complete sources and coding definitions, keeping automated results
and other reviewer decisions separate. Do not fill templates with invented
expert judgments. Existing PMC blinded-pack commands remain available.

Labels declare `schema_version: error-labels/1.0`, `manifest_sha256`,
`label_origin` (`synthetic_fixture` for synthetic data, `caller_declared_external`
for real papers), and `cases`. Every case needs exactly two `reviewers` with
distinct `reviewer_id`, `label` (`error`, `no_error`, `uncertain`,
`not_applicable`) and a rationale of at least 20 characters. Agreement supplies
the final label. Disagreement requires an `adjudication` by a third distinct
reviewer with label and rationale. A provided adjudication also overrides
agreement. Every manifest case, including negatives, must be labeled exactly
once. Uncertain and not-applicable labels remain visible and are excluded from
binary performance denominators. Real-paper manifests reject synthetic labels.

## Predictions and denominators

The runner executes actual source-bound toolkit checks. Only VERIFIED/REFUTED
from the explicitly documented decision kinds can map to `no_error`/`error`:
polynomial identity/calculus, symbolic identity/calculus, unit conversion,
statistical replay, reported-statistic consistency, CSV table comparison,
declared-DAG backdoor checking and literal protocol field comparison. These
decisions concern supplied checks, not whole-paper truth. All other statuses
and kinds abstain, including CANDIDATES, CALCULATED, UNDETERMINED, unavailable
backends, caller bias judgments, lexical retrieval and checklist records.
No detected candidate never becomes a negative label.

Evaluation checks complete case/source/manifest identities and the imported
run fingerprint. It recomputes decision mappings from retained check results;
inconsistent imported predictions are rejected. Reported metrics include exact
numerators and denominators and null for undefined ratios:

| Metric | Numerator / denominator |
| --- | --- |
| Decision coverage | Decided binary-labeled cases / all binary-labeled cases |
| Selective accuracy | Correct decisions / decided binary-labeled cases |
| Selective risk | Wrong decisions / decided binary-labeled cases |
| Decided precision | TP / (TP + FP) |
| Decided recall | TP / (TP + FN) |
| Decided specificity | TN / (TN + FP) |
| Decided false-positive rate | FP / (TN + FP) |
| End-to-end recall | TP / all gold errors, including abstained errors |
| False alarms per labeled negative | FP / all gold negatives |

Confusion counts cover decided binary units only; abstentions on errors and
negatives are separate. Summary, target, discipline and split strata use the
same policy. Development and test results are reported separately; pooled
counts are descriptive and are not held-out performance claims. No confidence
intervals are calculated: case dependence, paper clustering, sampling and
representativeness require a separately specified uncertainty analysis.
Repeatability and 100% software test coverage are not scientific accuracy.

## Interfaces and remaining validation

Python: `sra.error_benchmark.run_error_benchmark(manifest)`,
`error_label_template(manifest)` and
`sra.error_evaluation.evaluate_errors(manifest, run, labels)` accept dictionaries
or bounded JSON strings. Node exposes `benchmarkErrors`, `errorLabelTemplate`,
`evaluateErrors` using file paths and the existing output options. MCP exposes
`benchmark_errors`, `error_label_template`, `evaluate_errors` with JSON strings,
including inline source texts; it never accepts server file paths or fetches
source URIs. Python/CLI imported runs and output reports are bounded to 4 MiB;
the existing MCP limits remain 1 MiB per JSON input and 2 MiB complete response.
Split larger cohorts explicitly rather than truncating results.

The committed example labels intentionally exercise true/false positives,
negatives, exclusions and abstentions. They are fabricated test controls, not
external reviewer assessments. This implementation supplies the executable
evaluation machinery. A licensed representative real-paper cohort, genuine
independent labels, verified prose-to-check mapping and a preregistered
sampling/cluster uncertainty analysis are still needed for scientific accuracy
claims. Existing SciFact retrieval numbers are not substituted for this task.
