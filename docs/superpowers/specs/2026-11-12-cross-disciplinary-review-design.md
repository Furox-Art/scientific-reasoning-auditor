# Cross-disciplinary scientific review: proposed design

Date: 2026-11-12
Status: proposal awaiting user approval
Baseline: GitHub main, commit 61631f839e0ec5e64dd8fbe38529050df629c88d

## Intent and agreed direction

The user wants a scientific manuscript reviewer usable across scientific fields.
They selected a common core with extensible discipline modules and optional model
support, rather than a model-only reviewer. The existing Python engine, CLI,
Node adapter and MCP server remain the delivery interfaces. A browser application
is not required for this first milestone; that is the author's proposed scope.

The product should help a researcher see what deserves checking, where the
evidence is, and which parts have not been assessed. It must not turn execution
success, keyword presence, or a model opinion into scientific certification.

## Approaches considered

1. Common source-bound core, explicit discipline/method modules and optional
   model interpretation. More engineering, but individually testable coverage,
   offline utility and measurable failure modes. Selected by the user.
2. Model-centered whole-paper peer reviewer. Broader apparent immediate subject
   coverage, but provider dependence and difficult scientific validation. Not
   selected; existing model assistance is retained as one advisory module.

## Current project evidence

- `domain_evidence.py` has six abbreviated profiles: clinical, animal, physics,
  chemistry, computing and social-science. Their paragraph matches are candidates,
  not expert judgments. There is no substantive specialist profile for every field.
- `discipline.py` separately contains reporting cues for four study designs.
- Reasoning, writing, DOI metadata, statistical arithmetic, structured scientific
  verification and full-text model review are separate commands/results.
- `paper-review` validates exact source quotations and complete extracted-character
  submission; it does not prove the relevance or truth of a criticism.
- Independent, representative expert-labeled scientific accuracy is not established.
- Some structural rules expect Methods/Results/Conclusion headings. Applying these
  indiscriminately to theoretical work can produce misleading warnings.
- Python imports currently resolve to another editable local checkout unless the
  intended source is explicitly selected. Baseline verification must record the
  actual source path. This is an environment observation, not a repository defect.

## First implementation milestone

Deliver an end-to-end unified, offline-first review, not merely more checklist
names. Preserve existing commands, report schemas and six expert-review contracts.

### User flow

Proposed new command:

```console
sra review paper.pdf --study-type theoretical --out reports/paper
sra review paper.md --study-type computational --discipline computing --discipline physics --out reports/paper
sra capabilities
```

`study_type` is an explicit declaration, not an automatically proven classification.
Allowed values: unknown, quantitative, qualitative, computational, theoretical,
systematic-review, narrative-review and mixed. Default unknown. Unknown and mixed
must not silently enable assumptions about randomization, human subjects or test
choice. Unknown type produces an explicit applicability-review-needed record.

Discipline arguments select zero or more of the existing six profiles. An omitted
profile runs the common core and records specialist assessment as not requested.
Invalid identifiers are rejected before any external request. A capabilities
catalog explains supported profiles, study types, limitations and available
quantitative checks. A field without a specialist profile can use common and
model modules, with an explicit specialist-coverage gap. Do not invent field
expertise by relabeling generic questions.

Keep this first milestone bounded: implement the profile registry and applicability
architecture with the existing six profiles. New engineering, mathematics, biology,
earth/environment and other specialist rule packs follow only with meaningful
positive/negative controls and documented domain scope. The proposed milestone is
the foundation for all-field use, not a claim that every field is already validated.

### Unified modules

1. Extraction: source bytes, extracted text, page availability and immutable hashes.
2. Reasoning: existing source-located findings and graph, with applicability metadata.
3. Writing: general editorial and reference-format signals, with language limits.
4. Discipline reporting: all explicitly selected existing profiles, separately named.
5. Citation metadata: offline DOI extraction by default; registry queries only on
   explicit online opt-in. Exact cited-claim support remains not assessed.
6. Quantitative verification: optional user-supplied statistics/science JSON specs,
   checked by existing bounded engines. No guessed numbers or automatic figure-to-
   statistics reconstruction. Not supplied means not requested, never verified.
7. Model interpretation: optional existing full-text review with source quotes.
   This requires explicit `--send-to-model` and a model identifier; no model call
   happens during development tests. It remains advisory, even when quotes match.

The Python API returns the same unified contract used by the CLI and adapters.
Node gains a corresponding typed wrapper. MCP gains a bounded unified tool and a
capabilities tool, retaining existing tools. MCP uses its current decoded input,
structured input, concurrency and output limits. Model/online calls require both
per-call consent and the existing host enable flags. OCR and page vision remain
CLI-only capabilities in this milestone and are listed as unavailable in MCP.

