# Gap closure plan

A durable, reviewable stand-in for a session goal: the list of gaps this project
knows about, what closes each one, and how far each has got. Every item states
what "closed" means, so a claim here can be checked in the repository rather than
remembered.

Status keys: `open` · `in progress` · `closed` · `blocked (external)`.

## 0. No skipped tests — `closed`

The suite skipped two cases on Windows (symlinks need Developer Mode; the release
guard runs under MSYS bash) plus one FIFO case where `os.mkfifo` is absent. All
three now run everywhere: the alias test falls back to a hard link, the guard is
replayed with the commit inlined because MSYS bash loses shell variables started
from Python, and the FIFO guard is exercised through the file-status word where
no FIFO exists. Closed when: `unittest discover -s tests` reports no skips on
Windows and on Linux. The hard-link case also exposed a real gap: the CLI
preflight compared resolved paths, so a hard link to the manuscript passed the
check and the write would have destroyed it. It now compares file identity.

## 1. Numbers agreeing with each other — `closed` (0.6.0, `96f5a08`)

Sentence-scoped comparison of a reported interval with its own p-value, and of a
mean with its own interval. Closed when: both rules exist, are wired into the
audit, keep the suite green at 100% statement coverage, and the README states
what they cannot see (numbers in other sentences, tables or figures).

## 2. Test selection and impossible values — `closed`

What closes it:
- a group count compared with pairwise t-tests only, with no omnibus test named;
- a p-value that cannot exist (`p = 0.000`, `p > 1`, `p < 0`);
- a dispersion or sample size that cannot exist (negative SD/SE, `n = 0`).

Same narrowness as item 1: one sentence, both numbers present, quote the sentence.

## 3. PDF tables — `closed`

Extraction turned out not to be the blocker: pypdf already returns a table row on
one line. The gap was that the rules read prose. PDF text is now read in layout
mode, and a row whose header names n, mean, SD, SE or p becomes the statements
the plausibility rules understand, with the row and column recorded as evidence.
Closed when: a PDF table with an impossible dispersion and p-value is audited and
both are reported, and the limits (merged cells, sub-headers, figure text) are in
the README.

Today only `page.extract_text()`. Numbers printed in a table are invisible, which
is where most reported statistics live. Closing it needs a table-aware reader
(optional extra), tests on a generated PDF, and an honest statement of the layout
limits that remain.

## 4. Validation harness — harness `closed`, labels `blocked (external)`

Earlier I recorded this as open on the code side; that was wrong. The three
stages already existed and were individually tested: `validation-pack` builds the
blinded worksheets, `adjudicate-labels` merges two reviewers plus an adjudicator
and reports raw exact agreement and Cohen's kappa, and `evaluate-labels` reports
tp/fp/fn/tn, precision, recall, specificity and Wilson intervals per finding code
and as a micro average, with the limitations attached to the report.

What was missing is protection: nothing asserted that the three stages still fit
together. `tests/test_validation_pipeline.py` now runs two synthetic reviewers,
one adjudicator and the metric report end to end (agreement 0.75, kappa 0.5, one
tp, one fn), and asserts that incomplete coverage is refused. Closed when: that
test passes on CI, which it does.

The labels themselves remain external. No number produced by synthetic labels is
evidence of accuracy, and the README, the runbook and the report's own limitations
say so.

## 5. Rule inventory — `closed`

`docs/CHECK_INVENTORY.md` lists all 21 finding codes with three columns each:
what the rule detects, what it cannot detect, and where its false positives come
from. `tests/test_check_inventory.py` derives the code's rule ids from the syntax
tree (both the `Finding(...)` and the local `_finding(...)` constructors) and
compares them with the table in both directions, so a rule cannot ship
undocumented and a documentation row cannot outlive its rule. A row whose cells
are thinner than a real explanation fails as well.

Closed when: the inventory parses, all three tests pass on CI, and the README
points at it.

## 6. Multilingual coverage — `closed` (translations unreviewed)

English and Turkish were the only recognised languages, so a Spanish or Japanese
manuscript returned a clean report because no rule could read it. The lexicons
behind the existing rules (headings, direction, absolute claims, association,
causal verbs, corrections, group counts, rate measures, paired designs, test
names) now list 14 languages. `tests/test_multilingual.py` walks every term and
asserts the matching rule receives it, then builds a manuscript out of one
language's own listing to prove the pipeline runs.

Closed when: the term-by-term test passes, which it does locally; CI runs the same suite. Not closed: no
native speaker has reviewed the translations, and the README says so; a term that
is missing from a language still fails silently there.
