# Discipline-specific evidence and expert protocol

The six discipline profiles are **paragraph-grounded reporting aids**, not
complete expert systems or compliance certification. Each check requires
two or more named signals in an appropriate Methods/Results paragraph.

`TEXTUAL_EVIDENCE_CANDIDATE` means cues co-occur; `PARTIAL_CUES_REVIEW_MANUALLY`
means incomplete or scattered cues; `NOT_DETECTED_REVIEW_MANUALLY` means
no supported cue was recognized. None proves that reporting is adequate
or inadequate. The counts are not scientific validity scores.

## Field profiles

| Discipline | Topics | Reference |
| --- | --- | --- |
| `clinical` | Ethics, allocation, harms, endpoints, missing data, effect confidence intervals | [CONSORT 2025](https://www.bmj.com/content/389/bmj-2024-081123) |
| `animal` | Experimental unit, blinding, randomization, group size, age/sex, result variability | [ARRIVE 2.0](https://arriveguidelines.org/arrive-guidelines) |
| `physics` | Measurement uncertainty, calibration, apparatus resolution, propagation, boundary conditions | [NIST measurement guidance](https://www.nist.gov/itl/sed/topic-areas/measurement-uncertainty) |
| `chemistry` | Analytical purity, NMR conditions, detection limits, replicates, calibration, yields | SRA original review questions |
| `computing` | Dataset leakage, seeds, baselines, hyperparameters, software versions, external evaluation | SRA original review questions |
| `social-science` | Sampling, ethics, confounders, reliability, missing responses, sensitivity analyses | [STROBE](https://www.strobe-statement.org/) |

For medical prediction models consult [TRIPOD+AI](https://www.tripod-statement.org/).
The profiles are original abbreviations, *not copies or full implementations*
of these published checklists.

## Review workflow

Generate a source-bound candidate report and **unfilled** expert template:

```bash
sra domain-review examples/physics_domain_demo.md --discipline physics --out reports/domain.json
sra domain-template examples/physics_domain_demo.md --discipline physics --out reports/template.json
```

Give the complete manuscript, appendices, data and reporting guidelines to
**two independent qualified reviewers**. They must independently assess each
rule using one of: `adequately_reported`, `partially_reported`,
`not_reported`, `not_applicable`, `uncertain`.

Each template assessment needs exactly two reviewer objects, with distinct
`reviewer_id` values, `verdict`, `rationale` (at least 20 characters) and,
for positive or partial verdicts, an **exact 12+ character source_quote**.
A final `adjudicated_verdict` and `adjudication_rationale` (20+ characters)
must be supplied. Retain the template-level `source_sha256`,
`ruleset_sha256`, `contract_sha256` and all rule IDs.

After **real reviewers** complete it:

```bash
sra domain-validate examples/physics_domain_demo.md reports/completed.json --discipline physics --out reports/checked.json
```

The importer rejects missing/duplicate rule IDs, mismatched source and
ruleset hashes, absent quotes and inadequate rationale. The software cannot
verify real reviewer identity, qualifications, independence, or scientific
judgment, even when the review is structurally accepted. Do not invent
assessments to obtain an apparent expert sign-off.

For performance estimation on independently adjudicated real papers, follow
[the separate validation protocol](../benchmarks/VALIDATION_PROTOCOL.md).

## Privacy

The domain tool is offline and never alters the source manuscript.
The optional local LanguageTool interface sends non-reference prose only
to a user-run `127.0.0.1` server and never to a public grammar API.
