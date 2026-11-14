# Inspection expansion: areas 1–6

These unreleased source features extend the existing toolkit and unified review.
All reports and examples are in English. Manuscripts remain read-only; findings
and proposed inputs are separate JSON/Markdown reports. No new graphical UI,
package publication or main-branch merge is included.

## 1. Prepare inspection inputs from a manuscript

```bash
sra prepare-inspection examples/inspection-paper.md --out reports/prepared
sra review examples/inspection-paper.md --prepare-inputs --out reports/review
```

Python: `sra.inspection.prepare_inspection(document)`, where `document` comes from
`sra.document.load_document`. Unified Python review accepts `prepare_inputs=True`.
Node exposes `prepareInspection(path, options)` and `prepareInputs: true` in
`reviewManuscript`. MCP exposes `prepare_inspection(content, file_format, encoding)`
and the `prepare_inputs` parameter in `review_manuscript`.

Candidates retain exact source character ranges, lines, quotes and raw/extracted
source hashes. Recognized inline `$...$` or single-line `\[...\]` equations
receive proposed symbolic checks when the restricted grammar is supported.
Common t/F/z/chi2 statistic reports receive proposed rounding-aware checks.
Assumption sentences, Markdown tables and figure references/captions receive
explicit review candidates. Fenced code is ignored without shifting offsets.

`proposed_toolkit_specs` contains bounded executable-shape drafts (at most 32
checks/eight symbolic checks each), retaining all proposed checks across batches.
The singular `proposed_toolkit_spec` is populated only when exactly one batch is
needed; otherwise it is null. Confirm every mapping and assumption before saving
a batch as a toolkit input. No proposed check executes automatically; `checks_executed` is
false. In particular, prose such as "assume positive" does not silently become
a mathematical assumption. PDF text/OCR extraction is inherited from the existing
loader; full LaTeX semantics, table recognition in raster PDFs and implicit
prose-to-formula translation remain unverified. Preparation is limited to
200000 extracted characters and 500 candidates; limits fail explicitly.

## 2. Broader symbolic mathematics

The new kinds `symbolic_identity`, `symbolic_derivative` and
`symbolic_antiderivative` accept `left`, `right`, a `variables` object and, for
calculus, `variable`. Each variable declares one of `real`, `positive`,
`nonnegative`, `nonzero`. The grammar supports rational arithmetic, integer
powers -4..4, and non-nested `sin`, `cos`, `exp`, `log`, `sqrt` calls.

No strings are passed to eval, SymPy `parse_expr` or string `sympify`. An inert
AST is compiled to SymPy constructors. Denominator nonzero, logarithm positive
and square-root real-domain obligations are recorded before cancellation.
Square roots in calculus require strictly positive radicands. An unresolved
obligation returns `UNDETERMINED`, even if cancellation would yield zero.

Thus `x/x = 1` with only real x is undetermined; declaring nonzero x allows
verification. `sqrt(x**2) = x` for real x has a negative counterexample.
Verification uses assumption-preserving rewrites; refutation requires an exact
finite counterexample from a fixed rational grid. Failure to find one is
undetermined. Antiderivatives are checked by differentiation, not integration.
This is not a general theorem prover.

Limits: 1..3 variables, 256 characters/64 AST nodes/10 nesting levels per
expression, four non-nested function calls, no nested powers, estimated expansion
width <=256, at most eight symbolic checks per report. Each symbolic operation
runs in an isolated Python subprocess with a five-second timeout. A timeout is
undetermined, not proof; load-dependent budget outcomes are possible. The selected
interpreter must have this source checkout installed, as required by Node too.

## 3. More statistical inspection

`statistical_analysis` supports these explicitly selected operations:

- `linear_regression`: paired `x`/`y` arrays, 3..2000 observations, returns simple
  OLS slope, intercept, R-squared, slope standard error and two-sided p-value.
  Nulls are counted. Default `missing_policy: report` abstains if any are missing;
  explicit `complete_case` drops incomplete pairs and reports the count. This
  does not justify complete-case assumptions or fit multivariable/mixed models.
- `multiple_testing`: 1..2000 supplied `p_values`, `method` equal to `holm`,
  `bonferroni`, or `benjamini_hochberg`. Fixed Decimal arithmetic preserves input
  precision and original ordering. The caller must supply the whole intended
  family; BH independence/positive-dependence requirements are not inferred.
- `assumption_diagnostics`: Shapiro-Wilk per group and median-centered Levene
  on 2..8 groups (3..2000 observations each, <=10000 total). P-values are
  diagnostics. Failure to reject does not prove normality, equal variance or
  independence, and no automatic test selection is made.

`statistic_consistency` accepts a test (`t`, `z`, `F`, `chi2`), decimal-string
`statistic`, exact integer `df` list, decimal-string `reported_p` and `relation`
(`=`, `<`, `>`; default `=`). t/z are two-sided; F/chi-square upper-tail.
Both statistic and equal-sign p-value rounding are represented as intervals.
All possible rounded statistic values agreeing with the reported interval can
be verified; disjoint intervals can be refuted; overlaps remain undetermined.
Inequality thresholds are explicit. Tail zero/underflow, nonfinite outputs or
numerical warnings cannot yield agreement. These checks do not validate study
design, one-sided-test intent, corrected degrees of freedom or data authenticity.

