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

## 3. PDF tables — `open`

Today only `page.extract_text()`. Numbers printed in a table are invisible, which
is where most reported statistics live. Closing it needs a table-aware reader
(optional extra), tests on a generated PDF, and an honest statement of the layout
limits that remain.

## 4. Validation harness — `blocked (external)` for the labels, `open` for the code

`sra evaluate-labels` exists; what is missing is an end-to-end run that emits the
pre-registered metrics (recall, precision, Wilson interval, Cohen's kappa) from a
label file. The labels themselves need real reviewers: this project cannot
manufacture scientific accuracy evidence, and says so in its README.

## 5. Rule inventory — `open`

Every `check_id`, with what it catches, what it cannot catch, and where its false
positives come from. A test should fail when a rule exists without an inventory
row, so a new rule cannot ship undocumented.
