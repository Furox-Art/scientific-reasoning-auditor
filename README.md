# Scientific Reasoning Auditor

A research-software project for auditing the reasoning chain in scientific manuscripts:

**Hypothesis → assumptions → methods → data → analysis → inference → conclusion**

The software exposes reviewable reasoning risks with evidence locations and reproducibility metadata. It does not declare a manuscript scientifically true or false.

## Current status: v0.5.1

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

## Independently verify a Welch t-test

Create a JSON file with two groups' mean, sample SD and n, plus the reported statistics to compare. Example:

    sra verify-stats examples/welch_t_example.json --out reports/welch-verification.json

Each reported value is compared with the independently calculated value using the configured absolute tolerance. Without an explicit tolerance, the verifier uses half the last displayed decimal place; field-specific or default overrides can be supplied in the JSON input. A mismatch returns a non-zero exit code. Report p-values as positive values in (0, 1], not as zero. The command supports only independent two-group Welch t-tests in this version. Input JSON rejects duplicate object keys (including nested keys) and non-standard numeric constants rather than silently accepting ambiguous reported values.

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
