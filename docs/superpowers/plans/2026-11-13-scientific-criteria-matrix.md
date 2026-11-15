# Scientific criteria matrix implementation plan

**Goal:** Make broad manuscript-review coverage explicit, including criteria
that the software cannot assess. This is an original extensible review catalog,
not an exhaustive scientific standard or certification of guideline compliance.

**Design:** Add an immutable catalog of common and study-type criteria, required
evidence, available procedures and limitations. Unified review derives a
source-bound matrix from actual module/check results. Applicability, automation
support, execution and scientific adequacy are separate axes. Every scientific
verdict remains NOT_ASSESSED; a completed calculation or keyword match cannot
establish a manuscript-level criterion. Unknown/mixed study types and conditional
criteria require human applicability review. Explicit checks that conflict with
declared type remain visible and request review instead of disappearing.

**Architecture:** New catalog and matrix modules use the standard library only.
The existing review API adds criteria_matrix, capabilities exposes a detached
catalog, the JSON schema accepts the additive field, and Markdown renders it.
Evidence uses JSON Pointers into the same report, retaining per-check failures,
unknowns and source hashes. Model advice never upgrades scientific verification.
No manuscript writes, network calls, quality score or new backend is introduced.

**Scope:** Question/contribution, background/novelty, design/sampling/measurement,
logic/math/units, inference/multiplicity/missingness/power/robustness, bias/causality,
ethics/consent/harms, preregistration/protocol deviations, conflicts/funding,
citations/updates, data/materials/code access and reexecution, tables/figures,
computational/ML/Bayesian methods, systematic/narrative reviews, qualitative
credibility/reflexivity, theoretical proof obligations and research integrity.
Unavailable specialist assessments remain explicit. New estimators, plagiarism
databases, full code execution and independent expert accuracy are outside scope.

## Tasks

- [x] Add failing tests for applicability, evidence references, unknown results,
      source binding, deterministic hashes and honest unsupported criteria.
- [x] Implement catalog and matrix derivation; integrate report/schema/catalog.
- [x] Add CLI/Node/MCP regressions and English documentation/examples.
- [x] Run full tests/coverage, package validation and visual report QA.
- [x] After all implementation, assign one separate agent a read-only review;
      resolve material findings and rerun affected checks.

Delivery procedure: transfer verified commits to the clean Windows feature
branch, test there, push the existing remote branch and update draft PR #8.
Record Windows and remote CI evidence in the PR; do not merge or publish.

## Local verification and review record

On Linux Python 3.12.14 / Node 24.22.1: 766 Python, 28 Node and 44 MCP tests
passed; 6444 runtime statements, 100% statement coverage. Compile/dependency/
whitespace checks and 10 synthetic controls passed. Two independent builds
produced identical wheels and normalized sdists; exact inventories, isolated
installation/audit and metadata validation passed. Rendered matrices for
theoretical, qualitative and computational examples and the feature document
were visually inspected, with text-bound checks and Markdown tables enabled.

After implementation, one separate read-only software-review agent examined all
new production code, catalog entries, schema, integrations, tests and documents.
It found four P2 status/scope bugs: unrequested structured references upgrading
paragraph screens; legacy PARTIAL/unverified comparisons being lost; automatic
general screening producing a false applicability conflict; and SVG/metadata
inventories being classified as structured calculation. Failing regressions
reproduced them; fixes passed. The same reviewer confirmed closure and reran the
17 criterion tests and original reproductions. This is software review, not
independent scientific expert validation or a claim of complete field coverage.

## Method references

- EQUATOR study-type reporting resources: https://www.equator-network.org/
- COS TOP disclosure/sharing/verification distinctions:
  https://www.cos.io/initiatives/top-guidelines
- Existing docs/CHECK_INVENTORY.md, docs/DOMAIN_EXPERT_PROTOCOL.md and
  docs/RESEARCH_METHODS.md define the implemented procedures and their limits.
