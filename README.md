# Scientific Reasoning Auditor

A research-software project for auditing the reasoning chain in scientific manuscripts:

**Hypothesis → assumptions → methods → data → analysis → inference → conclusion**

The software exposes reviewable reasoning risks with evidence locations and reproducibility metadata. It does not declare a manuscript scientifically true or false.

## Current status: v0.8.0

The v0.8.0 release includes the academic-writing, discipline-review, DOI, PMC benchmark and expanded-statistics tooling that was previously available only from the main branch, together with the hardening work described below. The PyPI package is version 0.8.0; the Node.js adapter is version 0.1.2 and is versioned independently — but it is not independent of the Python engine's *interface*: it refuses to drive an engine older than 0.5.2 and says which upgrade command to run, instead of failing later on a command that version does not have.

This release limits model API response memory use, validates reasoning-graph node/edge schema and endpoint types, rejects non-standard JSON constants in imported semantic reviews, and expands the reproducibility source hash to selected runtime, test, workflow, schema, adapter and build inputs. Statistical reports now state that pooled-SD Cohen's d and classical Hedges' g assume a common within-group variance model and are not heteroskedasticity-adjusted. CI covers Python 3.11 and 3.12, uses Node.js 24-compatible GitHub Actions, and pins each external action to a verified full commit SHA.

### Detailed full-paper reading, explanation, and scientific critique (repository main)

The `paper-review` command sends **every extractable character** of a manuscript to an explicitly configured OpenAI-compatible model in ordered, non-overlapping chunks, checks that source quotations actually occur in the corresponding chunk, and produces a whole-paper synthesis plus a section-by-section scientific criticism. It also includes the project's independent rule-based warning signals. A failed chunk, invented quote, invalid model response, or context/size limit produces an error rather than a falsely "complete" review.

```bash
# Install the source checkout; this feature is not yet guaranteed in published PyPI/npm versions.
python3 -m pip install -e ".[pdf,statistics]"

# Explicit network/model use. The document text is sent to this configured API.
export OPENAI_API_KEY="YOUR_KEY"
sra paper-review manuscript.pdf --model YOUR_MODEL_ID --out reports/paper-review

# Scanned PDF pages are OCR-processed locally by default when the text layer is thin.
# Requires the system programs pdftoppm and tesseract with the indicated languages.
sra paper-review manuscript.pdf --model YOUR_MODEL_ID --ocr-mode missing --ocr-languages eng+tur --out reports/paper-review

# To OCR every rendered PDF page including pages with native text/figure labels:
sra paper-review manuscript.pdf --model YOUR_MODEL_ID --ocr-mode all --out reports/ocr-all

# Optional page-image understanding. This uploads *all* rendered PDF pages in
# addition to extracted text; the selected model MUST support vision/image_url.
sra paper-review manuscript.pdf --model VISION_CAPABLE_MODEL --visual-pages --out reports/visual-review

# For long manuscripts, increase chunk size (2,000–20,000 extracted characters).
sra paper-review manuscript.md --model YOUR_MODEL_ID --chunk-chars 20000 --out reports/paper-review
```

Outputs: `reports/paper-review.json` and `reports/paper-review.md`. JSON contains the source SHA-256, extracted-text SHA-256, page-level extraction methods, native/OCR text counts, page spans and hashes, physical-page text coverage, per-chunk analyses, severity-ranked critiques with verbatim source quotations, optional model-generated page-image observations, model interaction hashes and independent rule-based screening findings. The model is called **once per text chunk, plus one synthesis call, plus one per PDF page when `--visual-pages` is enabled**. The client requires `finish_reason=stop`, an attributable response model identity, and bounds output to 4,096 tokens per request. Actual cost and provider limits vary. A provider may reject the JSON response-format setting or the `max_tokens` parameter; such unsupported combinations fail instead of reporting false success.

**Limitations:** Local Tesseract OCR can recover text from image-only/scanned pages. OCR does **not** scientifically interpret plots, diagrams, equations, tables, colors or graphical relationships. `--visual-pages` requests a vision model's image interpretation but does not establish scientific truth or verified figure comprehension. `extracted_text_coverage=complete` means only *all extracted characters were submitted*; it is not whole-PDF scientific completeness. Page text coverage, OCR pages and unextractable pages are reported separately. There is a 20 MiB paper input limit, 480,000 extracted characters, 40 text chunks, 100 OCR pages, and 30 vision pages. Any limit causes explicit failure instead of silent truncation. The OCR programs must be installed locally and requested Tesseract language packs available. Independent domain experts, source/figure inspection and reanalysis of original data remain necessary. All extracted manuscript text (and, only with `--visual-pages`, all rendered PDF page images) is sent to the configured model provider; confirm confidentiality, permission and retention policies before use. The repository's automated tests use controlled fake-model responses; they are not a live-provider scientific validity benchmark.

For a **real-provider** opt-in smoke test using only a public-shareable synthetic manuscript, set an API key locally and run:

```bash
PYTHONPATH=src python tools/verify_live_model_api.py \
  --model YOUR_MODEL_ID --confirm-send-synthetic
```

This makes **two actual API calls** (one text chunk plus synthesis), verifies provider response completion and model identity, validates the quote and full-text coverage, and prints metadata without secrets or manuscript content. It requires a valid provider key and may incur charges; it is intentionally not run in CI. Without `OPENAI_API_KEY` it returns `LIVE_API_NOT_TESTED` and makes no request. **A passing live smoke test does not prove scientifically correct model interpretations.** The project CI separately runs a genuine locally rendered image-only PDF OCR test on a synthetic three-page document with Tesseract and Poppler, without model API access.

