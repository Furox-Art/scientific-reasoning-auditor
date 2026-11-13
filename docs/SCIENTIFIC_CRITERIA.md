# Scientific criteria coverage

Every unified `sra review` result includes `criteria_matrix`; `sra capabilities`
includes its detached, versioned `criteria_catalog`. Python, CLI, Node and MCP
use the same implementation. No extra network request or dependency is needed.
Manuscripts remain read-only and findings stay in separate reports.

This is an original, extensible catalog of important review questions. It is
**not exhaustive for every field**, an official guideline checklist, a scientific
quality score or certification that a manuscript meets its criteria.

## Separate assessment axes

| Field | Meaning |
| --- | --- |
| `applicability` | Applicable under the declared type, outside that type, or requiring human confirmation. |
| `support_level` | Structured checks, screening/evidence organization, human review only, or not implemented. |
| `execution_status` | What the relevant procedures actually did in this report. |
| `scientific_verdict` | Always `NOT_ASSESSED`; completion never becomes scientific adequacy. |

Unknown/mixed study types require applicability review for type-specific rows.
Conditional topics such as ethics, preregistration, ML, Bayesian sampling and
pooling also require confirmation. A quantitative/computational declaration
does not mean every such study uses those methods. `not_applicable` is conditional
on the caller's declared type, not an independently verified exclusion. Requested
checks or selected profile cues conflicting with that type remain visible and
change applicability to `requires_review`.

## Catalog scope and required evidence

Questions cover objectives/contribution, novelty and prior work, methods/structure,
claims and limitations, citation support/metadata/updates, ethics/consent/harms,
funding/conflicts/contributors, registration/protocol deviations, data/materials/
code/environment, reexecution, integrity, design/confounding, sampling,
measurement, allocation/blinding, sample-size/power, inference/uncertainty,
multiplicity, missingness, robustness, bias, mathematics/units, tables/figures,
ML/computational/Bayesian evaluation, qualitative credibility/reflexivity,
systematic searches/screening/extraction, pooling/narrative synthesis and
theoretical definitions/proof completeness.

Each row states `required_evidence`, the available `procedure` and its
`limitation`. These are review requirements, not claims that the evidence was
supplied. Full code reexecution, comprehensive plagiarism/data authenticity
checks and full reporting-guideline assessments remain `not_implemented`.
Qualitative credibility, novelty, protocol comparison and complete proof
adequacy remain human review questions. New catalog entries alone do not
implement scientific validation.

## Source-bound execution references

`evidence` contains source hashes and JSON Pointers into the **same report**:
module records, individual toolkit/scientific checks or specific profile items.
Pointers use RFC 6901 escaping. No quotations or model judgments are invented.
Toolkit operations match validated requested checks. A multiple-testing
correction does not count as missing-data analysis, and a confidence-interval
check does not count as a dimensional check. Requested scientific kinds are
retained even when their backend is unavailable.

Each reference retains module execution, individual check status and limited
assessment scope. A failed check elsewhere in a toolkit report does not erase
valid calculations. Backend failures, solver unknowns, unknown bias domains and
unassessed ML checks cannot look fully completed. Disagreement (`REFUTED` or
arithmetic `FAIL`) means a comparison completed, not that execution failed;
inspect that retained check result.

- `checks_completed`: linked bounded procedures completed.
- `screening_completed`: screening or evidence organization completed.
- `partial`, `failed`, `unavailable`: unresolved or unsuccessful execution.
- `not_requested`: no relevant automated procedure was executed/requested.
- `human_review_required`, `not_implemented`: no automated adequacy assessment.
- `not_applicable`: outside the declared type; confirm that declaration.

Available structured capability alone never upgrades a completed paragraph
screen. SVG inventories and publication snapshots remain screening. Unverified
reported statistical fields remain partial even if other fields disagree.
Arithmetic-only statistical requests can complete without comparing reported
numbers; that does not establish agreement with numbers in the manuscript.

`human_review_required` stays true for applicable/uncertain criteria, including
successful calculations. Model advice never upgrades coverage. Summary counts
are not completion/quality percentages. Root `execution_status=complete` still
describes requested module execution; many criteria can remain unassessed.

Catalog and matrix have separate schema versions and deterministic SHA-256
fingerprints. The existing report schema accepts this additive field and still
reads older reports without a matrix. Source identities are checked before
references are constructed. Hashes do not authenticate data or prove that
supplied formulas belong to the paper.

## Examples

```bash
sra capabilities
sra review examples/unified_review/theoretical_math.md --study-type theoretical --out reports/criteria-theory
sra review examples/unified_review/qualitative_social.md --study-type qualitative --discipline social-science --out reports/criteria-qualitative
sra review examples/unified_review/computational_physics.md --study-type computational --discipline computing --discipline physics --out reports/criteria-computational
```

These existing examples are synthetic controls, not independent scientific
evaluations. The theoretical workflow leaves proof completeness to human review
and unrequested empirical power outside the declared type. The qualitative
workflow includes credibility/reflexivity questions without judging adequacy.
Computational review retains conditional ML applicability despite paragraph
cues. Structured check inputs retain the source-binding/confirmation rules in
`DETERMINISTIC_TOOLKIT.md`.

## Method context

Study-specific reporting resources: [EQUATOR](https://www.equator-network.org/).
Disclosure, sharing and verification are distinct levels in
[COS TOP](https://www.cos.io/initiatives/top-guidelines). These sources inform
scope and terminology; this catalog does not reproduce or certify their complete
checklists. See `CHECK_INVENTORY.md`, `DOMAIN_EXPERT_PROTOCOL.md` and
`RESEARCH_METHODS.md` for the implemented screens/calculations and their limits.