## 4. Citation source context

`citation_context` takes a `claim` and 1..8 `sources` with `id`, exact `text` and
UTF-8 `sha256`. A source is at most 100000 characters; the common 1 MiB spec
bound still applies. Bound queries must occur exactly in the manuscript.
Local sentence/line windows retain offsets, neighboring context and source
hashes. RapidFuzz token-set similarity ranks up to five candidates with stable
tie ordering. Windows are <=800 characters with overlap for long segments;
at most 2000 windows across sources. Excess input fails instead of being dropped.

Negation and direction cues are displayed for human inspection. They are not
semantic contradiction labels. `support_status` remains `NOT_ASSESSED`; an exact
quote, high similarity or DOI metadata match never establishes entailment.
Sources are supplied locally; no publisher download or model call occurs.

## 5. Tables, figures and supplemental snapshots

`table_compare` accepts exact `table_csv`, `supplement_csv`, explicit `keys` and
optional absolute `atol` (default zero). Both CSVs need distinct headers, unique
nonempty keys, 1..32 columns and 1..1000 data rows; each text <=200000 characters.
Rows are joined by keys so ordering is irrelevant. Missing rows/columns and cell
differences are reported; numeric cells use bounded Decimal comparisons and
other cells exact text equality. Reports bind both input hashes and include
total mismatches with an explicitly marked first-100 display limit. Caller
extraction and the CSV-to-manuscript mapping still require confirmation.

`figure_svg` inventories text labels, title/description, viewBox, shape counts
and active/external-content presence from supplied SVG text. It does not render
or load external resources. Event attributes, CSS URL/import indicators and
active SVG elements are flagged; the inventory is explicitly incomplete and is
not a sanitizer. DTD/entity declarations are rejected, XML <=200000
characters and <=2000 nodes. Scientific visual interpretation is always false;
axis units/scales, uncertainty and agreement with tables are review questions.
Raster images, curve digitization, full graphic comprehension and arbitrary
supplemental analysis-code execution are not implemented.

## 6. Real-paper evaluation and external expert labels

```bash
python tools/fetch_scifact.py --out-dir ../scifact-data
sra benchmark-evidence ../scifact-data/corpus.jsonl \
  --claims ../scifact-data/claims_dev.jsonl --out reports/scifact
```

The downloader accepts only the frozen official archive hash and two expected
file hashes, reads bounded named members without extracting archive paths and
refuses to overwrite different inputs. Runtime evaluation is offline and
records corpus/claims hashes, backend version, denominators and per-case results.

Measured on the released development split: 5183 corpus records, 300 claims,
188 claims with gold rationale evidence. The remaining 112 are excluded from
retrieval denominators. Gold-sentence overlap recall at k=1/3/5 was
0.2541/0.4863/0.6913. Returned-window overlap precision was
0.4947/0.3227/0.2799. This is retrieval inside supplied cited documents, not full
literature search. An overlap is any intersection with a human-labelled sentence,
not recovery of the complete rationale. Semantic classification coverage is 0;
all 300 claims abstain and semantic accuracy is null. These results expose a
limited lexical baseline; they do not establish scientific-error detection rates.

Broader expert evaluation uses the existing `validation-pack`, adjudication,
`evaluate-labels` and domain-cohort workflows. Two independent declared reviewers
and adjudication are required there; no new experts, labels, or multi-field
accuracy numbers were invented for this expansion. Additional labelled domains
remain unmeasured until independently obtained reference labels are provided.

Attribution: SciFact, Wadden et al., *Fact or Fiction: Verifying Scientific Claims*
(2020), [official repository](https://github.com/allenai/scifact),
[data schema](https://github.com/allenai/scifact/blob/master/doc/data.md).
Claims/rationale annotations are CC BY 4.0; the abstract database is ODC-By 1.0;
repository code is Apache 2.0. Original data are downloaded separately and not
relicensed or bundled as this project's MIT code. [Official licenses](https://github.com/allenai/scifact/blob/master/LICENSE.md).

## Run the expanded toolkit

```bash
python -m pip install -e ".[toolkit]"
sra verify-toolkit examples/inspection-checks.json --out reports/expanded
```

This example intentionally includes an unresolved domain, so partial execution
and exit code 1 are expected. Existing Python `verify_toolkit_spec`, Node
`verifyToolkit` and MCP `verify_toolkit` accept all new kinds. The toolkit adapter
version is `bounded-toolkit-2`; old kinds and report schema remain compatible.

Primary mathematical/statistical references:
[SymPy assumptions](https://docs.sympy.org/latest/guides/assumptions.html),
[SymPy simplification limits](https://docs.sympy.org/latest/tutorial/simplification.html),
[SciPy statistical functions](https://docs.scipy.org/doc/scipy/reference/stats.html).

## Software validation

719 Python tests passed with 5838 runtime statements covered (100% statement
coverage); 28 Node and 43 MCP tests passed, including real stdio preparation.
One fresh whole-change review led to RED/GREEN regressions for gold-candidate
leakage, oversized proposed specifications and SVG event/CSS indicators.
The sdist inventory checked 156 declared source files; the wheel checked 52
Python modules, clean installation and CLI/audit execution. Metadata checks
passed, and independent wheel/normalized-sdist builds were byte-identical.
These are software checks, not an estimate of multi-field scientific accuracy.