Node.js adapter users can call `sra.paperReview('manuscript.md', { model: 'YOUR_MODEL_ID', out: 'reports/paper-review' })` with a Python engine installed from this source checkout.

### Implemented

- Read Markdown and UTF-8 text manuscripts; optional PDF text extraction.
- Preserve repeated section headings, ignore fenced code blocks during section/heuristic extraction, and conservatively detect standard standalone headings in plain text/PDF extraction.
- Apply negation-aware causal/directional screening and avoid treating a cited prior randomized trial as proof that the current study was randomized.
- Record the raw manuscript-file SHA-256 and a separate SHA-256 of the exact extracted/parser text (so PDF and BOM inputs retain both identities), plus a scoped source hash (runtime Python source, schemas, tests, Node adapter sources, GitHub Actions workflows, examples and package/build metadata when running from a repository), file size, parser details, ruleset/configuration hashes, Python/runtime details and an environment fingerprint. The manifest lists every relative file path included in the hash. Source archives include the selected tests, workflows, schemas, examples and Node adapter inputs so their full source inventory can be reproduced. CI compares every declared sdist provenance file byte-for-byte with the checkout, verifies the wheel's exact Python source inventory and metadata, installs the wheel with pip in an isolated temporary virtual environment, checks the installed CLI entry point, and runs an audit using only the installed package.
- Attach line and section references to extracted Discussion/Conclusion claims and candidate result passages.
- Identify conclusion claims for which no lexical result candidate is found.
- Flag possible opposite-direction statements between Results and Conclusion (for example, increased versus decreased for overlapping topics).
- Exclude `higher dose` and `lower-dose` treatment-arm labels as standalone outcome directions while retaining actual increase/decrease predicates.
- Flag a repeated, explicitly formatted **rate ratio + p-value** when its reported **95% CI bounds differ**. This is a narrowly scoped reporting-consistency screening rule, not an independent reanalysis or proof of an error.
- Flag causal conclusion language when Methods text describes an observational or non-randomized design.
- Avoid attributing observational designs of reviewed papers to the authors of an explicitly identified methodological / meta-research review, unless the review itself explicitly reports its own observational design.
- Flag selected absolute/conclusive wording.
- Flag a manuscript that reports three or more p-values and never mentions a multiplicity adjustment: no statement of a correction, a test family, or a procedure that corrects by itself. The signal is text-only and says so; it cannot tell a pre-specified single test from exploratory tests, so it asks for adjudication.
- Flag an independent-samples test quoted for a design described as paired, matched, repeated-measures or before/after, unless the manuscript also names a paired test. The check points at both sentences rather than deciding which analysis was run.
- Flag a sentence whose 95% confidence interval and p-value disagree about the null: an interval that contains the null with p below 0.05, or an interval that excludes it with p at or above 0.05 (ratios use 1 as the null). Descriptive intervals, such as a mean age with a CI, are not compared with a p-value.
- Flag a sentence whose reported mean falls outside its own 95% confidence interval.
- Flag a p-value that cannot be a probability in the printed form: `p = 0.000` (rounded to zero), `p = 1.4`, `p > 1`, or a negative p.
- Flag a dispersion or sample size that cannot exist: a negative standard deviation or standard error, or `n = 0`.
- Flag three or more groups compared with pairwise tests only, when no omnibus test (ANOVA, Kruskal-Wallis, mixed model) and no adjusted contrast (Tukey, Dunnett, Bonferroni, FDR) is named.
- Recognise the languages that publish most of the literature, not just English and Turkish: section headings, increase/decrease wording, absolute claims, association and causal verbs, multiplicity corrections, group counts, rate measures, paired designs and test names are listed for Spanish, Portuguese, French, German, Italian, Dutch, Russian, Polish, Indonesian, Arabic, Hindi, Chinese, Japanese and Korean ([src/sra/multilingual.py](src/sra/multilingual.py)). Scripts without word boundaries (CJK, Devanagari) are matched as phrases, and single characters broad enough to match ordinary prose were deliberately left out.
- Read PDF text in layout mode, so a table row stays on one line with its cells separated by spaces, and read the numbers out of rows whose header names n, mean, SD, SE or p. Each such cell becomes the statement the prose rules already understand (`SD = -1.2`, `p = 0.000`), reported against the table row and column it came from.
- Recalculate a two-independent-group Welch t-test from supplied group means, sample standard deviations and sample sizes; compare reported mean difference, t statistic, degrees of freedom and two-sided p-value within explicit tolerances.
- Recalculate a two-sided two-proportion z-test from a 2x2 event-count table; compare reported proportions, difference, z statistic and p-value within explicit tolerances, and report a pooled normal approximation with an unpooled Wald 95% confidence interval.
- Produce an explicit reasoning graph with claim, evidence, method, assumption, limitation, inference and grouped document-context nodes, source locations, relation edges and a graph fingerprint. Shared context nodes avoid method/limitation-to-inference Cartesian edge growth.
- Validate complete graph objects through the strict graph validator, including supported schema version, fingerprint algorithm, canonical node/edge metadata, allowed top-level fields, deterministic edge IDs, endpoint types, dangling references, duplicate IDs and dependency cycles. The lower-level node/edge validator remains available for structural-only checks. Full validation checks required node/edge fields and types, the stored derived validation result, and the graph fingerprint; the derived validation result itself is intentionally excluded from the fingerprint and is recomputed. Graph fingerprints include schema version, fingerprint algorithm, schema metadata, nodes and edges; report inferences without lexical evidence.
- Create source-bound semantic-review 1.4 templates for external LLMs/agents using the original manuscript text (required by the Python template API); the text is checked against the extracted-text digest recorded in the audit manifest, while the raw-file digest remains separate for PDF/BOM inputs. The graph schema and fingerprint algorithm are bound explicitly; the graph's manuscript SHA-256 must equal the audited manuscript SHA-256 when templates are built or reviews are imported. Importers continue to accept review schemas 1.0–1.3 when their fingerprint matches either the current graph or the historical v1.1 fingerprint for unchanged node/edge data; changed graph content is still rejected.
- Require explicit causal-assumption review even when a lexically similar assumption sentence was extracted; lexical overlap no longer clears the causal assumption gap.
- Produce JSON and Markdown audit reports plus a machine-readable statistical verification result.
- Run tests using Python's standard library plus the optional SciPy statistics extra.
- Check academic writing structure, citations/reference-list candidates, placeholders and potentially overconfident wording using a separate advisory report.

