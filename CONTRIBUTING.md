# Contributing

Thanks for considering a contribution. This project is a research-software tool
for evidence-traceable screening of scientific manuscripts. A finding it emits
is a review signal, not a verdict, so contributions that change detection rules
must keep the interpretation rules in `README.md` accurate.

## Requirements

- Python 3.11 or newer (CI runs 3.11 and 3.12).
- Node.js 18, 22 or 24 for the npm adapter tests.

## Set up a development environment

```bash
git clone https://github.com/Furox-Art/scientific-reasoning-auditor.git
cd scientific-reasoning-auditor
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[pdf,statistics,logic,toolkit,dev]"
```

The editable install is required: the tests import the installed `sra` package,
so a stale non-editable install in site-packages will shadow the working tree.

## Run the tests

The test suite uses the standard library `unittest` runner under `coverage`
(there is no pytest dependency):

```bash
python -m coverage run --source=src/sra -m unittest discover -s tests -v
python -m coverage report
```

CI enforces 100% *statement* coverage for `src/sra` using both
`[tool.coverage.report] fail_under = 100` in `pyproject.toml` and an explicit
command-line threshold:

```bash
python -m coverage report --fail-under=100
```

A local `coverage report` also applies the configured threshold. Branch coverage
is not currently measured; 100% statement coverage is not proof that every
decision or scientific edge case has been tested.

Other checks that CI runs on every push and pull request
(`.github/workflows/tests.yml`):

```bash
python -m compileall -q src tests tools
PYTHONPATH=src python tools/evaluate_heuristics.py --require-perfect-on-synthetic
npm test
```

The release workflows (`.github/workflows/publish.yml`,
`.github/workflows/npm-publish.yml`) additionally build the distributions,
normalize the sdist, verify reproducibility and run `twine check`:

```bash
export SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)"
python -m build --outdir dist
python tools/normalize_sdist.py dist/*.tar.gz
python tools/verify_distributions.py dist
python -m twine check dist/*
```

## Local hooks

`.pre-commit-config.yaml` runs only generic whitespace, YAML, JSON, TOML and
merge-conflict checks. This repository has no `ruff`, `flake8`, `black`, `isort`
or `mypy` configuration, so no formatter or linter hook is configured; do not
add one without agreeing on the tool and its configuration first.

```bash
python -m pip install pre-commit
pre-commit install
pre-commit run --all-files
```

## Versioning

The Python version is declared in three places and must stay in lockstep:

- `pyproject.toml` -> `[project].version`
- `src/sra/__init__.py` -> `__version__`
- `src/sra/provenance.py` -> `RULESET_VERSION`

The npm adapter has its own independent version in `package.json` (currently
0.1.x). No automated lockstep check exists; verify by hand.

Record user-visible changes in `CHANGELOG.md` under `## [Unreleased]` using
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) headings.

## Pull request expectations

- Add or update tests for any behavior change. The suite must stay at 100%
  coverage of `src/sra`.
- Do not change a detection rule without updating the matching interpretation
  rule in `README.md` and, when the change affects a stored schema or
  fingerprint, the schema version.
- Keep the tool read-only with respect to inputs: it must never overwrite a
  source manuscript, template or review document.
- Do not claim that the tool proves a manuscript correct or incorrect, and do
  not report accuracy figures that are not backed by the recorded benchmark data
  in `docs/` and `benchmarks/`.

## Reporting bugs and security issues

Open a regular issue for functional bugs. Report security vulnerabilities
privately as described in `SECURITY.md`; do not use a public issue for them.
