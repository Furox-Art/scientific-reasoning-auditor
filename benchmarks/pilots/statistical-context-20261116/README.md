# Recorded statistical-context numerical controls

This packet tests distribution-table arithmetic and explicitly synthetic guards.
It evaluates **zero papers** and collects **zero new human reviews**. It is not
whole-paper accuracy, representative multi-field validation, a held-out paper
cohort or independent scientific expert verification.

## Recorded result

All 32 expected behaviors matched: 24 VERIFIED NIST-derived numerical cases,
two REFUTED intentionally wrong-direction synthetic controls and six
UNDETERMINED synthetic controls. Abstentions remain visible. This is not a
scientific accuracy percentage. The engine execution is deliberately partial
because unknown context must abstain.

The protocol and cases were committed before implementation at
`40880b924d931538b93c25c99b0891714848bf14`. Reviewed implementation:
`10bc2482b48ebc10d75379904c541008e82d5f13`.
Development unit tests also exercised these controls; this is a recorded native
Windows run after the reviewed implementation commit, not a new blinded study.
The separate precision clarification records an agent-found conversion defect
and its conservative correction without changing the selected cases.

## Identities and environment

- JSON file SHA-256: `8dc7149bc75b619664e0e11330d83b5787378ea40066b3e1f7f0babff7e34282`.
- Semantic report SHA-256: `1120cd52e91c05721f0f0d3635fb09618418d97d34df296f63b7836927daaee8`.
- Producer SHA-256: `5385e34d30aac40af95ab95067a270bafcf10de6aa531888f07bb13864474303`.
- Runtime source SHA-256: `8f474a0bc36091139bf85d7531e13ba58674a734c9512e769a73c50c5bb87b3b`.
- Case, protocol and clarification hashes are retained in the complete JSON.
- Windows AMD64 / Python 3.15.2 / NumPy 2.5.4 / SciPy 1.18.1.
- Other recorded packages: Statsmodels 0.15.0, NetworkX 3.7, arviz-stats 1.3.3.

`recorded-run.json` and `.md` are unchanged copies of the external run outputs.
The report hashes runtime Python files, producer and frozen inputs separately;
it does not hash its own output into its provenance. Full byte identity also
depends on the recorded environment, including optional package metadata.

## Reproduce

Use the source checkout or the included script in the npm archive. The Python
wheel installs the engine; the Python source distribution includes this packet.
For the measured Windows environment, use PowerShell:

```powershell
py -3.15 -m venv .venv-context
.venv-context/Scripts/python -m pip install "scientific-reasoning-auditor[statistics,research]==0.10.0" "numpy==2.5.4" "scipy==1.18.1"
$env:OPENBLAS_NUM_THREADS="1"
$env:OMP_NUM_THREADS="1"
$env:MKL_NUM_THREADS="1"
$env:NUMEXPR_NUM_THREADS="1"
.venv-context/Scripts/python -I tools/evaluate_statistical_context.py --out reports/context-replication
```

Installation needs a registry or local wheel cache; the numerical run is offline.
Choose a fresh output prefix: existing reports are refused. The standalone
comparison returns success for matched expectations even though six engine
checks intentionally abstain. Complete case results remain available for review.

## Sources and limits

The protocol links the four original NIST Engineering Statistics Handbook pages.
Printed critical values and explicit symmetry transformations form 24 cases;
eight controls are separately marked as synthetic. Original source pages are
not bundled and no NIST endorsement is implied. NIST integer-df tables do not
validate arbitrary fractional df; separate analytic unit controls cover selected
values and the precision regression.

Unknown/rounded df abstain. Even exact decimal df abstain if the float backend
cannot represent them exactly (for example 1.3); .5 and 10.5 are supported.
Correction choice and test intent remain caller declarations. Backend probability
error bounds are not formally proven. No real-world false-alarm reduction rate
was measured. The old published 0.9.0 historical report remains unchanged and
was not rescored. New human assessment and representative paper validation
remain outstanding.
