# Local deterministic inspection toolkit

Additional source preparation, mathematics/statistics, contextual citations,
tables/figures and real-paper evaluation are specified in
[inspection expansion](INSPECTION_EXPANSION.md). Old check inputs remain supported.

The toolkit complements the Z3 logic adapter with working local checks. It
never edits manuscripts. JSON and Markdown findings go to the user separately.
It does not claim to certify every scientific field or turn arbitrary prose
into verified formal statements. These additions are unreleased source features.

| Area | Selected tool | Implemented operation | Interpretation |
| --- | --- | --- | --- |
| Mathematics | SymPy 1.14.0 (BSD) | Exact rational-coefficient polynomial identities, derivatives, supplied antiderivatives checked by differentiation | Conditional exact algebra |
| Quantities | Pint 0.25.3 (BSD) | Named units, SI prefixes, compound units, dimensional incompatibility, standalone offset-temperature conversion | Agreement with explicitly supplied quantities and tolerance |
| Data replay | Existing SciPy >=1.11 (BSD) | Two-sided Welch t, paired t, Pearson correlation, classical one-way ANOVA from supplied numeric arrays | Calculation or agreement within declared tolerances |
| Text preparation | spaCy 3.8.18 (MIT) | Untrained `xx`, `en`, `tr` sentence segmentation with exact offsets and lines | Candidates requiring human review |
| Citation passages | RapidFuzz 3.14.6 (MIT) | Literal matching and case-sensitive normalized Indel similarity on supplied local passages | Ranked candidates; semantic support is always `NOT_ASSESSED` |

Pint 0.26.2 requires Python 3.12; 0.25.3 preserves this repository's Python 3.11
support. Optional tools are not vendored or relicensed. Their own dependencies
and licenses continue to apply. No statistical resampling, model inference,
remote retrieval or supplementary analysis script execution is performed.

## Install and run

```bash
python -m pip install -e ".[logic,toolkit]"
sra verify-toolkit examples/toolkit.json --out reports/toolkit
```

Separate extras: `mathematics`, `units`, `statistics`, `language`, `citations`.
The base installation remains dependency-free. Missing backends are reported per
check as `UNAVAILABLE`; other checks continue. Unsupported backend calculations
are `FAILED`. Exit codes: 0 requested execution completed, 1 a partial report
was saved, 2 invalid input or output configuration. A `REFUTED` result alone does
not cause exit 1: the requested comparison completed successfully.

```python
from sra.toolkit import verify_toolkit_spec
report = verify_toolkit_spec(open("examples/toolkit.json", encoding="utf-8").read())
```

Node: `verifyToolkit('spec.json', {out: 'reports/toolkit', manuscript: 'paper.md'})`.
MCP: `verify_toolkit(spec_json, content=None, file_format='md', encoding='text')`.
MCP retains 1 MiB specifications, 20 MiB uploads and 2 MiB response limits.
No tool accepts remote URLs, arbitrary paths inside the spec or executable code.

## Bind a specification to a manuscript

When supplying `--manuscript paper.md`, or using `sra review paper.md
--toolkit-spec spec.json --out reports/review`, the specification must contain
both `source_sha256` (raw file) and `extracted_text_sha256` (exact parser text).
Use `sra.document.load_document` and SHA-256 of `document.text.encode('utf-8')`
to obtain these identities. Python unified review accepts `toolkit_spec`; Node
accepts `toolkitSpec`; MCP unified review accepts `toolkit_spec_json`.

Bound `claim_candidates` reads the manuscript snapshot and must omit `text`.
Bound `citation_match.claim` must occur exactly in extracted manuscript text.
Passage SHA-256 values bind the exact UTF-8 passage supplied by the caller;
they do not establish publisher identity, accurate quotation or semantic support.
Unbound specifications are explicitly marked `unbound`, even if hashes were
provided. No source hash validates the prose-to-formula or data-to-paper mapping.

## Input contract and limits

The executable reference is `examples/toolkit.json`. Strict schema version `1.0`
accepts only `checks` and the optional source identities. Each check has a unique
ASCII identifier (`[A-Za-z][A-Za-z0-9_]{0,31}`) and one supported `kind`.
Unknown keys, duplicate JSON keys, nonfinite values and oversized inputs fail
before external work. At most 32 checks and 1 MiB encoded JSON are accepted.

