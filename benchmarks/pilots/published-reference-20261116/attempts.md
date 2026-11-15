# Execution attempts and deviation record

The specification and parser clarification were frozen before any reference
predictions. Engine code, source bytes, labels, case inclusion and tolerances
were unchanged between the attempts below.

1. The first WSL-launched Windows process terminated with an OpenBLAS memory
   allocation error. No completed JSON/Markdown comparison was produced. The
   initial error log is preserved in the private execution workspace; it is
   not a suppressed unfavorable metric result.
2. A native Python driver set `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`,
   `MKL_NUM_THREADS` and `NUMEXPR_NUM_THREADS` to `1` inside the process before
   loading numerical libraries. The unchanged comparator completed successfully.
   This first completed result is preserved as `first-run.json` / `first-run.md`.

The completed numerical environment was Windows AMD64 / Python 3.15.2 /
NumPy 2.5.5 / SciPy 1.18.1. This record is an environment/setup deviation, not
a change to the reference labels or an optimization against observed scores.
Do not overwrite the first completed result when attempting replication.
