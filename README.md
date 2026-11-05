# Scientific Reasoning Auditor

A research-software project for auditing the reasoning chain in scientific manuscripts:

**Hypothesis → assumptions → methods → data → analysis → inference → conclusion**

The software exposes reviewable reasoning risks with evidence locations and reproducibility metadata. It does not declare a manuscript scientifically true or false.

## Current status: v0.5.1 (latest tagged release)

The main branch contains additional **unreleased** language and domain-review tooling. Tagged PyPI/npm packages do not yet include those additions.

New source-only experimental tools are listed below; the tagged release does not include them.

The main branch also contains source changes that are not yet in a new tagged Python or npm release. Install from source to use the latest academic-writing module.

This patch release hardens authenticated model API transport and JSON handling, stabilizes Welch and pooled-standard-deviation calculations across extreme numeric scales, and corrects Hedges' g for very large degrees of freedom. It retains the traceable reasoning-review layer and independently recalculable statistical summary checks introduced in earlier releases.

### Implemented

- Read Markdown and UTF-8 text manuscripts; optional PDF text extraction.
- Preserve repeated section headings, ignore fenced code blocks during section/heuristic extraction, and conservatively detect standard standalone headings in plain text/PDF extraction.
- Apply negation-aware causal/directional screening and avoid treating a cited prior randomized trial as proof that the current study was randomized.
- Record manuscript SHA-256, exact source/config tree SHA-256 (including uncommitted changes), file size, parser details, ruleset/configuration hashes, Python/runtime details and an environment fingerprint.
- Attach line and section references to extracted Discussion/Conclusion claims and candidate result passages.
- Identify conclusion claims for which no lexical result candidate is found.
- Flag possible opposite-direction statements between Results and Conclusion (for example, increased versus decreased for overlapping topics).
- Flag causal conclusion language when Methods text describes an observational or non-randomized design.
- Flag selected absolute/conclusive wording.
- Recalculate a two-independent-group Welch t-test from supplied group means, sample standard deviations and sample sizes; compare reported mean difference, t statistic, degrees of freedom and two-sided p-value within explicit tolerances.
- Produce an explicit reasoning graph with claim, evidence, method, assumption, limitation, inference and grouped document-context nodes, source locations, relation edges and a graph fingerprint. Shared context nodes avoid method/limitation-to-inference Cartesian edge growth.
- Validate graph structure for dangling references, duplicate IDs and dependency cycles; report inferences without lexical evidence.
- Create source-bound semantic-review templates for external LLMs/agents and validate returned source hashes, graph fingerprints, inference-linked support evidence, explicitly reviewer-selected additional evidence, confidence fields and meaningful source quotations.
- Require explicit causal-assumption review even when a lexically similar assumption sentence was extracted; lexical overlap no longer clears the causal assumption gap.
- Produce JSON and Markdown audit reports plus a machine-readable statistical verification result.
- Run tests using Python's standard library plus the optional SciPy statistics extra.
- Check academic writing structure, citations/reference-list candidates, placeholders and potentially overconfident wording using a separate advisory report.

### Interpretation rules

- A finding is a review signal, not an automatic verdict.
- Lexical overlap is not semantic entailment and does not prove that evidence supports a claim.
- A missing lexical match is not proof that a conclusion is unsupported; relevant evidence may be paraphrased or located elsewhere.
- A possible direction conflict may be caused by subgroup definitions, recoding, different endpoints or sentence-extraction errors.
- Observational wording does not by itself invalidate a causal inference; causal identification may be justified by design and assumptions not detected by these rules.
- Welch verification checks arithmetic conditional on supplied summary statistics. It does not validate the raw data, study design, assumptions or choice of statistical test.
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

The npm package requires Node.js 18+ and Python 3.11+ with the Python package available to the selected interpreter. It has no npm runtime dependencies and performs no network requests or package installation itself. Set `SRA_PYTHON` to the Python executable when the engine is installed in a non-default environment.

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

To publish a subsequent npm version, update package.json, commit the change, and push a matching tag such as npm-v0.1.1. The workflow runs Node tests and npm pack --dry-run before publishing via OIDC. npm currently requires a package to exist before its Trusted Publisher can be configured, so the first package publication must be completed once using npm account verification.

## Run manuscript audit

    sra audit examples/sample_manuscript.md --out reports/sample

The command writes reports/sample.json and reports/sample.md. JSON includes the reproducibility manifest; Markdown is the human-readable review.

