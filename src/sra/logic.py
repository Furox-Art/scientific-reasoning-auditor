"""Conditional formal verification through Z3, with reproducible bounded settings."""
from __future__ import annotations

import hashlib
import json
from importlib.metadata import version

from sra.document import ParsedDocument
from sra.logic_spec import LogicProblem, Term, prepare_logic_spec

SETTINGS = {"random_seed": 0, "threads": 1, "rlimit": 100000}


def _load_z3():
    try:
        import z3
    except ImportError as exc:
        raise RuntimeError("Formal verification requires the optional scientific-reasoning-auditor[logic] extra.") from exc
    return z3


def _compile(term: Term, symbols: dict, z3, context):
    if term.kind == "variable":
        return symbols[term.value]
    if term.kind == "boolean":
        return z3.BoolVal(term.value, ctx=context)
    if term.kind == "number":
        return (z3.IntVal if term.sort == "Int" else z3.RealVal)(term.value, ctx=context)
    args = [_compile(part, symbols, z3, context) for part in term.args]
    if term.kind == "div":
        numerator = z3.ToReal(args[0]) if term.args[0].sort == "Int" else args[0]
        return numerator / args[1]
    operations = {
        "and": lambda: z3.And(*args), "or": lambda: z3.Or(*args),
        "not": lambda: z3.Not(args[0]), "implies": lambda: z3.Implies(*args),
        "iff": lambda: args[0] == args[1], "neg": lambda: -args[0],
        "add": lambda: args[0] + args[1], "sub": lambda: args[0] - args[1],
        "mul": lambda: args[0] * args[1], "eq": lambda: args[0] == args[1],
        "ne": lambda: args[0] != args[1], "lt": lambda: args[0] < args[1],
        "le": lambda: args[0] <= args[1], "gt": lambda: args[0] > args[1],
        "ge": lambda: args[0] >= args[1],
    }
    return operations[term.kind]()


def _check(z3, context, expressions) -> str:
    solver = z3.Solver(ctx=context)
    solver.set(**SETTINGS)
    solver.add(*expressions)
    return str(solver.check())


def verify_prepared_logic(problem: LogicProblem) -> dict:
    z3 = _load_z3()
    context = z3.Context()
    sorts = {"Bool": z3.Bool, "Int": z3.Int, "Real": z3.Real}
    symbols = {name: sorts[sort](name, ctx=context) for name, sort in problem.variables.items()}
    expressions = {identity: _compile(term, symbols, z3, context) for identity, term in problem.terms.items()}
    premises = [expressions[item["id"]] for item in problem.assumptions]
    base = _check(z3, context, premises)
    outcomes = []
    partial = base == "unknown"
    for claim in problem.claims:
        negative, positive = "not_run", "not_run"
        if base != "sat":
            status = "UNDETERMINED"
            reason = "INCONSISTENT_PREMISES" if base == "unsat" else "SOLVER_RESOURCE_LIMIT"
        else:
            formula = expressions[claim["id"]]
            negative = _check(z3, context, [*premises, z3.Not(formula)])
            if negative == "unsat":
                status, reason = "VERIFIED", "NEGATED_CLAIM_UNSATISFIABLE"
            else:
                positive = _check(z3, context, [*premises, formula])
                if positive == "unsat":
                    status, reason = "REFUTED", "CLAIM_UNSATISFIABLE"
                else:
                    status = "UNDETERMINED"
                    reason = "BOTH_POSSIBLE" if negative == positive == "sat" else "SOLVER_RESOURCE_LIMIT"
            partial = partial or negative == "unknown" or positive == "unknown"
        outcomes.append({**claim, "status": status, "reason": reason,
                         "checks": {"assumptions_and_negated_claim": negative, "assumptions_and_claim": positive},
                         "basis_assumption_ids": [item["id"] for item in problem.assumptions]})
    report = {
        "schema_version": "formal-logic-review/1.0", "adapter_version": "z3-linear-1", "input_sha256": problem.input_sha256,
        "source_sha256": problem.source_binding["source_sha256"],
        "extracted_text_sha256": problem.source_binding["extracted_text_sha256"],
        "source_binding": problem.source_binding, "execution_status": "partial" if partial else "complete",
        "engine": {"name": "Z3", "version": z3.get_version_string(),
                   "distribution_version": version("z3-solver"), "settings": dict(SETTINGS)},
        "variables": problem.variables, "assumptions": list(problem.assumptions),
        "premises": {"status": {"sat":"CONSISTENT", "unsat":"INCONSISTENT", "unknown":"UNDETERMINED"}[base],
                     "solver_result": base}, "claims": outcomes,
        "limitations": [
            "Results concern only the supplied formal assumptions, not their empirical truth.",
            "Source hashes and quote presence do not verify faithful translation from prose to formulas.",
            "Only Boolean logic and bounded quantifier-free linear integer/real arithmetic are supported.",
            "Resource-limited unknown results are never proofs; no wall-clock timing or noncanonical model witnesses enter this report.",
            "Repeatability is scoped to the same input, adapter, solver version/settings and platform; cross-version/platform identity is not guaranteed.",
            "The input manuscript is never edited; findings are a separate report for the user.",
        ],
    }
    report["report_sha256"] = hashlib.sha256(json.dumps(report, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return report


def verify_logic_spec(spec: dict | str, *, document: ParsedDocument | None = None) -> dict:
    return verify_prepared_logic(prepare_logic_spec(spec, document))