### Applicability and meaningful absence

Introduce an explicit applicability table, versioned separately from legacy
rules. It governs presentation in the NEW unified report. Do not alter old CLI
outputs or old graph fingerprints merely to suppress a warning in the new flow.

For theoretical and narrative-review papers, empirical Methods/Results-heading
requirements cannot be presented as confirmed deficiencies. Relevant legacy
structural findings are retained under an excluded-findings record, with original
ID, source location and reason; they are not silently deleted. No scientific
content finding is suppressed merely because of a discipline label. Quantitative,
qualitative, computational and systematic-review types can still have different
reporting expectations; only implement exclusions supported by explicit tests and
documented rationale. Unknown/mixed are conservative and ask for applicability
review rather than guessing which paradigm is correct.

Each module status is one of completed, not_requested, not_applicable, unavailable
or failed. Completed means execution completed, not that the paper passed.
Use applicability and assessment status separately so missing text, unperformed
checks and out-of-scope questions cannot collapse into a single negative verdict.

### Source and report contract

New report schema `cross-disciplinary-review/1.0` includes:

- Original source label, raw SHA-256, extracted-text SHA-256, parser/extraction
  metadata, supplied study type and selected disciplines.
- Effective configuration and capability/applicability contract identifiers.
- Module status, reason, source hashes and existing module result payloads.
- Source-located findings and explicit exclusions; source quotes remain verbatim.
- Coverage gaps including raw-data validation, proof verification, exact citation
  support, unexamined figures/supplements and missing specialist profiles.
- An execution status complete or partial, with a plain statement that it is not
  scientific quality or validity. No aggregate scientific score or PASS verdict.
- Provenance using the existing manifest; no promise of deterministic model output.

Parse a single bounded immutable manuscript snapshot for the unified flow. Add
parsed-document helpers to existing path-based APIs as needed; path APIs delegate
to them without changing their public result formats. If any existing stage must
reopen a file, use a private byte-identical snapshot and verify both source and
extracted-text hashes before associating its results with the unified report.
Never attach a result from changed input bytes. Keep the original input unchanged.

Validate configuration and structured spec sizes/types before network access.
Malformed input or source mismatch is a hard error. Optional-module dependency or
runtime failures are explicit failed/unavailable entries and make the report
partial. Requested model failure cannot yield a complete review. Required source
extraction failure prevents any complete report. Do not expose secrets or provider
response bodies in errors.

Write JSON and Markdown through the existing source-alias/output protections.
Render model/user content with existing Markdown escaping. CLI exit codes: 0 for
completed requested execution, 1 for partial execution, 2 for invalid input or
required processing failure. Findings alone do not change execution exit status.

## Validation and acceptance

- Preserve the existing Python, Node and MCP tests and required source coverage.
  Record baseline failures separately from regressions; do not weaken tests to
  manufacture success.
- End-to-end fixtures for theoretical math, computational physics, clinical
  quantitative research, qualitative social research, systematic review and an
  unknown-field manuscript. Fixtures are synthetic behavior controls, never expert
  scientific accuracy evidence.
- Verify theoretical/narrative work does not acquire empirical-structure verdicts;
  verify genuine empirical warning signals are retained and exclusions visible.
- Verify multi-profile composition, duplicate selection, unknown IDs, missing
  optional dependencies/specs, source mutation, malformed JSON, failed model chunk,
  output aliases and report output bounds.
- Assert no network by default. Test per-call and host consent combinations in MCP,
  using deterministic fakes, without a live paid-provider request.
- Check all composed results bind to the same source hashes; public legacy result
  contracts and six profile/ruleset hashes remain compatible unless separately
  versioned and justified.
- Run meaningful Node/MCP protocol integration tests for the new entry points.
  Package metadata/distribution checks must cover new runtime and schema files.
- Document exact example commands, current coverage gaps and reproducible checks.

## Subsequent milestones and limits

After this foundation, grow specialist profiles by discipline AND method, improve
false-positive behavior with held-out cases, and establish an independently
adjudicated multi-field evaluation. Real experts, authorized paper corpora and
reviewer independence cannot be supplied by this coding task. No accuracy target
will be claimed without that evidence.

Data/code reproducibility in a real sandbox, mathematical proof/equation engines,
verified cited-claim retrieval, new-language validation, and public multi-tenant
hosting are separate milestones. No arbitrary supplementary code execution,
automatic deployment, package publication, paid model calls or messages to human
reviewers are included in the first milestone.

## Implementation decisions delegated to the builder

Exact helper/module filenames, internal dataclasses, rendering layout and fixture
phrasing are implementation choices. Prefer standard-library runtime code and
existing optional dependencies. Keep adapter/version/schema changes minimal and
explicit. No new runtime dependency is required by this proposed architecture.