- `polynomial_identity`: `variables`, `left`, `right`. `derivative` and
  `antiderivative` additionally require `variable`. Variables are real; at most
  four. Expressions accept decimal rational constants, declared variables,
  `+ - *`, division by a nonzero constant polynomial and literal integer powers
  0..8. Each expression: 512 characters, 128 AST nodes, 24 nesting levels,
  polynomial degree <=12, <=256 terms, <=512-bit coefficients at every step.
  No calls, attributes, variable denominators, general functions or string-based
  SymPy parsing. `REFUTED` means the equation is not a polynomial identity; it
  may hold at particular values. Antiderivative constants may differ freely.
- `unit_conversion`: `value`, `from_unit`, `to_unit`, `reported`, optional `atol`
  (default `1e-9`). Unit grammar: names, `1`, `*`, `/`, integer powers -8..8;
  128 characters and 48 AST nodes. A fresh Pint registry uses a fixed 50-digit
  Decimal context. Standalone `degC`/`degF` support offsets; ambiguous compound
  offset or logarithmic calculations may fail explicitly. No custom definitions,
  contexts, files or quantities parsed from unrestricted strings.
- `statistical_replay`: `test`, `groups`, optional `reported` containing
  `statistic` and/or `p_value`, optional `atol=1e-9`, `rtol=1e-7`.
  Two groups for Welch/paired/Pearson, 2..8 for ANOVA, 2..2000 values per group,
  at most 10000 values per check. Paired/Pearson lengths must match. Numbers
  must be finite decimal values (64 characters, exponent -64..64). Numerical
  replay uses SciPy defaults without stochastic resampling. Numerical warnings,
  nonfinite results and zero p-values yield `UNDETERMINED` (precision loss,
  overflow, degeneracy or underflow is unresolved); a finite result alone is
  insufficient to award agreement.
  Replay warning capture is serialized between toolkit calls on Python 3.11/3.12
  to prevent concurrent checks from stealing each other's numerical warnings.
  No reported metric means `CALCULATED`; supplied metrics are compared within
  `max(atol, rtol * max(abs(computed), abs(reported)))`. Sampling assumptions,
  appropriateness of the test, missing-data handling and authenticity need review.
- `claim_candidates`: optional `language` (`xx` default, `en`, `tr`), `text`
  required only when unbound. At most 100000 characters and 1000 nonblank
  sentences; excess sentences fail without silent truncation. These are all
  sentence candidates, not semantic claim extraction. `formal_expression` is
  always null. Abbreviations and sentence boundaries may require correction.
- `citation_match`: `claim` <=2000 characters, 1..16 `passages`, each with unique
  `id`, exact `text` <=2000 characters and `sha256`. Up to five candidates are
  returned, sorted by literal match first, then descending similarity, then ID.
  No score threshold awards a truth verdict. DOI registration remains a separate
  metadata check; full-text acquisition and semantic entailment are not supplied.

All checks are validated before importing optional backends. In a unified review
the local toolkit completes before any explicitly enabled registry/model request.
Every report records the normalized input hash, adapter/backend versions and
report hash. Repetition assumes the same versions and numerical platform;
bit-identical results across arbitrary dependency or platform changes are not
claimed. `complete` describes execution, not scientific validity.

## Validation

Validation on 2026-11-12: 701 Python tests passed with 5234 runtime statements
covered (100% statement coverage), 28 Node tests and 43 MCP tests passed,
including a real stdio toolkit call. The synthetic heuristic controls passed
10/10 cases; these do not measure accuracy on real scientific manuscripts.
Fresh-context review found finite-but-wrong Welch p-values following overflow;
RED/GREEN regressions now require numerical warnings to yield `UNDETERMINED`.
A concurrent-warning regression also reproduced cross-check warning loss;
serialization fixed it. Unsupported offset/log calculations are failures rather
than dimensional-refutation verdicts. Distribution verification checked all 146
declared source files and 47 installed Python modules, including a clean base
wheel install and CLI/audit run. Optional backends were exercised in the source
installation. Package metadata checks and byte-identical independent wheel/sdist
build comparisons passed. Scientific correctness across all
domains or independent expert accuracy has not been established.

## Primary sources

- [SymPy polynomial operations](https://docs.sympy.org/latest/modules/polys/reference.html)
  and [unsafe string parsing warning](https://docs.sympy.org/latest/modules/parsing.html).
- [Pint temperature conversions](https://pint.readthedocs.io/en/stable/user/nonmult.html)
  and [package releases](https://pypi.org/project/Pint/).
- [SciPy statistical functions](https://docs.scipy.org/doc/scipy/reference/stats.html).
- [spaCy rule-based sentencizer](https://spacy.io/api/sentencizer/).
- [RapidFuzz ratio definition](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html).
