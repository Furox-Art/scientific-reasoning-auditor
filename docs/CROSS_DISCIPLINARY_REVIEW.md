# Cross-disciplinary review (source checkout)

`sra review` combines existing SRA checks on one extracted manuscript snapshot.
It accepts manuscripts from any field for common screening; specialist reporting
cues exist only for the six profiles listed by `sra capabilities`. This is an
extensible foundation, not a validated expert system for all scientific fields.

These additive commands require a source checkout containing this feature.
The published Python 0.8.0 and npm 0.1.2 releases are not guaranteed to include it.

## Local installation and a first review

```bash
python -m pip install -e ".[pdf,statistics]"
sra capabilities
sra review examples/unified_review/theoretical_math.md --study-type theoretical --out reports/theory
sra review examples/unified_review/computational_physics.md --study-type computational --discipline computing --discipline physics --out reports/simulation
```

Outputs are `reports/<name>.json` and `.md`. The JSON report follows
[`cross-disciplinary-review/1.0`](../schemas/cross-disciplinary-review.schema.json).
The input manuscript and supplied specifications are never overwritten.

## Declared study type and selected disciplines

Study types are `unknown` (default), `quantitative`, `qualitative`, `computational`,
`theoretical`, `systematic-review`, `narrative-review` and `mixed`. They are caller
declarations, not a scientifically verified classification. Unknown/mixed types
explicitly request human applicability review.

Select zero or more `--discipline` arguments: `clinical`, `animal`, `physics`,
`chemistry`, `computing`, `social-science`. Repeated identical profiles are run
once, preserving selection order. Without a profile, common checks still run and
the report explicitly records missing specialist assessment. A mathematics paper
can use theoretical/common checks without pretending a mathematics expert module
exists. Interdisciplinary work can select multiple existing profiles.

For declared theoretical and narrative-review papers, two empirical structural
signals (`structure.methods_missing`, `structure.results_missing`) are moved to
`excluded_findings` with original details and a reason. All other findings remain;
the legacy audit command, graph schema and six expert-review contracts are unchanged.
This policy does not decide whether any individual paper's reporting is adequate.

## What completion means

Each module has `status`, `reason`, `source_sha256`, `extracted_text_sha256`, and
`result`. Status distinguishes `completed`, `not_requested`, `not_applicable`,
`unavailable` and `failed`; this first version handles inapplicable heading findings
in the separate exclusion list rather than skipping a complete module.

`execution_status=complete` means the requested module executions completed. It
does not mean every possible scientific check was requested, that DOI metadata
was found, or that model interpretations are true. `partial` means an optional
requested calculation/module failed or was unavailable. Source mismatches,
invalid configurations/specifications and required extraction/reasoning failures
are hard errors. The CLI returns 0 for completed execution, 1 for a saved partial
report and 2 for invalid input/required processing failures. Findings alone do not
change the execution exit code. There is no aggregate scientific validity score.

Always read the result payloads and `coverage_gaps`, including raw-data checking,
code reruns, mathematical proofs, actual citation support, figures/supplements,
and independent expert validation. User-supplied arithmetic inputs are not
independently established to belong to the manuscript.

## Explicit quantitative inputs

```bash
sra review paper.md --study-type quantitative --statistics-spec examples/welch_t_example.json --scientific-spec examples/advanced_scientific_checks.json --out reports/quantitative
```

Each specification is capped at 1 MiB. Strict JSON rejects duplicate keys and
nonstandard constants. Supported tests and structured scientific checks are listed
by `sra capabilities`. The engines recalculate supplied values; they do not infer
the right test or reconstruct the manuscript's figures/data. A calculation's own
PASS/FAIL remains conditional arithmetic, separate from review execution status.

## External services are off by default

`--online` sends only extracted DOI identifiers to Crossref/DataCite, capped at 20
identifiers per review with a six-second timeout per request. The DOI result reports
its total found count and truncation; it does not verify cited-claim support.

For opt-in whole-extracted-text model assistance:

```bash
sra review paper.pdf --study-type quantitative --send-to-model --model YOUR_MODEL_ID --out reports/model
```

Set the provider key in `OPENAI_API_KEY` locally (or choose `--api-key-env`). The
complete extracted text goes to the explicitly configured provider. Exact source
quotation presence is checked; scientific relevance and interpretation are not
independently proven. Failed model work yields partial execution with an explicit
failed module, never a fabricated complete interpretation. Provider secrets and
response bodies are not exposed in module errors. There are no live model calls
in automated tests.

For PDF OCR use `--ocr-mode missing` or `all` and locally installed Poppler/Tesseract.
Default is `off`. `--visual-pages` additionally sends all rendered PDF page images
and requires `--send-to-model` and a vision-capable model. Existing text, page,
OCR and model-size limits still apply. Page-image observations remain unverified.

## Python and Node

```python
from sra.review import review_manuscript
report = review_manuscript("paper.md", study_type="computational",
                           disciplines=["computing", "physics"])
```

Python specifications may be JSON strings (preserving decimal spelling) or
JSON-serializable dictionaries. `review_document` composes an already extracted
`ParsedDocument`; its raw-file identity is caller-supplied unless created by
`load_document`. All modules use a detached copy of the same parsed snapshot.

```javascript
const sra = require('scientific-reasoning-auditor');
const result = await sra.reviewManuscript('paper.md', {
  studyType: 'computational', disciplines: ['computing', 'physics'],
  out: 'reports/paper', stdio: 'pipe'
});
const catalog = await sra.capabilities({ stdio: 'pipe' });
```

Install both adapters from a source checkout for these new functions. Set
`SRA_PYTHON` to the interpreter with that source installed. The Node adapter probes
the actual capabilities contract and gives an upgrade/source-install error if an
older engine lacks these commands, even if its package version is also 0.8.0.

## MCP

`get_review_capabilities` lists coverage. `review_manuscript` accepts content,
file format/encoding, study type, profile list and optional JSON specification
strings. It accepts no filesystem paths or remote URLs. Follow the existing
[MCP setup](../mcp_server/README.md). Model use requires explicit caller consent
and host enable/model/key settings; DOI network use requires caller and host
enablement. OCR and page images are unavailable in MCP.

The adapter retains its 20 MiB decoded upload, 1 MiB specification, 2 MiB output
and two-concurrent-analysis limits. `ok=true` means the adapter returned a report;
check `result.execution_status` and individual module statuses separately.

## Validation evidence and future extensions

The six examples in `examples/unified_review/` are synthetic behavior controls:
theoretical math, computational physics, clinical quantitative work, qualitative
social science, systematic review and an unknown field. They demonstrate routing,
source identity and schema/behavior contracts. They are not expert labels or a
measurement of real scientific accuracy.

New specialist packs require defined scope, meaningful positive/negative controls,
false-positive analysis and eventually independently adjudicated real-paper
evaluation. Additional profile names alone do not establish scientific capability.