A synthetic document with deliberately planted inference and direction-conflict signals is provided:

    sra audit examples/logic_review_demo.md --out reports/logic-review-demo

## Build a reasoning graph and request semantic review

Run an audit to include a graph in the JSON and Markdown reports:

    sra audit examples/logic_review_demo.md --out reports/logic-review

The output contract is documented in the [semantic-review JSON Schema](https://github.com/Furox-Art/scientific-reasoning-auditor/blob/main/schemas/semantic-review.schema.json).

Create a JSON template and choose the review mode:

    sra review-template examples/logic_review_demo.md --mode single --out reports/semantic-review-single.json
    sra review-template examples/logic_review_demo.md --mode parallel --out reports/semantic-review-parallel.json

The single mode (default) prepares the whole review for one model. It can now call an OpenAI-compatible Chat Completions endpoint directly. The parallel mode remains an external agent-orchestrator workflow; the user selects the mode for each run. The Python CLI does not pretend to launch ChatGPT parallel agents.

For a direct single-model API review, set the API key in the environment and run:

    export OPENAI_API_KEY="your-api-key"
    sra review-model examples/logic_review_demo.md --model "your-model-id" --base-url "https://api.openai.com/v1" --out reports/semantic-review-completed.json

The command sends the complete manuscript and source-bound template to one model, parses its JSON response, then validates the returned review against the manuscript and reasoning graph. Any OpenAI-compatible Chat Completions endpoint can be configured with --base-url and --api-key-env. Remote endpoints must use HTTPS so the API key is encrypted in transit; plain HTTP is accepted only for localhost or IP loopback addresses (127.0.0.0/8 and ::1) for inference servers, and these local clear-text requests bypass environment-configured HTTP proxies. URLs containing embedded credentials or query/fragment delimiters are rejected, and HTTP redirects are not followed to prevent forwarding authorization headers to another host. Statistical inputs that underflow or overflow the supported floating-point range are rejected with a validation error rather than producing silently rounded or non-finite report values; the Welch and pooled-standard-deviation calculations use scaled formulas to preserve valid extreme-range inputs. Statistics JSON input rejects non-standard NaN/Infinity constants. The API key is read from the environment and is not written to reports. Model/API charges and provider data-retention policies are controlled by the provider.

For parallel mode, export the template and pass it to the connected external parallel-agent orchestrator. Each agent must receive the full manuscript and its assigned assessment subset; merge all results by inference ID before importing. The current CLI does not launch the ChatGPT UI-based parallel-agent tool.

Give the template and full manuscript to the selected model or external orchestration layer for passage-grounded assessment. Fill every assessment with a relation (entailed, partially_supported, contradicted, not_supported, or unclear), confidence, rationale and exact source quotations where applicable. Then import the completed file:

    sra audit examples/logic_review_demo.md --semantic-review reports/semantic-review-completed.json --out reports/semantic-reviewed

The template includes a complete source-bound catalog of Results evidence-node IDs, passages and locations. The importer checks the manuscript hash and reasoning-graph fingerprint, requires graph-linked support IDs or explicit reviewer-selected Results evidence IDs, and validates the existence, type and source quotation provenance of selected nodes. Reviewer-selected evidence provenance is checked, but its semantic relevance is not proven. Current-schema quotations must be at least 20 characters and match both the manuscript and selected node text. The importer also enforces the review contract and UTC timestamps. It does not prove the external reviewer’s semantic judgment; expert adjudication remains necessary. The application can call one OpenAI-compatible model in single mode. Parallel-agent execution remains an external orchestration step.

## Academic writing review

Run a separate, offline academic-writing checklist without changing the manuscript. This main-branch feature is not part of the last tagged release (v0.5.1):

    sra writing-audit examples/academic_writing_sample.md --genre original-research --abstract-max-words 250 --out reports/writing-review

This creates a structured JSON report and a readable Markdown report. Review prompts include:

- Recognizable section headings (English/Turkish), with an optional original-research checklist.
- Abstract word count; word limits apply **only if configured** for the target journal.
- Numeric references such as [1] and [2-3], and simple author-year references such as (Smith, 2020) / Smith (2020), matched conservatively to entries in a References/Kaynakça section.
- Unmatched citations, unrecognized reference formats, uncited entries, duplicate numbers/author-year keys, editing placeholders, and potentially absolute wording, with source line numbers where available.

The default genre is general, so non-IMRaD manuscripts are not automatically treated as incomplete. Warnings are advisory and do not produce a nonzero process exit code. Citation style support is limited and matching an author and year is **not** proof of bibliographic identity or support for a scientific claim. This tool is **not** a full grammar corrector, plagiarism detector, DOI validator, copyeditor, or substitute for journal-specific and expert review. No source content is sent to any external API.

## Independently verify a Welch t-test

Create a JSON file with two groups' mean, sample SD and n, plus the reported statistics to compare. Example:

    sra verify-stats examples/welch_t_example.json --out reports/welch-verification.json

Each reported value is compared with the independently calculated value using the configured absolute tolerance. Without an explicit tolerance, the verifier uses half the last displayed decimal place; field-specific or default overrides can be supplied in the JSON input. A mismatch returns a non-zero exit code. Report p-values as positive values in (0, 1], not as zero. The command supports only independent two-group Welch t-tests in this version. Input JSON rejects duplicate object keys (including nested keys) and non-standard numeric constants rather than silently accepting ambiguous reported values.

## Expanded validation tools (main branch; not in v0.5.1 release)

These features are available only by installing from the repository's current
source. They have not been published to PyPI or npm as a new release.

### Five independently calculated statistics

The `sra verify-stats` command now supports:

| `test` | Inputs | Calculated summary |
| --- | --- | --- |
| `welch_t` | Two independent groups (mean, sample SD, n) | Welch t, df, two-sided p, 95% CI |
| `one_sample_t` | `sample` (mean, sd, n); optional `mu0` | Student one-sample t, df, p, 95% CI |
| `paired_t` | `differences` (paired-difference mean, sd, n); optional `mu0` | Paired t on differences, df, p, 95% CI |
| `chi_square_2x2` | `table`: 2 x 2 nonnegative integer counts | Pearson chi-square, df, upper-tail `p_value`, expected counts |
| `fisher_exact_2x2` | `table`: 2 x 2 counts | Fisher two-sided p, finite sample odds ratio |

    sra verify-stats examples/extended_statistics.json --out reports/stats.json

For paired t, supply **within-pair differences**, not two independent
groups' summary statistics. The Pearson chi-square test uses no Yates
correction and emits a caution when expected cell counts are below five.
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

### Expanded academic grammar and field review (unreleased main branch)

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

## Scientific validation roadmap

The project is split into separate assurance layers. A rule-based text scan must not be presented as full scientific validation.

1. **Reasoning graph** — extend the current graph from rule-extracted candidates to validated, semantic claim/evidence/assumption/method/inference relations with provenance.
2. **Quantitative verification** — extend beyond Welch tests to supported tests, effect sizes, confidence intervals, model-fit statistics and data-level recalculation.
3. **Mathematical verification** — symbolic/numeric checks of equations, dimensions, boundary conditions and derivation steps where machine-checkable.
4. **Code and data reproducibility** — controlled execution of supplied analysis code, dataset fingerprints, environment lockfiles, logs and output comparison.
5. **Literature and citation verification** — resolve references and verify whether cited sources support the exact claims.
6. **Specialist review** — task-specific expert analysis, disagreement tracking and human adjudication.
7. **Benchmarking** — curated positive/negative examples, false-positive/false-negative rates, calibration and regression tests.

## Development

    python -m unittest discover -s tests -v

## Safety and scope

Never run untrusted supplementary code automatically. Any future execution layer must be sandboxed, resource-limited and explicit about network, file and process permissions. Preserve original source files; reports are written separately.

## Read-only PyPI download monitoring

GitHub Actions checks this project's public PyPI download statistics once per day using a single GET request to the PyPI Stats API. The monitor uses only Python's standard library, has no package-install step, does not request wheel or source archives, and does not write back to the repository or send notifications. A manual run is available through the GitHub Actions PyPI download monitor (read-only) workflow. If PyPI Stats has not indexed a newly published package yet, the run reports that state and checks again on the next scheduled run. Statistics are aggregate counts and can include activity from other automated clients.

## Read-only npm download monitoring

A separate GitHub Actions workflow checks the npm Downloads API once per day using one read-only GET request. It does not invoke npm, install dependencies, request package archives, publish packages, write to the registry, or send notifications. It reports daily, weekly and 30-day aggregate download counts when the package exists on npm. A 404 is reported as “not published/statistics unavailable,” not as zero downloads. The workflow can also be run manually from GitHub Actions.