### Interpretation rules

- A finding is a review signal, not an automatic verdict.
- Lexical overlap is not semantic entailment and does not prove that evidence supports a claim.
- A missing lexical match is not proof that a conclusion is unsupported; relevant evidence may be paraphrased or located elsewhere.
- A possible direction conflict may be caused by subgroup definitions, recoding, different endpoints or sentence-extraction errors.
- A repeated rate ratio with a differing CI may still refer to different endpoints, populations or statistical models; the check requires explicit `rate ratio …; 95% CI …; p = …` formatting, and misses other estimate types or layouts. Human adjudication remains necessary.
- Observational wording does not by itself invalidate a causal inference; causal identification may be justified by design and assumptions not detected by these rules.
- Multiplicity and design/test signals are wording checks: a correction stated in prose, or a paired test named anywhere, clears them, and a correction applied but never mentioned is invisible to them.
- The interval checks are sentence-scoped: numbers reported in separate sentences, in a table, or in a figure are not compared, and an interval that belongs to a different model than the p-value cannot be detected as such.
- The multilingual lists were written from standard terminology and are checked by tests that every term reaches its rule; they have not been reviewed by native speakers, and a rule whose vocabulary is missing from a language silently does nothing there.
- Table reading needs a header naming a statistic the audit understands and one value per cell: merged cells, sub-headers, footnotes and numbers inside figures are not read, and a table whose caption states the sample size is not joined with the column.
- The plausibility checks read single sentences: `p = 0.000` may be a rounding style rather than an error, and a group count with an omnibus test named in a different sentence will be flagged because the sentence-scope rule cannot join them.
- Welch verification checks arithmetic conditional on supplied summary statistics. It does not validate the raw data, study design, assumptions or choice of statistical test. Pooled-SD Cohen's d uses a common within-group variance reference and is not heteroskedasticity-adjusted; the classical Hedges' J correction is derived under a normally distributed, two-independent-group model with a common variance.
- No finding does not mean that the paper is logically valid.

A synthetic rule ablation ([docs/RULE_ABLATION.md](docs/RULE_ABLATION.md)) measures which rules actually fire on the cases that plant them, and which fire where nothing was planted.

Every finding code is listed in [docs/CHECK_INVENTORY.md](docs/CHECK_INVENTORY.md) with what it detects, what it cannot detect and where its false positives come from; a test fails the build when a rule and its inventory row drift apart.

## Deterministic formal logic with Z3 (source checkout)

