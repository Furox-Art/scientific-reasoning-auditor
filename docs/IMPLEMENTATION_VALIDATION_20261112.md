# Cross-disciplinary review implementation validation

Date: 2026-11-12. This is software behavior evidence, not scientific validation.

## Scope delivered

- Unified source-bound Python API, `sra review` and `sra capabilities`.
- Multiple existing discipline profiles and explicit study-type applicability.
- JSON schema, source-located Markdown, module states, exclusions and coverage gaps.
- Typed Node interface with actual feature discovery; eight bounded MCP tools.
- Offline defaults and explicit per-call/host opt-in for external services.
- Six synthetic cross-field behavior controls, without expert labels or accuracy claims.

## Verification

The baseline was GitHub main commit `61631f839e0ec5e64dd8fbe38529050df629c88d`.
It passed 625 Python tests with 100% statement coverage. Final verification after
review fixes passed 660 Python tests and 100% coverage (4,554 statements), 25 Node
tests and 38 MCP tests, including actual stdio client/server calls. Windows tests
used Python 3.12.10 and Node 24.14.0 in a separate virtual environment.

Commands, with `sra` installed from this checkout:

```bash
python -m coverage run --source=src/sra -m unittest discover -s tests -q
python -m coverage report --fail-under=100
npm test
python -m unittest discover -s mcp_server/tests -q
python -m build --outdir /path/to/dist
python tools/normalize_sdist.py /path/to/dist/scientific_reasoning_auditor-0.8.0.tar.gz
python tools/verify_distributions.py /path/to/dist
python -m twine check /path/to/dist/*
```

Set `OPENBLAS_NUM_THREADS=1` on constrained hosts and `SRA_PYTHON` to the matching
interpreter for Node tests. Package builds used isolated build environments and
a fixed `SOURCE_DATE_EPOCH`. Distribution validation confirmed 128 declared source
files and 39 installed Python module files against their complete allowlists,
including a clean pip-installed wheel, CLI entry point and audit invocation.
Generated text metadata permits CRLF/LF equivalence; source files remain byte-exact.

## Independent code review and corrections

A separate read-only code reviewer identified four substantive issues; each was
reproduced with a failing test and fixed:

1. Model-embedded rule findings now follow the same applicability exclusions as
   the common reasoning module; standalone legacy model output stays unchanged.
2. Extended statistics validate supplied groups/tables and reported settings
   before importing SciPy, so missing dependencies cannot let malformed inputs
   reach registry or model requests.
3. Failed/unverifiable DOI requests yield partial execution with preserved DOI
   results. Completed negative registration lookups remain completed executions.
4. Source-identity errors escape optional-module handling. Unified vision reads
   and verifies original PDF bytes before outbound requests, then uses a private
   immutable copy for model page images.

Windows integration additionally exposed inherited stdin in Git provenance
subprocesses and slash-dependent temporary-path scrubbing; regression tests and
real stdio calls verify the corrections. Generated package metadata line-ending
differences are tested separately from real content changes.

## Limits and decisions

Implementation remained in a separate clone and feature branch; the user's
existing local checkout was not modified. Existing Python/MCP dependencies were
reused, with the required MCP 1.x SDK installed only in the task's virtual environment.

No live paid-provider call, public deployment, package publication or human-reviewer
outreach was performed. Independent scientific accuracy, live registry/provider
behavior and real figure understanding are unverified by this implementation work.
Six specialist cue profiles remain the supported specialist scope; other fields
use common checks and optional model interpretation with explicit coverage gaps.
