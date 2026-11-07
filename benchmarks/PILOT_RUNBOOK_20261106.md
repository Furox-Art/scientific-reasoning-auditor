# Pilot runbook: reviewer recruitment and labeling (2026-11-06)

Organizer-facing operations only. This runbook does not change the frozen
protocol, preregistration, coding manual, benchmark or pack. It adds no
expert labels. Reviewers never receive this file.

## Current status

- Frozen corpus: 12 processed PMC papers, two codes, 24 units.
- Blinded pack v3 built and hash-verified; stored outside the repository.
- Reviewers recruited: 0. Adjudicators recruited: 0. Expert labels: 0.
- Quality metrics remain unavailable until two real independent reviewers and
  a distinct adjudicator complete the work.

## Non-negotiable rules

- Two real, distinct, qualified reviewers; one distinct qualified adjudicator.
  The organizer does not label. No fabricated, AI-generated or tool-derived
  labels.
- Reviewers receive only the paper texts, the coding manual and their own
  worksheet. They do not receive this runbook, the protocol, the
  preregistration, the frozen benchmark, the repository link, the tool, the
  pack manifest or the other reviewer's worksheet.
- Do not name the repository or tool before both worksheets are submitted.
  The public repository contains predictions, so naming it enables lookup.
  Blinding is procedural, not enforced by software.
- Keep declarations, identity-to-pseudonym mapping and personal contact data
  outside the repository.
- Run all hash-binding commands from an LF checkout with the package
  installed (a fresh Linux clone or an instabox work tree). A Windows CRLF
  checkout changes the benchmark hash and breaks worksheet verification.

## Roles

| Role | Pseudonym | Who |
| --- | --- | --- |
| Organizer | organizer | [ORGANIZER] |
| Reviewer A | reviewer_1 | [PENDING] |
| Reviewer B | reviewer_2 | [PENDING] |
| Adjudicator | adjudicator_1 | [PENDING] |

Pseudonyms are assignments, not verified identities. Record the mapping in a
private file outside the repository.

## Recruitment

1. Identify candidates from your own professional network, institutional
   contacts or methods/peer-review communities. Do not scrape or cold-email
   public profiles. Aim for at least four reviewer candidates and two
   adjudicator candidates so declines can be covered.
2. Screen against the preregistered qualifications: PhD/MD or equivalent
   research training in a biomedical, health-science or adjacent empirical
   discipline; at least two years of active peer-review or research-ethics
   experience; fluent English; no authorship, employment, funding or personal
   relationship connected to any of the twelve papers.
3. Send [REVIEWER_INVITATION_20261106.md](REVIEWER_INVITATION_20261106.md) with
   only [REVIEWER_DECLARATION_20261106.md](REVIEWER_DECLARATION_20261106.md)
   attached. Fill every bracketed field first.
4. On a positive reply, collect the signed declaration. Check degree, field,
   experience years, English fluency, every conflict item and every commitment
   initial. Do not send the pack if any required item is missing or a conflict
   is unresolved.
5. The adjudicator needs the same qualifications and independence, must be
   distinct from both reviewers, and must not see reviewer verdicts before
   deciding the disagreement units.

## Private workspace

Create a directory outside the repository. The verified pack v3 is currently
copied at `C:/_work/sra-validation-pack-20261106-v3`; place it wherever the
labeling environment can read it. For example:

```bash
PRIVATE=/path/to/pilot-20261106-private
PACK=/path/to/validation-20261106-pilot-v3
mkdir -p "$PRIVATE"
```

Store there: the identity mapping, signed declarations, invitation log,
returned worksheets, adjudication file, final labels and hashes. Never commit
declarations or the identity mapping.

## Send the pack

After a declaration is accepted, assign the reviewer to `reviewer_1` or
`reviewer_2` at random and record the mapping privately. Send that reviewer
only:

- the `papers/` directory (or a zip of it);
- `coding_manual.md`;
- their own `reviewer_N.json`;
- the deadline and return address in the email body.

Do not send the pack README, manifest, protocol, preregistration, benchmark,
repository link or the other worksheet. Do not send both worksheets to either
reviewer. If a reviewer withdraws after receiving the pack, assign a backup to
the same worksheet, update only its `reviewer_id`, record the change, and do
not reuse partial verdicts.

## Check returned worksheets

Save this as `$PRIVATE/check_worksheet.py` and run it on each returned sheet:

```python
import json
import sys
from pathlib import Path

sheet = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert sheet["kind"] == "blinded_validation_worksheet"
cases = sheet["cases"]
assert len(cases) == 24
assert len({(c["pmcid"], c["code"]) for c in cases}) == 24
assert all(type(c["verdict"]) is bool for c in cases)
print("worksheet OK:", sheet["reviewer_id"], len(cases))
```

