# Deterministic formal logic verification: Z3 integration design

User requirement: a general-purpose deterministic verifier, with findings delivered
to the user in a separate report. The original manuscript must remain read-only.
The user delegated selection and integration of an existing suitable tool.

## Tool selection (2026-11-12)

Selected [Z3](https://github.com/Z3Prover/z3), MIT licensed, through the official
`z3-solver` Python package. [The official guide](https://microsoft.github.io/z3guide/docs/logic/intro/)
describes Z3 as a component for solving explicitly modeled logical formulas.
Its existing Python bindings fit this Python engine and supported Windows/Linux
development environments. [cvc5](https://github.com/cvc5/cvc5) is another capable SMT
engine, but integrating a second backend adds no necessary first-version behavior.
Neither solver automatically establishes the meaning or truth of scientific prose.

## Bounded first integration

- Optional pinned `logic` extra. No network, models or manuscript rewriting.
- Boolean logic and quantifier-free linear integer/real arithmetic through a
  restricted expression parser, never Python eval or arbitrary SMT-LIB commands.
- Expressions permit declared variables, exact numeric literals, Boolean operators,
  comparisons, addition/subtraction, multiplication by a constant and division by
  a nonzero constant. Functions are restricted to `implies` and `iff`.
- A JSON problem declares variables, named assumptions and claims. Check premise
  consistency before conclusions: inconsistent premises never prove every claim.
- A claim is VERIFIED only if assumptions plus its negation are unsatisfiable;
  REFUTED only if assumptions plus the claim are unsatisfiable. If both remain
  possible or the solver budget is exhausted, return UNDETERMINED with a reason.
- Fixed solver version, seeds, one thread, bounded resource units and ordered
  construction. Record engine version/settings and canonical input/report hashes.
  Do not promise identical behavior across solver versions/platforms, use elapsed
  time in report identities, or claim canonical models/minimal proof cores.
- Input at most 1 MiB, 64 variables, 64 assumptions, 32 claims, 512 characters and
  128 AST nodes per expression, depth 32, 5,000 nodes overall, bounded numbers.
- If a manuscript is supplied, require matching raw and extracted-text digests.
  Validate any supplied source quote and line. Quote presence does not verify
  that a formula faithfully formalizes its natural-language meaning.
- Standalone structured verification is usable outside scientific manuscripts;
  clearly identify unbound problems and the limits of conditional formal results.

## Interfaces and integration plan

1. Add safe parsing/validation in `src/sra/logic_spec.py`, Z3 checking and stable
   report generation in `src/sra/logic.py`, and separate Markdown rendering.
2. Add `sra verify-logic spec.json [--manuscript paper.md] --out reports/logic`.
   CLI returns 0 for completed verification, 1 for budget-unknown work and 2 for
   invalid input. Logical refutation is a finding, not an execution failure.
3. Accept `logic_spec` in unified review and `--logic-spec` in `sra review`.
   Validate/bind/solve before any requested registry/model transmission.
4. Expose typed Node `verifyLogic` and a read-only local MCP `verify_logic` tool;
   allow the same optional specification in unified MCP review. Preserve old
   result contracts and make the additive report module optional when unrequested.
5. Add exact Boolean/arithmetic examples, source-preservation and hostile-input
   tests, missing-dependency and budget-unknown tests, repeatability tests across
   processes and concurrent independent contexts, and interface integration tests.
6. Run existing Python coverage, Node and MCP suites, package/provenance checks,
   a fresh read-only code review and push to the user's existing development PR.

Report outcomes describe entailment within supplied formal assumptions only.
Raw-data truth, causal identification, all mathematical proofs and automatic
full-manuscript semantic verification remain outside this first integration.

## Installation and use

This feature requires a source checkout containing the integration, not merely
the published Python 0.8.0/npm 0.1.2 releases. The optional extra pins the official
Python distribution to `z3-solver==5.4.1.0`; no solver source is vendored.

```bash
python -m pip install -e ".[logic]"
sra verify-logic examples/logic_boolean.json --out reports/logic
sra verify-logic examples/logic_arithmetic.json --out reports/arithmetic
```

Each command creates separate `.json` and `.md` reports. Original manuscript and
specification files cannot be output targets, including link aliases. Completed
verification exits 0, resource-unknown execution exits 1, invalid input or missing
solver exits 2. A REFUTED claim is a completed formal finding, not a process error.

Python uses `from sra.logic import verify_logic_spec` with a dictionary or JSON
string. Node provides `verifyLogic(specPath, {out, manuscript, stdio})`, and MCP
provides `verify_logic(spec_json, content?, file_format?, encoding?)`. All these
paths are offline. MCP content is temporary uploaded source data, never a local
filesystem path or a request to modify a manuscript.

The input schema is [formal-logic-input.schema.json](../schemas/formal-logic-input.schema.json).
The parser additionally checks syntax, expression types, ID uniqueness, source
identities and complexity limits that JSON Schema alone cannot establish.

## Binding formal statements to a manuscript

For `--manuscript paper.md` or unified `sra review paper.md --logic-spec formal.json`,
the input must contain both the raw-file `source_sha256` and the extracted-text
`extracted_text_sha256`. Construct these from the exact parser snapshot:

```python
import hashlib
import json
from pathlib import Path
from sra.document import load_document

document = load_document("paper.md")
problem = json.loads(Path("formal.json").read_text(encoding="utf-8"))
problem["source_sha256"] = document.sha256
problem["extracted_text_sha256"] = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
Path("bound-formal.json").write_text(json.dumps(problem, indent=2), encoding="utf-8")
```

This writes a separate specification, never the manuscript. Add `source_quote`
and optional `line` to assumptions/claims when relevant. Quotes must be exact
12–2,000 character substrings; supplied lines must identify their start. Missing
quotes are marked unprovided. Standalone problems without a manuscript are
explicitly unbound, even when someone has supplied digest strings in the JSON.

Matching a source or quotation does not verify the semantic translation from
prose to formulas. No heuristic or model proposal is silently promoted to a
formal proof. User results state precisely which supplied assumptions were used.
The listed assumptions are the full basis, not a claimed minimal proof core.

## Reading the decisions

- `VERIFIED`: assumptions plus the negated claim are unsatisfiable.
- `REFUTED`: assumptions plus the claim are unsatisfiable.
- `UNDETERMINED`: both may be possible, the premises are inconsistent, or the
  bounded solver returned unknown. The report distinguishes these reasons.

The engine checks consistency first. For example, assuming both `p` and `not p`
does not result in every unrelated claim being displayed as verified. For `x / 2`,
division is exact rational division even when `x` is an integer; it is not Python
floor division or a floating-point approximation. Decimal literals are exact.

The report includes normalized input SHA-256, adapter version, actual Z3/library
versions and fixed `random_seed=0`, `threads=1`, `rlimit=100000`. It contains no
timestamps, wall-clock measurements, noncanonical model witnesses or unspecified
minimal unsatisfiable core. Unknown is not a proof. Resource budgets are per query;
the supported input bounds also cap the number and size of queries.

## License and upstream references

Z3 copyright is held by Microsoft Corporation and is distributed under the
[MIT license](https://github.com/Z3Prover/z3/blob/master/LICENSE.txt). This repository
uses its optional package and does not relicense or redistribute its source code.
Installed third-party distributions retain their own license notices.

- [Official logical-modeling guide](https://microsoft.github.io/z3guide/docs/logic/intro/)
- [Python solver API](https://z3prover.github.io/api/html/classz3py_1_1_solver.html)
- [Resource and solver parameter reference](https://microsoft.github.io/z3guide/programming/Parameters/)
- [Official Python package](https://pypi.org/project/z3-solver/)

## Implementation validation (2026-11-12)

Final local validation passed 685 Python tests with 100% statement coverage
(4,880 statements), 27 Node tests and 42 MCP tests, including actual stdio calls
to the formal tool. Real Z3 is used for Boolean decisions, exact decimal/rational
arithmetic, integer/real division, cross-process report equality and independent
concurrent contexts. Test cases explicitly cover inconsistent premises, under-
determination, solver-unknown results, source preservation, invalid AST/code input,
allocation bounds and separate outputs. No live model or registry calls were used.

A fresh read-only code review found repetitive-quote matching could repeatedly
scan document prefixes and native solver exceptions could escape adapter error
handling. Regression tests first reproduced both issues. Quote binding now builds
a compact line index once, caches quote ambiguity and searches a requested start
line directly, also accepting overlapping valid quotes. Backend exceptions become
sanitized RuntimeErrors so unified review preserves its other modules and MCP
returns a structured failure. No upstream Z3 correctness or scientific accuracy
claim follows from these software tests.

Distribution verification checked 138 declared source files and 43 installed
Python module files against complete allowlists, installed the base wheel in a
clean environment and ran its CLI/audit without requiring the optional solver.
The optional solver itself was exercised through the source installation.
