# Scientific Reasoning Auditor

A research-software project for auditing the reasoning chain in scientific manuscripts:

**Hypothesis → assumptions → methods → data → analysis → inference → conclusion**

The software exposes reviewable reasoning risks with evidence locations and reproducibility metadata. It does not declare a manuscript scientifically true or false.

## Current status: v0.5.2 release candidate (unreleased)

The published PyPI release remains **v0.5.1**. This v0.5.2 work is a draft release candidate, not yet merged into main or released. Do not treat draft branch features as installed from PyPI.

This candidate limits model API response memory use, validates reasoning-graph node/edge schema and endpoint types, rejects non-standard JSON constants in imported semantic reviews, and expands the reproducibility source hash to selected runtime, test, workflow, schema, adapter and build inputs. Statistical reports now state that pooled-SD Cohen's d and classical Hedges' g assume a common within-group variance model and are not heteroskedasticity-adjusted. CI covers Python 3.11 and 3.12, uses Node.js 24-compatible GitHub Actions, and pins each external action to a verified full commit SHA.

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
- Recalculate a two-independent-group Welch t-test from supplied group means, sample standard deviations and sample sizes; compare reported mean difference, t statistic, degrees of freedom and two-sided p-value within explicit tolerances.
- Produce an explicit reasoning graph with claim, evidence, method, assumption, limitation, inference and grouped document-context nodes, source locations, relation edges and a graph fingerprint. Shared context nodes avoid method/limitation-to-inference Cartesian edge growth.
- Validate complete graph objects through the strict graph validator, including supported schema version, fingerprint algorithm, canonical node/edge metadata, allowed top-level fields, deterministic edge IDs, endpoint types, dangling references, duplicate IDs and dependency cycles. The lower-level node/edge validator remains available for structural-only checks. Full validation checks required node/edge fields and types, the stored derived validation result, and the graph fingerprint; the derived validation result itself is intentionally excluded from the fingerprint and is recomputed. Graph fingerprints include schema version, fingerprint algorithm, schema metadata, nodes and edges; report inferences without lexical evidence.
- Create source-bound semantic-review 1.4 templates for external LLMs/agents using the original manuscript text (required by the Python template API); the text is checked against the extracted-text digest recorded in the audit manifest, while the raw-file digest remains separate for PDF/BOM inputs. The graph schema and fingerprint algorithm are bound explicitly; the graph's manuscript SHA-256 must equal the audited manuscript SHA-256 when templates are built or reviews are imported. Importers continue to accept review schemas 1.0–1.3 when their fingerprint matches either the current graph or the historical v1.1 fingerprint for unchanged node/edge data; changed graph content is still rejected.
- Require explicit causal-assumption review even when a lexically similar assumption sentence was extracted; lexical overlap no longer clears the causal assumption gap.
- Produce JSON and Markdown audit reports plus a machine-readable statistical verification result.
- Run tests using Python's standard library plus the optional SciPy statistics extra.

### Interpretation rules

- A finding is a review signal, not an automatic verdict.
- Lexical overlap is not semantic entailment and does not prove that evidence supports a claim.
- A missing lexical match is not proof that a conclusion is unsupported; relevant evidence may be paraphrased or located elsewhere.
- A possible direction conflict may be caused by subgroup definitions, recoding, different endpoints or sentence-extraction errors.
- A repeated rate ratio with a differing CI may still refer to different endpoints, populations or statistical models; the check requires explicit `rate ratio …; 95% CI …; p = …` formatting, and misses other estimate types or layouts. Human adjudication remains necessary.
- Observational wording does not by itself invalidate a causal inference; causal identification may be justified by design and assumptions not detected by these rules.
- Welch verification checks arithmetic conditional on supplied summary statistics. It does not validate the raw data, study design, assumptions or choice of statistical test. Pooled-SD Cohen's d uses a common within-group variance reference and is not heteroskedasticity-adjusted; the classical Hedges' J correction is derived under a normally distributed, two-independent-group model with a common variance.
- No finding does not mean that the paper is logically valid.

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

    npx sra audit manuscript.md --out reports/sample
    npx sra review-template manuscript.md --mode single
    npx sra verify-stats welch-input.json

Or call it from JavaScript:

    const { audit, createReviewTemplate, verifyStats } = require("scientific-reasoning-auditor");

    await audit("manuscript.md", { out: "reports/manuscript" });
    await createReviewTemplate("manuscript.md", { mode: "parallel" });
    await verifyStats("welch-input.json");

The functions return `{ code, signal, stdout, stderr }`. By default command output is inherited from the current terminal; pass `stdio: "pipe"` to capture output. The `reviewModel` function also accepts `model`, `baseUrl`, `apiKeyEnv`, `timeout` and `out` options. The Python engine remains the source of truth for audit behavior and output schemas.

## npm releases with OIDC Trusted Publishing

After the initial npm release has created the package, configure a GitHub Actions Trusted Publisher in npm package settings with owner Furox-Art, repository scientific-reasoning-auditor, workflow filename npm-publish.yml, and no environment. Allow direct npm publish. The workflow uses GitHub-hosted runners, Node.js 24+, npm 11.5.1+, and the id-token: write permission; it stores no npm publish token.

To publish a subsequent npm version, update package.json, commit the change, and push a matching tag such as npm-v0.1.1. The workflow runs Node tests and npm pack --dry-run before publishing via OIDC. npm currently requires a package to exist before its Trusted Publisher can be configured, so the first package publication must be completed once using npm account verification.

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

Each reported value is compared with the independently calculated value using the configured absolute tolerance. Without an explicit tolerance, the verifier uses half the last displayed decimal place; field-specific or default overrides can be supplied in the JSON input. A mismatch returns a non-zero exit code. Report p-values as positive values in (0, 1], not as zero. The command supports only independent two-group Welch t-tests in this version. It also reports pooled-SD Cohen's d and classical Hedges' g; these effect-size estimates use a common within-group variance reference and are not heteroskedasticity-adjusted. The classical Hedges' J small-sample correction is derived under a normally distributed, two-independent-group model with a common variance. Interpret them cautiously when group variances differ substantially, even though the Welch test itself permits unequal variances.

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