The optional, MIT-licensed [Z3 engine](https://github.com/Z3Prover/z3) checks
explicit Boolean and linear integer/real formulas. Findings go to a separate
user report; the manuscript is read-only.

```bash
python -m pip install -e ".[logic]"
sra verify-logic examples/logic_boolean.json --out reports/logic
sra verify-logic examples/logic_arithmetic.json --out reports/arithmetic
```

Reports distinguish `VERIFIED`, `REFUTED` and `UNDETERMINED` conditional on the
provided assumptions. Inconsistent premises never prove every claim. Fixed solver
settings, resource budgets and a report fingerprint support repeatability within
the same solver/adapter/platform. Z3 does not automatically interpret a paper's
prose or establish empirical truth. See [input format, source binding and limits](docs/DETERMINISTIC_LOGIC.md).

## Unified cross-disciplinary review (source checkout)

Use one source-bound report for reasoning, writing, selected discipline cues,
DOI metadata, supplied quantitative checks and optional model interpretation:

```bash
sra capabilities
sra review examples/unified_review/theoretical_math.md --study-type theoretical --out reports/theory
sra review examples/unified_review/computational_physics.md --study-type computational --discipline computing --discipline physics --out reports/simulation
```

Common screening is usable with manuscripts from other fields; specialist cues
remain limited to the six listed profiles. Theoretical/narrative papers do not
inherit empirical Methods/Results-heading warnings without an explicit exclusion
record. Reports distinguish completed, unrequested, unavailable and failed work;
execution completion is never a scientific validity score. Network/model use is
off by default. These commands and new Node/MCP entry points require the source
checkout; published package versions are not guaranteed to include them.

See [scope, examples, interfaces and limitations](docs/CROSS_DISCIPLINARY_REVIEW.md).

## Optional MCP tools for ChatGPT and Codex

A separate Model Context Protocol (MCP) adapter provides nine bounded tools for
scientific manuscript reasoning, academic writing, DOI checks, structured
statistics, scientific validation, and opt-in external-model paper review.
It supports local stdio and token-protected Streamable HTTP; it does not
change the core SRA rules. Public-directory submission requires additional
OAuth, deployment and OpenAI review steps.

See [MCP setup, privacy, security and tests](mcp_server/README.md).

## Install

Install the published release from PyPI:

    python -m pip install "scientific-reasoning-auditor[statistics]"

For PDF input:

    python -m pip install "scientific-reasoning-auditor[pdf,statistics]"

To work from source:

    git clone https://github.com/Furox-Art/scientific-reasoning-auditor.git
    cd scientific-reasoning-auditor
    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -e ".[statistics]"

For PDF input:

    python -m pip install -e ".[pdf,statistics]"

## Use from Node.js / npm

The npm package is a small Node.js adapter around the Python engine; it is not a separate JavaScript reimplementation. Install the Python engine explicitly first (Node.js does not download or install it):

    python -m pip install "scientific-reasoning-auditor[statistics]"

Then install the Node.js adapter in your project:

    npm install scientific-reasoning-auditor

The npm package requires Node.js 18+ and Python 3.11+ with the Python package available to the selected interpreter. It has no npm runtime dependencies and performs no network requests or package installation itself. Set `SRA_PYTHON` to the Python executable when the engine is installed in a non-default environment. For safety, the Node adapter launches Python in isolated mode (`-I`) and clears inherited/per-call `PYTHONPATH`, excluding user-site packages and untrusted working-directory modules. Install the engine in the selected interpreter or virtual environment rather than relying on `PYTHONPATH` or `pip install --user`.

Use the CLI after installation:

    npx sra audit examples/sample_manuscript.md --out reports/sample
    npx sra review-template examples/sample_manuscript.md --mode single
    npx sra verify-stats examples/welch_t_example.json
    npx sra writing-audit examples/academic_writing_sample.md --genre original-research

Or call it from JavaScript:

    const { audit, createReviewTemplate, verifyStats, writingAudit } = require("scientific-reasoning-auditor");

    await audit("manuscript.md", { out: "reports/manuscript" });
    await createReviewTemplate("manuscript.md", { mode: "parallel" });
    await verifyStats("welch-input.json");
    await writingAudit("manuscript.md", { genre: "original-research", abstractMaxWords: 250 });

The functions return `{ code, signal, stdout, stderr }`. By default command output is inherited from the current terminal; pass `stdio: "pipe"` to capture output. The `reviewModel` function also accepts `model`, `baseUrl`, `apiKeyEnv`, `timeout` and `out` options. The Python engine remains the source of truth for audit behavior and output schemas.

## npm releases with OIDC Trusted Publishing

After the initial npm release has created the package, configure a GitHub Actions Trusted Publisher in npm package settings with owner Furox-Art, repository scientific-reasoning-auditor, workflow filename npm-publish.yml, and no environment. Allow direct npm publish. The workflow uses GitHub-hosted runners, Node.js 24+, npm 11.5.1+, and the id-token: write permission; it stores no npm publish token.

To publish a subsequent npm version, update package.json, commit the change, and push a matching tag such as npm-v0.1.2. The workflow runs Node tests and npm pack --dry-run before publishing via OIDC. npm currently requires a package to exist before its Trusted Publisher can be configured, so the first package publication must be completed once using npm account verification.

## Run manuscript audit

    sra audit examples/sample_manuscript.md --out reports/sample

The command writes reports/sample.json and reports/sample.md. JSON includes the reproducibility manifest; Markdown is the human-readable review.

A synthetic document with deliberately planted inference and direction-conflict signals is provided:

    sra audit examples/logic_review_demo.md --out reports/logic-review-demo

## Build a reasoning graph and request semantic review

Run an audit to include a graph in the JSON and Markdown reports:

    sra audit examples/logic_review_demo.md --out reports/logic-review

The [review template JSON Schema](schemas/semantic-review.schema.json) accepts unfilled values; completed submissions must additionally conform to the [completed-review JSON Schema](schemas/semantic-review-completed.schema.json).

Create a JSON template and choose the review mode:

    sra review-template examples/logic_review_demo.md --mode single --out reports/semantic-review-single.json
    sra review-template examples/logic_review_demo.md --mode parallel --out reports/semantic-review-parallel.json

The single mode (default) prepares the whole review for one model. It can now call an OpenAI-compatible Chat Completions endpoint directly. The parallel mode remains an external agent-orchestrator workflow; the user selects the mode for each run. The Python CLI does not pretend to launch ChatGPT parallel agents.

For a direct single-model API review, set the API key in the environment and run:

    export OPENAI_API_KEY="your-api-key"
    sra review-model examples/logic_review_demo.md --model "your-model-id" --base-url "https://api.openai.com/v1" --out reports/semantic-review-completed.json

The command also writes a .provenance.json sidecar containing hashed request/response data, selected model, endpoint and any provider fingerprint; it does not store the API key. Temperature zero does not guarantee identical provider output. The command sends the complete manuscript and source-bound template to one model, parses its JSON response, then validates the returned review against the manuscript and reasoning graph. Any OpenAI-compatible Chat Completions endpoint can be configured with --base-url and --api-key-env. Remote endpoints must use HTTPS so the API key is encrypted in transit; plain HTTP is accepted only for localhost or IP loopback addresses (127.0.0.0/8 and ::1) for inference servers, and these local clear-text requests bypass environment-configured HTTP proxies. URLs containing embedded credentials or query/fragment delimiters are rejected, and HTTP redirects are not followed to prevent forwarding authorization headers to another host. Statistical inputs that underflow or overflow the supported floating-point range are rejected with a validation error rather than producing silently rounded or non-finite report values; the Welch and pooled-standard-deviation calculations use scaled formulas to preserve valid extreme-range inputs. Statistics JSON input rejects non-standard NaN/Infinity constants. The API key is read from the environment and is not written to reports. Model/API charges and provider data-retention policies are controlled by the provider.

For parallel mode, export the template and pass it to the connected external parallel-agent orchestrator. Each agent must receive the full manuscript and its assigned assessment subset; merge all results by inference ID before importing. The current CLI does not launch the ChatGPT UI-based parallel-agent tool.

Give the template and full manuscript to the selected model or external orchestration layer for passage-grounded assessment. Fill every assessment with a relation (entailed, partially_supported, contradicted, not_supported, or unclear), confidence, rationale and exact source quotations where applicable. Then import the completed file:

    sra audit examples/logic_review_demo.md --semantic-review reports/semantic-review-completed.json --out reports/semantic-reviewed

The template includes a complete source-bound catalog of Results evidence-node IDs, passages and locations. The importer checks the manuscript hash and reasoning-graph fingerprint, requires graph-linked support IDs or explicit reviewer-selected Results evidence IDs, and validates the existence, type and source quotation provenance of selected nodes. Reviewer-selected evidence provenance is checked, but its semantic relevance is not proven. Current-schema quotations must be at least 20 characters and match both the manuscript and selected node text. The importer also enforces the review contract and UTC timestamps. It does not prove the external reviewer’s semantic judgment; expert adjudication remains necessary. The application can call one OpenAI-compatible model in single mode. Parallel-agent execution remains an external orchestration step.

## Academic writing review

Run a separate, offline academic-writing checklist without changing the manuscript:

    sra writing-audit examples/academic_writing_sample.md --genre original-research --abstract-max-words 250 --out reports/writing-review

This creates a structured JSON report and a readable Markdown report. Review prompts include:

- Recognizable section headings (English/Turkish), with an optional original-research checklist.
- Abstract word count; word limits apply **only if configured** for the target journal.
- Numeric references such as [1] and [2-3], and simple author-year references such as (Smith, 2020) / Smith (2020), matched conservatively to entries in a References/Kaynakça section.
- Unmatched citations, unrecognized reference formats, uncited entries, duplicate numbers/author-year keys, editing placeholders, and potentially absolute wording, with source line numbers where available.

The default genre is general, so non-IMRaD manuscripts are not automatically treated as incomplete. Warnings are advisory and do not produce a nonzero process exit code. Citation style support is limited and matching an author and year is **not** proof of bibliographic identity or support for a scientific claim. This tool is **not** a full grammar corrector, plagiarism detector, DOI validator, copyeditor, or substitute for journal-specific and expert review. No source content is sent to any external API.

### Python API migration note for v0.5.2

Direct Python callers must now provide the manuscript text when creating a source-bound semantic-review template. The caller-supplied source_sha256 override was removed: the implementation verifies the supplied text against reproducibility_manifest.input.extracted_text_sha256, while the audit report separately retains the raw-file SHA-256 (important for PDF and UTF-8 BOM inputs). Existing CLI commands are unchanged.

~~~python
from sra.audit import audit_file
from sra.document import load_document
from sra.semantic_review import build_semantic_review_template, validate_semantic_review

path = "manuscript.md"
document = load_document(path)
report = audit_file(path).to_dict()

template = build_semantic_review_template(report, source_text=document.text)
# After the external reviewer completes the template:
result = validate_semantic_review(completed_review, report, document.text)
~~~

Calls that previously used build_semantic_review_template(report) or passed source_sha256 must migrate to this source-text-based API. This is an intentional Python API compatibility change in v0.5.2; an external hash override is not accepted as proof of the supplied text's identity. Older PDF audit reports created before manifest schema 1.4 do not contain an extracted-text digest and must be regenerated from the original PDF before source-verified template creation or review import.

## Independently verify a Welch t-test

Create a JSON file with two groups' mean, sample SD and n, plus the reported statistics to compare. Example:

    sra verify-stats examples/welch_t_example.json --out reports/welch-verification.json

Each reported value is compared with the independently calculated value using the configured absolute tolerance. Without an explicit tolerance, the verifier uses half the last displayed decimal place; field-specific or default overrides can be supplied in the JSON input. A mismatch returns a non-zero exit code. Report p-values as positive values in (0, 1], not as zero. The command supports the statistical tests listed below. For the Welch test it also reports pooled-SD Cohen's d and classical Hedges' g; these effect-size estimates use a common within-group variance reference and are not heteroskedasticity-adjusted. The classical Hedges' J small-sample correction is derived under a normally distributed, two-independent-group model with a common variance. Interpret them cautiously when group variances differ substantially, even though the Welch test itself permits unequal variances. Input JSON rejects duplicate object keys (including nested keys) and non-standard numeric constants rather than silently accepting ambiguous reported values.

## Expanded validation tools

### Five independently calculated statistics

The `sra verify-stats` command now supports:

| `test` | Inputs | Calculated summary |
| --- | --- | --- |
| `welch_t` | Two independent groups (mean, sample SD, n) | Welch t, df, two-sided p, 95% CI |
| `one_sample_t` | `sample` (mean, sd, n); optional `mu0` | Student one-sample t, df, p, 95% CI |
| `paired_t` | `differences` (paired-difference mean, sd, n); optional `mu0` | Paired t on differences, df, p, 95% CI |
| `chi_square_2x2` | `table`: 2 x 2 nonnegative integer counts | Pearson chi-square, df, upper-tail `p_value`, expected counts |
| `fisher_exact_2x2` | `table`: 2 x 2 counts | Fisher two-sided p, finite sample odds ratio |
| `two_proportion_z` | `table`: 2 x 2 event counts (rows = groups, columns = event/non-event) | Pooled z, two-sided p, difference in proportions, unpooled Wald 95% CI |

    sra verify-stats examples/extended_statistics.json --out reports/stats.json

For paired t, supply **within-pair differences**, not two independent
groups' summary statistics. The Pearson chi-square test uses no Yates
correction and emits a caution when expected cell counts are below five.
The two-proportion z-test uses a pooled-variance normal approximation and
emits a caution for sparse expected counts; its confidence interval is an
unpooled Wald interval without continuity correction.
No result confirms statistical-test suitability, input validity or scientific
causality. `PASS` compares only explicitly reported statistics.

### Academic grammar, style and study-design reporting cues

    sra writing-audit examples/academic_writing_sample.md --style-language en --design observational --out reports/writing

Source-located, conservative editing suggestions include repeated words,
selected English article agreement and modal verb constructions, Turkish
spelling patterns, concision suggestions and long lines. The tool never
automatically edits scientific claims. It is not a full grammar corrector.
`--style-language` accepts `en`, `tr` and `none`.

The optional `--design` profiles are `clinical-trial`, `observational`,
`systematic-review` and `computational`. They inspect short reporting cues
inspired by CONSORT 2025, STROBE, PRISMA 2020 and project-specific
computational reproducibility, respectively. Keyword detection is neither
adherence to the official checklist nor evidence of study quality.

Official references:
- CONSORT 2025: https://www.consort-spirit.org/
- STROBE: https://www.strobe-statement.org/
- PRISMA 2020: https://www.prisma-statement.org/prisma-2020

### Expanded academic grammar and field review

The offline writing checker now includes additional, conservative
English/Turkish grammar and academic phrasing patterns. Suggestions do
**not** change the manuscript and should be judged in context.

For broader spell/grammar detection, connect to a **separately installed
and running LanguageTool local HTTP server** on your own computer
([setup instructions](https://dev.languagetool.org/http-server)):

```bash
sra writing-audit examples/academic_writing_sample.md \
  --style-language en --grammar-engine local-languagetool \
  --grammar-port 8081 --out reports/writing-local
```

This mode is explicitly opt-in. The connector sends non-reference prose
without fenced code to `http://127.0.0.1:8081/v2/check` using HTTP POST.
Requests cannot target external hosts or inherited proxies; redirects are
disallowed. The server is **not downloaded, started or installed** by SRA.
A missing local server produces an explicit error. Text/reply sizes are
bounded, suggestions preserve source-line provenance and Unicode-safe
offsets, and no correction is automatically applied. The public
LanguageTool endpoint is never used.

Six additional **discipline-specific** reporting evidence profiles operate
locally: `clinical`, `animal`, `physics`, `chemistry`, `computing`,
`social-science`. Each profile contains several source-section-scoped
questions, matching multiple required cues *in one paragraph*.
Statuses are textual evidence candidates, partial cues or undetected cues;
none means scientifically correct, guideline-compliant or missing information.

```bash
sra writing-audit examples/physics_domain_demo.md --discipline physics --out reports/writing-physics
sra domain-review examples/physics_domain_demo.md --discipline physics --out reports/physics-evidence.json
sra domain-template examples/physics_domain_demo.md --discipline physics --out reports/physics-template.json
sra domain-validate examples/physics_domain_demo.md reports/human-completed.json --discipline physics --out reports/physics-reviewed.json
```

Two genuinely qualified independent experts must complete every assessment
with reasoned verdicts and source quotations before the last command can
accept a review. Acceptance checks only review completeness, document and
ruleset hashes, and quotation provenance; it **does not verify experts or
scientific accuracy**. No external human expert adjudication was performed
for these software changes. Read [the full domain expert protocol](docs/DOMAIN_EXPERT_PROTOCOL.md).

This layer draws on the original [CONSORT 2025](https://www.bmj.com/content/389/bmj-2024-081123),
[ARRIVE 2.0](https://arriveguidelines.org/arrive-guidelines),
[NIST measurement uncertainty](https://www.nist.gov/itl/sed/topic-areas/measurement-uncertainty)
and [STROBE](https://www.strobe-statement.org/) guidance where applicable,
but is **not a complete implementation** of these standards.

### DOI and bibliographic metadata

Offline DOI extraction does not contact third parties:

    sra doi-check examples/doi_metadata_demo.md --out reports/doi-offline.json

Explicit `--online` uses official Crossref metadata first and DataCite when
Crossref has no record:

    sra doi-check examples/doi_metadata_demo.md --online --out reports/doi-online.json

Only DOI identifiers are transmitted. The report indicates registry presence,
title, first author and year when available, with optional *weak* token
overlap against the reference line. Neither DOI registration nor word overlap
establishes that the source supports any manuscript claim. Registry outages
are reported as unverified and absent DOI records are never called proof
of a fabricated citation.

Official API documentation:
- Crossref: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- DataCite: https://support.datacite.org/docs/rest-api

### Real published papers and independently adjudicated annotations

The reproducible PMC BioC runner processes a configured allowlist of real
papers. It stores source URLs, identifiers, SHA-256 hashes, counts and
finding-code names, but **does not redistribute full article texts**:

    sra benchmark-pmc benchmarks/pmc_real_papers.json --online --limit 12 --out benchmarks/pmc_smoke.json

The corpus and method exercise the tool against independent external
manuscript texts; they are **not an expert-labeled scientific accuracy
benchmark**. Runs can handle a configurable 1–200 article allowlist per
invocation. Respect publisher copyright and the PMC BioC service conditions:
https://www.ncbi.nlm.nih.gov/research/bionlp/APIs/BioC-PMC/

A separate command evaluates *complete* blinded two-reviewer expert labels
against frozen per-paper automated outputs, with source-hash matching,
confusion matrices and Wilson 95% intervals:

    sra evaluate-labels benchmarks/pmc_smoke.json experts/adjudicated.json --out reports/validation.json

No external expert labels are bundled or fabricated. Thus no sensitivity,
specificity or independent scientific performance score is available yet.
See [independent validation protocol](benchmarks/VALIDATION_PROTOCOL.md).

Before evaluation, build a prediction-free review pack and merge the two
independent worksheets with third-party disagreement decisions:

    sra validation-pack benchmarks/pmc_smoke_20261105.json \
      --reviewer reviewer_1 --reviewer reviewer_2 \
      --code potential_overclaim --code references_section_missing \
      --manual benchmarks/CODING_MANUAL_20261106.md \
      --out-dir /external/validation-20261106 --online

    sra adjudicate-labels benchmarks/pmc_smoke_20261105.json \
      reviewer_1.json reviewer_2.json adjudications.json \
      --out final-labels.json

The frozen pilot plan is
[benchmarks/PREREGISTRATION_20261106.md](benchmarks/PREREGISTRATION_20261106.md).
The commands verify hashes, coverage and declared roles only; they cannot
verify reviewer identity, qualifications, independence or actual blinding.

## Measured academic-language limitations and blinded expert review (main only)

**Real human-annotated evidence:** we evaluated all 200 examples in the
arXivEdits 2022 human-annotated scientific revision **test split** (69 papers),
with the original file and its SHA-256 frozen. On this edit-enriched dataset
the current *offline English language rules* detected **4 of 136**
human-labelled language-edit revision pairs (**2.94%** conditional recall).
The system flagged only six pairs in total. This reveals a real and serious
coverage limitation; it is **not** a reliable estimate of full-manuscript
grammatical correctness. The 64 comparison sentences were revised for
other stated reasons, not independently certified as error-free.

Download the version-pinned dataset separately and reproduce with:

    sra benchmark-language /tmp/arxivedits-human-test.csv --expected-sha256 6541dce4c7f82019e8f24dc0259a1a04e20dd853d87b465adeb1febc2cbf0220 --max-rows 200 --out reports/language-test.json

The repository distributes **only aggregate statistics**, not third-party
scientific writing and copyright-encumbered annotations. See the
[observed benchmark report](benchmarks/arxivedits_style_test_20261105.json)
and [full methodology and caveats](docs/ACADEMIC_LANGUAGE_BENCHMARK.md).
The optional LanguageTool service was **not benchmarked** here.

**Specialist review strengthened:** the domain expert template is now
**blinded by default** (it contains questions, but no prior automatic
predictions or extracted candidate paragraphs). Review validation requires
the *same two declared reviewer IDs* across all items. Outputs provide
item-level comparison against adjudicated judgments, raw reviewer
agreement and Cohen's kappa (null when undefined). None confirms reviewer
identity, genuine independence, scientifically correct judgments or
guideline compliance.

    sra domain-template examples/physics_domain_demo.md --discipline physics --out reports/blind-template.json
    sra domain-validate examples/physics_domain_demo.md reports/real-reviewed.json --discipline physics --out reports/verified-review.json

When two or more **genuinely reviewed manuscripts** are available, their
structured outputs can be aggregated by discipline and fixed ruleset:

    sra domain-aggregate reports/review-1.json reports/review-2.json --out reports/domain-cohort.json

The aggregator checks for duplicate paper hashes, mismatched rule sets and
inconsistent confusion matrices. It reports conditional retrieval
statistics and simple Wilson intervals; these intervals do not account for
clustering or selection bias. No real external domain experts were recruited
for this change, and no domain-wide scientific accuracy numbers can be
claimed yet. Refer to [the expert protocol](docs/DOMAIN_EXPERT_PROTOCOL.md).

## Scientific validation roadmap

The project is split into separate assurance layers. A rule-based text scan must not be presented as full scientific validation.

1. **Reasoning graph** — extend the current graph from rule-extracted candidates to validated, semantic claim/evidence/assumption/method/inference relations with provenance.
2. **Quantitative verification** — extend beyond Welch tests to supported tests, effect sizes, confidence intervals, model-fit statistics and data-level recalculation.
3. **Mathematical verification** — symbolic/numeric checks of equations, dimensions, boundary conditions and derivation steps where machine-checkable.
4. **Code and data reproducibility** — controlled execution of supplied analysis code, dataset fingerprints, environment lockfiles, logs and output comparison.
5. **Literature and citation verification** — resolve references and verify whether cited sources support the exact claims.
6. **Specialist review** — task-specific expert analysis, disagreement tracking and human adjudication.
7. **Benchmarking** — curated positive/negative examples, false-positive/false-negative rates, calibration and regression tests.

## Published-manuscript regression pilot (development branch only)

Using the published, open-access 2025 RECOVERY ventilatory-support paper (PMCID
[PMC11872607](https://pmc.ncbi.nlm.nih.gov/articles/PMC11872607/),
DOI [10.1016/j.eclinm.2025.103080](https://doi.org/10.1016/j.eclinm.2025.103080)),
the main Results text reports a rate ratio 0.87 with a 95% CI of
0.64–1.18 (p = 0.37), while the paper's *Added value of this study* section
prints 0.64–1.33 with the same rate ratio and p-value. This observable
inconsistency is a **review signal**, not proof that the underlying analysis is
incorrect. The new `statistics.repeated_rate_ratio_ci_conflict` check
detects that specific class of repeated-value mismatch. The
`reasoning.directional_contradiction` heuristic is also less likely to treat
higher/lower *dose labels* as an effect-direction reversal.

Positive and negative unit tests in `tests/test_published_paper_regressions.py`
reproduce both problems and guard against a matching CI, distinct estimates or
p-values, and manuscript code fences. A published-paper pilot is not an
expert-labeled representative validation corpus. Real-world precision, recall,
false-positive and false-negative rates remain **unknown**. Existing semantic
review schema versions 1.0–1.3 are preserved; direction-rule version changes
from 3 to 4 in the reproducibility manifest, and a new CI-rule version 1 is
recorded.

### Methodological-review safeguard (published-paper pilot)

The 2021 BMJ Open paper [PMC8141434](https://pmc.ncbi.nlm.nih.gov/articles/PMC8141434/)
reviews causal language in 60 published observational articles. The manuscript
describes its own work as a methodological study (research on research), rather
than asserting that the authors measured an exposure-to-outcome effect in a
patient cohort. A narrow safeguard now prevents treating the *reviewed papers'*
observational design as this manuscript's study design. This check is supported
by negative controls for meta-research plus positive controls for an actual
observational cohort. The rule does **not** establish whether other causal
statements elsewhere in this paper are valid; the code still produces heuristic
flags requiring adjudication. The causal-design rule version increases to 4.

## Advanced scientific checks (structured input)

Run `sra verify-science examples/advanced_scientific_checks.json --out science-checks.json`.
This command checks explicitly supplied structured values and emits a JSON
result with `PASS`, `FAIL`, or `PARTIAL`. It does **not** automatically
interpret whole papers or replace scientific peer review.

- **`semantic_ci`:** Checks a researcher-specified claim category against
  a 95% confidence interval. Supported ratio effects include risk, odds,
  hazard and rate ratios (null=1); additive effects use null=0.
  A displayed bound exactly at the null returns `NOT_VERIFIED` because
  rounding can affect interpretation. `no_effect` and `equivalent`
  never establish equivalence; explicit `exact_null_effect` is contradicted
  only when the CI excludes the null. `risk_difference` estimates must be
  in [-1,1]. Free-text `claim_text` is **not** interpreted, and results
  explicitly mark `claim_text_checked: false`.
  CI decisions preserve supplied decimal precision; `reported_interval_exact` and `estimate_exact` retain exact decimal strings.
- **`dimension_equation`:** Checks SI-base dimensional consistency and
  an optional supplied numeric example. Safe, restricted expressions
  (`+`, `-`, `*`, `/`, literal integer powers -8..8) are evaluated
  using bounded exact rational arithmetic on decimal inputs; numeric
  results are represented as rational strings. This is not a symbolic
  proof or validation of physical model assumptions.
- **`unadjusted_risk_ratio`:** Independently calculates crude cumulative
  risk ratio and an approximate Katz log-Wald 95% CI from 2×2 counts.
  Reported crude estimates are checked with displayed-precision and
  relative numerical tolerances. Sparse cells, very coarse precision
  and a collapsed printed CI can yield `NOT_VERIFIED`.
  Do not compare this result directly with a Cox hazard/rate ratio,
  adjusted estimate, or causal effect.

**Example:** The 2025 RECOVERY mortality rate ratio (0.87,
95% CI 0.64–1.18) differs in estimand from the crude cumulative
risk ratio calculated from 86/246 versus 86/231 deaths (about 0.94).
Those two estimates cannot be declared inconsistent solely because
their values differ.

**Input and output safeguards:** Input JSON is limited to 1 MiB with
unique keys, finite numbers and bounded arithmetic; formulas are never
executed as supplied Python code. File-based results include an input
SHA-256, available code provenance, Python and dependency versions.
Packaging verifies reproducible wheel/sdist bytes using a fixed
`SOURCE_DATE_EPOCH` and canonical TAR/GZIP metadata. The standard
`audit` and review interfaces remain unchanged.

**Limitations:** These are checks of user-supplied structured values;
general scientific language interpretation, theorem proving, automatic
formula extraction and expert-rated precision/recall are not established.

## Development

    python -m coverage run --source=src/sra -m unittest discover -s tests -v
    python -m coverage report --fail-under=100

## Safety and scope

Never run untrusted supplementary code automatically. Any future execution layer must be sandboxed, resource-limited and explicit about network, file and process permissions. Preserve original source files; reports are written separately.

## Read-only PyPI download monitoring

GitHub Actions checks this project's public PyPI download statistics once per day using a single GET request to the PyPI Stats API. The monitor uses only Python's standard library, has no package-install step, does not request wheel or source archives, and does not write back to the repository or send notifications. A manual run is available through the GitHub Actions PyPI download monitor (read-only) workflow. If PyPI Stats has not indexed a newly published package yet, the run reports that state and checks again on the next scheduled run. Statistics are aggregate counts and can include activity from other automated clients.

## Read-only npm download monitoring

A separate GitHub Actions workflow checks the npm Downloads API once per day using one read-only GET request. It does not invoke npm, install dependencies, request package archives, publish packages, write to the registry, or send notifications. It reports daily, weekly and 30-day aggregate download counts when the package exists on npm. A 404 is reported as “not published/statistics unavailable,” not as zero downloads. The workflow can also be run manually from GitHub Actions.

## Pre-release validation caveats

Parsing improvements can change extracted claims, node IDs and reasoning-graph fingerprints. Regenerate templates and re-review affected manuscripts; historical imports remain supported only when the reconstructed source-bound graph matches. CI enforces 100% Python statement coverage over src/sra without coverage exclusions. This is not a claim of 100% branch/path coverage, defect absence or scientific validity. A synthetic rule benchmark tests planted warnings, not real scientific precision/recall. Full-text literature verification, raw-data/code execution, discipline-specific validation and independent expert adjudication remain future work.

Release tags are permitted to publish only if the tagged commit is reachable from `origin/main`; both PyPI and npm workflows enforce this ancestry before build or publishing. This repository-side guard complements, but does not replace, GitHub protected tags and release-environment approval.