```bash
python3 "$PRIVATE/check_worksheet.py" "$PRIVATE/reviewer_1.json"
python3 "$PRIVATE/check_worksheet.py" "$PRIVATE/reviewer_2.json"
sha256sum "$PRIVATE/reviewer_1.json" "$PRIVATE/reviewer_2.json" > "$PRIVATE/sheet-hashes.txt"
```

A sheet with a blank, null, string or missing verdict is returned to the
reviewer for correction; do not repair it yourself.

## Prepare the adjudication file

After both sheets pass, save this as `$PRIVATE/make_adjudication_template.py`:

```python
import json
import sys
from pathlib import Path

a_path, b_path, out_path = map(Path, sys.argv[1:4])

def load(path):
    sheet = json.loads(path.read_text(encoding="utf-8"))
    assert sheet["kind"] == "blinded_validation_worksheet"
    cases = sheet["cases"]
    assert len(cases) == 24
    assert all(type(c["verdict"]) is bool for c in cases)
    return {(c["pmcid"], c["code"]): c["verdict"] for c in cases}

a = load(a_path)
b = load(b_path)
assert set(a) == set(b)
disagreements = [key for key in a if a[key] != b[key]]
template = {
    "adjudicator_id": "adjudicator_1",
    "decisions": [
        {"pmcid": pmcid, "code": code, "expert_label": None, "rationale": None}
        for pmcid, code in disagreements
    ],
}
out_path.write_text(json.dumps(template, indent=2), encoding="utf-8")
print(len(disagreements), "disagreement(s)")
```

```bash
python3 "$PRIVATE/make_adjudication_template.py" \
  "$PRIVATE/reviewer_1.json" "$PRIVATE/reviewer_2.json" "$PRIVATE/adjudications.json"
```

Send the adjudicator the paper texts, the coding manual and
`adjudications.json`, plus the instruction: replace every `expert_label` null
with true or false and every `rationale` null with at least 20 characters of
reasoning, using only the supplied text. Do not reveal either reviewer's
verdicts. If there are no disagreements, the adjudicator still returns the
file with a distinct `adjudicator_id` and an empty `decisions` list.

## Merge, freeze and evaluate

Run from the LF checkout with the package installed:

```bash
cd /path/to/lf-checkout
sra adjudicate-labels benchmarks/pmc_smoke_20261105.json \
  "$PRIVATE/reviewer_1.json" "$PRIVATE/reviewer_2.json" "$PRIVATE/adjudications.json" \
  --out "$PRIVATE/final-labels.json"
sha256sum "$PRIVATE/final-labels.json" > "$PRIVATE/final-labels.sha256"
sra evaluate-labels benchmarks/pmc_smoke_20261105.json \
  "$PRIVATE/final-labels.json" --out "$PRIVATE/expert-validation-report.json"
```

The merge verifies hashes, coverage, distinct reviewer IDs, a distinct
adjudicator, boolean decisions and rationale length. It rejects decisions on
agreed units. Freeze the final-labels hash before evaluation. Report the
inter-reviewer agreement from the merge output with the metrics.

Final labels and the report may be committed only after confirming they
contain pseudonyms and no personal data. Declarations, the identity mapping
and contact details are never committed.

## Tracker

Keep this table updated in the private workspace, not in the repository.

| Candidate | Role | Source | Invited | Accepted | Declaration | Pack sent | Returned | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| [CANDIDATE] | reviewer_1 | | | | | | | |
| [CANDIDATE] | reviewer_2 | | | | | | | |
| [CANDIDATE] | adjudicator_1 | | | | | | | |
| [BACKUP] | reviewer backup | | | | | | | |
| [BACKUP] | adjudicator backup | | | | | | | |

## Deviations log

Record every deviation before continuing: date, what changed, why, and the
effect on blinding, coverage or interpretation.

| Date | Deviation | Reason | Impact |
| --- | --- | --- | --- |
| | | | |

## Stop conditions

- Cannot recruit two qualified independent reviewers: do not label; report
  that expert validation was not performed.
- A reviewer uses the tool, automated labeling or external literature, or
  discusses cases before both sheets are submitted: discard that sheet,
  replace the reviewer, and record the deviation.
- A source hash changes or a worksheet fails the frozen benchmark hash: stop.
  Do not relabel against a different corpus without a new preregistration.
- No qualified adjudicator is available: the labels are incomplete; do not
  report final metrics.

## What this pilot can and cannot claim

With 24 units from 12 papers, report per-code confusion matrices, precision,
recall, specificity, Wilson intervals and inter-reviewer agreement. Null
denominators are null, not zero. The corpus is a convenience sample; the
reviewers are declared, not verified; blinding is procedural. The result is a
pilot agreement estimate, not a publication-grade validation of the tool.
