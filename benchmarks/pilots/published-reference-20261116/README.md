# First frozen external reference comparison: SRA 0.9.0

This is a retrospective comparison against historical, source-declared manual
coding of reported statistical results. It is **not** whole-paper scientific
accuracy, new blinded human review, SRA text-extraction validation or a
representative multi-field/held-out study. Full original articles were not
available in this packet and are not claimed to have been read.

## Observed results

The source has 1211 rows: 1148 manual reference labels and 63 rows without them.
The source-study exclusion removes 28 labeled rows, retaining 1120 rows in 48
source author-key groups. All rows and both exclusion categories remain in JSON.

| Quantity | Exact count | Descriptive value |
| --- | --- | --- |
| Decided reference rows | 672 / 1120 | 60.0% coverage |
| Abstained reference rows | 448 / 1120 | 40.0% |
| Reference errors flagged | 34 / 49 | 69.4% reference-frame recall |
| Reference errors abstained | 15 / 49 | Not silently discarded |
| Flagged rows agreeing with reference | 34 / 54 | 63.0% decided precision |
| False alarms relative to reference | 20 / 54 flags | 37.0% of flags |
| Correct decisions among decided rows | 652 / 672 | 97.0% selective accuracy |

The decided confusion counts are TP=34, FP=20, TN=618 and FN=0. Abstentions
include 15 reference errors and 433 reference negatives. Thus zero decided false
negatives does **not** mean complete error detection. Selective accuracy alone
would hide both the abstentions and the modest precision of warnings.

Abstention reasons: 408 missing third-party raw strings, 28 unsupported literal
expressions and 12 numerically/rounding-undetermined results. Source strings were
supplied by statcheck; their availability is not an SRA extraction measurement.
Historical contextual corrections or one-tailed tests may explain disagreement;
the original articles and row joins have not been independently re-adjudicated.

`first-run.json` and `first-run.md` preserve the first completed run without edits.
JSON retains every case, numeric check result, group stratum and whole-group
omission diagnostic. No inferential confidence intervals are claimed.

## Frozen identities

- Analysis specification committed before predictions: `47f6e274540db6ec83715b574bec55e263f4bda2`.
- Producer and source-format clarification committed before predictions:
  `ea44a886ad7032f9d038772a5cfad478a30f200e`.
- Specification SHA-256: `db7ebe9e11c4c7e40423f6f694f1c878f603db9b2f881fca117c349a08316808`.
- Clarification SHA-256: `ceba6273d680d2fd01d00b6d6d3786343a2fb3dc1d04c04920a7fa676c87daef`.
- Producer SHA-256: `4e9a4b63a1106c0a01024c0f6b3e9854156e8fdf9c62d5a398bbceef67d3263c`.
- Semantic report SHA-256: `c7d40750a24cb44cf7b5a11414f76efc7260846ae812ff48020d835d8d27d30f`.
- Complete JSON file SHA-256: `e99491bbc0817074b9237fdb129eb192aca49a962bcdff78b03274056c0a92a0`.

The published 0.9.0 wheel is pinned and all 67 installed source/typing files
matched it before execution. Numerical environment: Windows AMD64, Python
3.15.2, NumPy 2.5.5, SciPy 1.18.1. No SRA engine code or tolerances were changed
after seeing these results. See [attempts.md](attempts.md) for the initial runtime
failure and native-process thread limits used for the completed run.

## Sources and license

Original manual coding: Wicherts, Bakker and Molenaar (2011),
https://doi.org/10.1371/journal.pone.0026828. Comparison data/codebook curated
for Nuijten and colleagues' statcheck validation work:
https://doi.org/10.3758/s13428-015-0664-2 and
https://doi.org/10.31234/osf.io/tcxaj.

- Workbook, original bytes: https://osf.io/axfbn/.
- Codebook, original bytes: https://osf.io/xqce2/.
- Source-study exclusion script: https://osf.io/zcysv/.
- Source project: https://osf.io/yu5wj/; metadata declares **CC BY 4.0**,
  https://creativecommons.org/licenses/by/4.0/.

Original sources remain unchanged. Reports are derived comparison results;
unused fields were omitted and no manual decisions were generated or altered.
No source endorsement, independent reviewer authentication or claim that all
original statistical conclusions are correct follows from these records.

## Reproduce from a source checkout

The comparator is a source-checkout tool, not a new Node/MCP operation. It
evaluates the already-published 0.9.0 engine; Python/Node registry versions are
unchanged. Download is explicit; `run` is offline. Existing input/output files
are not overwritten, and changed source/wheel hashes stop execution.

PowerShell example for the measured environment:

```powershell
py -3.15 -m venv .venv-reference
.venv-reference/Scripts/python -m pip install "scientific-reasoning-auditor[statistics]==0.9.0" "numpy==2.5.5" "scipy==1.18.1"
$env:OPENBLAS_NUM_THREADS="1"
$env:OMP_NUM_THREADS="1"
$env:MKL_NUM_THREADS="1"
$env:NUMEXPR_NUM_THREADS="1"
.venv-reference/Scripts/python -I tools/evaluate_published_reference.py download --out-dir reference-inputs
.venv-reference/Scripts/python -I tools/evaluate_published_reference.py run --workbook reference-inputs/150702ComparePvaluesPLOSStatcheckOrderedCleaned.xlsx --codebook reference-inputs/150706CodeBookComparisonStatcheckPLOS.docx --engine-wheel reference-inputs/scientific_reasoning_auditor-0.9.0-py3-none-any.whl --out reports/reference
```

If a provider changes its default file version, use the pinned original version;
do not update the expected hash just to make a download pass. Source-format
parsing, case linkage, uncertainty about corrections and the selective sample
remain limitations. New independent human review across representative papers
is still required for general scientific-error performance claims.
