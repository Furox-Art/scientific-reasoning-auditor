# Human error-review collection and grouped diagnostics

Continue the authorized deterministic-validation work without manufacturing
human labels or changing frozen pilot inputs. Implement in the current branch;
obtain a fresh read-only agent review after code is written, test and push to
the existing draft PR. No merge or publication.

## Design

The existing source-checkout exporter is tied to two licensed articles. Add an
offline `build-cohort` command for any validated bounded error manifest. Include
the complete supplied text snapshots, permission/source declarations, literal
quotes, target definitions and separate null reviewer sheets. Omit executable
checks, predictions, group/split allocation and the other reviewer's sheet from
reviewer archives. Snapshot completeness, source permissions and actual blinding
remain caller responsibilities. This does not select a representative corpus.

Add `inspect` for two complete returned sheets, before adjudication and without
running any numerical auditor. Produce an organizer report and a separate
prediction/decision-free adjudicator packet containing only disputed cases,
their sources/targets and null decisions. Reuse existing merge validation.
No disagreement is automatically resolved. Output files use exclusive creation.

Add four-category pre-adjudication agreement diagnostics to the existing
evaluator: explicit contingency table/marginals, raw agreement, expected
agreement and unweighted Cohen kappa. Use integer arithmetic for numerators and
denominators; a zero denominator is null. Compute kappa only for a fixed pair
of declared reviewer IDs across the cohort. It is descriptive, not a quality
threshold, independent expertise claim or cluster-adjusted uncertainty estimate.

Retain existing metrics and add paper/group strata, group IDs per result and
leave-one-group-out descriptive sensitivity. Require two groups for omission
sensitivity; retain abstentions and excluded labels in every subset. This
does not provide confidence intervals or cure sampling bias.

## Implementation and checks

- [x] Add failing collection/reliability tests with four-label disagreement,
  undefined kappa, varying reviewer pairs, reverse pair order and grouped counts.
- [x] Implement focused runtime agreement helpers and evaluator integration;
  verify existing CLI/Node/MCP paths retain the added diagnostics.
- [x] Generalize offline collection and add blinded adjudication packet export;
  test malformed sheets, content hashes, full snapshots and output protection.
- [x] Document exact contracts, source/sampling limits and commands in English.
- [ ] Run full Python/Node/MCP tests, statement coverage and distribution checks;
  render/visually inspect documents/reports; obtain and resolve agent review.
- [ ] Commit, verify Windows, push existing branch, update draft PR/checks.
