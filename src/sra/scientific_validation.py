"""Bounded, researcher-supplied scientific checks; never executes manuscript code.

Three distinct checks:
* semantic_ci: a *structured* inference-level claim versus its stated 95% CI.
* dimension_equation: restricted arithmetic units and one supplied numeric example.
* unadjusted_risk_ratio: crude 2x2 RR with log-Wald CI (not rate/hazard/adjusted RR).

These checks do NOT prove manuscript meaning, formulas in general, causal
identification, model assumptions, or reproduce a published adjusted analysis.
"""
import ast
import hashlib
import json
import math
import platform
import sys
from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from statistics import NormalDist
from typing import Any

from sra.json_utils import reject_duplicate_keys
from sra import __version__
from sra.provenance import _package_version, _source_revision, _source_tree_sha256
from sra.stats import _finite_number, _display_precision_tolerance

_UNIT_KEYS = frozenset(("kg", "m", "s", "A", "K", "mol", "cd"))
_RATIO_MEASURES = frozenset(("risk_ratio", "odds_ratio", "hazard_ratio", "rate_ratio"))
_ADD_MEASURES = frozenset(("mean_difference", "risk_difference"))
_ALLOWED_CLAIMS = frozenset((
    "significant_increase", "significant_decrease", "not_significant",
    "no_effect", "equivalent", "exact_null_effect",
))
_ALLOWED_BINARY = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)
_ALLOWED_UNARY = (ast.UAdd, ast.USub)
_MAX_CHECKS = 100
_MAX_AST_NODES = 80
_MAX_EXPR_LENGTH = 256
_MAX_BYTES = 1024 * 1024


def _obj(value: Any, name: str) -> Mapping:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object.")
    return value


def _num(value: Any, name: str) -> float:
    return _finite_number(value, name)


def _semantic_decimal(value: Any, name: str) -> Decimal:
    """Preserve displayed decimal precision when classifying CI significance."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be a number.")
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError(f"{name} must be finite.")
    if len(number.as_tuple().digits) > 100 or abs(number.adjusted()) > 300:
        raise ValueError(f"{name} exceeds supported decimal precision or magnitude.")
    return number


def _status_summary(rows: list[dict]) -> str:
    if any(row["status"] == "FAIL" for row in rows):
        return "FAIL"
    if rows and all(row["status"] == "PASS" for row in rows):
        return "PASS"
    return "PARTIAL"


def _semantic_ci(item: Mapping) -> dict:
    kind = item.get("claim_type")
    measure = item.get("effect_measure")
    if kind not in _ALLOWED_CLAIMS:
        raise ValueError("semantic_ci.claim_type must be a supported claim category.")
    if measure not in _RATIO_MEASURES | _ADD_MEASURES:
        raise ValueError("semantic_ci.effect_measure must name a supported measure.")
    if _num(item.get("confidence_level"), "confidence_level") != 0.95:
        raise ValueError("semantic_ci requires confidence_level=0.95; no other confidence level is supported.")
    lo, hi, estimate = (
        _semantic_decimal(item.get(k), f"semantic_ci.{k}")
        for k in ("ci_lower", "ci_upper", "estimate")
    )
    if lo > hi or not lo <= estimate <= hi:
        raise ValueError("semantic_ci requires ci_lower <= estimate <= ci_upper.")
    null = Decimal(1) if measure in _RATIO_MEASURES else Decimal(0)
    if measure in _RATIO_MEASURES and lo <= 0.0:
        raise ValueError("A ratio confidence interval and estimate must be positive.")
    if measure == "risk_difference" and not -1.0 <= estimate <= 1.0:
        raise ValueError("A risk-difference point estimate must lie in [-1, 1].")
    text_limit = ("Researcher-provided claim_text is not evaluated. No natural-language "
                  "entailment, method, causality, or statistical-model validation.")
    if kind in ("no_effect", "equivalent"):
        return {
            "status": "NOT_VERIFIED", "kind": "semantic_ci",
            "claim_type": kind, "null_value": float(null), "claim_text_checked": False,
            "reason": "Nonsignificance does not establish no effect or equivalence.",
            "limitations": "Formal equivalence/noninferiority requires prespecified margins. "
                           + text_limit,
        }
    # At a printed null boundary, the unrounded bound could lie on either
    # side of the null. The declared precision does not permit a verdict.
    if lo == null or hi == null:
        return {
            "status": "NOT_VERIFIED", "kind": "semantic_ci",
            "claim_type": kind, "null_value": float(null), "claim_text_checked": False,
            "reason": "The displayed CI boundary equals the null; rounding makes "
                      "significance ambiguous without unrounded bounds.",
            "limitations": text_limit,
        }
    if kind == "exact_null_effect":
        return {
            "status": "FAIL" if lo > null or hi < null else "NOT_VERIFIED",
            "kind": "semantic_ci", "claim_type": kind, "null_value": float(null),
            "claim_text_checked": False,
            "reason": ("CI excludes the null effect." if lo > null or hi < null
                       else "Failure to exclude the null cannot prove exact equality."),
            "limitations": "An exact-null claim is narrower than clinical no-effect claims. "
                           + text_limit,
        }
    supported = {
        "significant_increase": lo > null,
        "significant_decrease": hi < null,
        "not_significant": lo < null < hi,
    }[kind]
    return {
        "status": "PASS" if supported else "FAIL",
        "kind": "semantic_ci", "claim_type": kind, "null_value": float(null),
        "confidence_level": 0.95,
        "claim_text_checked": False,
        "reported_interval": [float(lo), float(hi)],
        "reported_interval_exact": [str(lo), str(hi)],
        "estimate": float(estimate),
        "estimate_exact": str(estimate),
        "reason": "The structured claim agrees with the interval/null criterion."
        if supported else "The structured claim contradicts the interval/null criterion.",
        "limitations": (
            "Only conditional consistency of a researcher-provided effect measure, "
            "claim category and 95% CI is tested; it does not validate statistical "
            "assumptions, data, causation or natural-language semantic entailment. "
            "Researcher-provided claim_text is not evaluated. "
            "Use reported_interval_exact for printed decimal precision; "
            "legacy numeric fields can round binary64."
        ),
    }


def _dimensions(mapping: Any) -> dict[str, dict[str, int]]:
    source = _obj(mapping, "dimensions")
    if not source or len(source) > 32:
        raise ValueError("dimensions must have 1..32 variables.")
    out = {}
    for variable, dims in source.items():
        if not isinstance(variable, str) or not variable.isidentifier() or variable.startswith("_"):
            raise ValueError("dimensions variable names must be safe identifiers.")
        out_dims = _obj(dims, f"dimensions.{variable}")
        if not set(out_dims).issubset(_UNIT_KEYS):
            raise ValueError("Unsupported base SI dimension.")
        checked = {}
        for unit, power in out_dims.items():
            if isinstance(power, bool) or not isinstance(power, int) or abs(power) > 12:
                raise ValueError("Dimension exponents must be integers within [-12,12].")
            if power:
                checked[unit] = power
        out[variable] = checked
    return out


def _expr_tree(expr: Any) -> ast.AST:
    if not isinstance(expr, str) or not expr or len(expr) > _MAX_EXPR_LENGTH:
        raise ValueError("Equation expression must be a nonempty string of at most 256 characters.")
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, MemoryError, ValueError) as exc:
        raise ValueError("Invalid arithmetic expression.") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise ValueError("Expression is too complex.")
    return tree.body


def _combined(a: dict[str, int], b: dict[str, int], sign: int = 1) -> dict[str, int]:
    merged = {k: a.get(k, 0) + sign * b.get(k, 0) for k in _UNIT_KEYS}
    if any(abs(power) > 24 for power in merged.values()):
        raise ValueError("Dimension exponent outside supported range.")
    return {k: v for k, v in merged.items() if v}


class _UnitMismatch(Exception):
    pass


def _exact_number(value: Any, name: str) -> Fraction:
    """Treat a displayed finite decimal as an exact rational, not binary64."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{name} must be a finite numeric value.")
    decimal = Decimal(str(value))
    if not decimal.is_finite():
        raise ValueError(f"{name} must be finite.")
    # Bound untrusted JSON magnitudes and precision before Fraction work.
    if len(decimal.as_tuple().digits) > 150 or abs(decimal.adjusted()) > 1000:
        raise ValueError(f"{name} exceeds the supported decimal bounds.")
    return _bounded_rational(Fraction(decimal), name)


def _bounded_rational(value: Fraction, name: str) -> Fraction:
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > 4096:
        raise ValueError(f"{name} exceeds safe exact-rational bit limits.")
    try:
        # Preserve established overflow safety, but never use this float
        # conversion for equality; subnormal values remain exact rationals.
        float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} exceeds supported numeric magnitude.") from exc
    return value


def _literal_zero(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and type(node.value) in (int, float) and node.value == 0


def _math_expr(node: ast.AST, dims: Mapping, values: Mapping | None) -> tuple[dict, Fraction | None]:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("Only finite numeric constants are permitted.")
        return {}, _exact_number(node.value, "constant")
    if isinstance(node, ast.Name):
        if node.id not in dims:
            raise ValueError(f"Unknown variable {node.id!r}.")
        number = _exact_number(values[node.id], f"values.{node.id}") if values is not None else None
        return dims[node.id], number
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, _ALLOWED_UNARY):
        units, value = _math_expr(node.operand, dims, values)
        return units, (-value if isinstance(node.op, ast.USub) and value is not None else value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, _ALLOWED_BINARY):
        left_u, left_v = _math_expr(node.left, dims, values)
        right_u, right_v = _math_expr(node.right, dims, values)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            # Literal zero is an additive identity in any physical dimension,
            # but a dimensionless *variable* with value zero is not silently
            # retyped as force/energy/length.
            if left_u != right_u:
                if _literal_zero(node.left):
                    out_u = right_u
                elif _literal_zero(node.right):
                    out_u = left_u
                else:
                    raise _UnitMismatch("Cannot add or subtract distinct physical dimensions.")
            else:
                out_u = left_u
            if left_v is None or right_v is None:
                return out_u, None
            result = left_v + right_v if isinstance(node.op, ast.Add) else left_v - right_v
            return out_u, _bounded_rational(result, "additive result")
        if isinstance(node.op, ast.Mult):
            out_u = _combined(left_u, right_u)
            result = None if left_v is None or right_v is None else _bounded_rational(left_v * right_v, "product")
            return out_u, result
        if isinstance(node.op, ast.Div):
            out_u = _combined(left_u, right_u, -1)
            if right_v == 0:
                raise ValueError("Division by zero.")
            result = None if left_v is None or right_v is None else _bounded_rational(left_v / right_v, "quotient")
            return out_u, result
        exponent = (node.right.value if isinstance(node.right, ast.Constant)
                    else -node.right.operand.value
                    if isinstance(node.right, ast.UnaryOp)
                    and isinstance(node.right.op, ast.USub)
                    and isinstance(node.right.operand, ast.Constant)
                    else None)
        if isinstance(exponent, bool) or not isinstance(exponent, int) or abs(exponent) > 8:
            raise ValueError("Only literal integer powers in [-8,8] are supported.")
        out_u = {k: v * exponent for k, v in left_u.items() if v * exponent}
        if any(abs(v) > 24 for v in out_u.values()):
            raise ValueError("Dimension exponent outside supported range.")
        if left_v == 0 and exponent < 0:
            raise ValueError("Negative power of zero.")
        return out_u, None if left_v is None else _bounded_rational(left_v ** exponent, "power")
    raise ValueError("Unsupported arithmetic syntax; no function calls or attribute access permitted.")


def _dimension_equation(item: Mapping) -> dict:
    dimensions = _dimensions(item.get("dimensions"))
    left, right = _expr_tree(item.get("left")), _expr_tree(item.get("right"))
    values = item.get("values")
    if values is not None:
        values = _obj(values, "values")
        if set(values) != set(dimensions):
            raise ValueError("values must provide exactly the declared equation variables.")
    tolerance = _num(item.get("absolute_tolerance", 1e-9), "absolute_tolerance")
    if tolerance < 0:
        raise ValueError("absolute_tolerance must be nonnegative.")
    try:
        lu, lv = _math_expr(left, dimensions, values)
        ru, rv = _math_expr(right, dimensions, values)
        # A literal zero may inhabit any physical dimension. If numeric
        # inputs are present, their equality is still checked separately.
        matches = lu == ru or _literal_zero(left) or _literal_zero(right)
        dim_status = "PASS" if matches else "FAIL"
    except _UnitMismatch:
        lu, ru, lv, rv, matches, dim_status = None, None, None, None, False, "FAIL"
    numeric_status = "NOT_VERIFIED"
    if lv is not None and rv is not None:
        tolerance_fraction = Fraction(Decimal(str(tolerance)))
        numeric_status = "PASS" if abs(lv - rv) <= tolerance_fraction else "FAIL"
    status = "FAIL" if dim_status == "FAIL" or numeric_status == "FAIL" else (
        "PASS" if numeric_status == "PASS" else "NOT_VERIFIED"
    )
    return {
        "kind": "dimension_equation", "status": status,
        "dimension_status": dim_status, "numeric_status": numeric_status,
        "left_units": lu, "right_units": ru, "absolute_tolerance": tolerance,
        "left_value": str(lv) if lv is not None else None,
        "right_value": str(rv) if rv is not None else None,
        "numeric_method": "exact_rational_from_displayed_inputs",
        "limitations": (
            "Values are decimal rational numbers interpreted as printed; output numeric values "
            "are strings to prevent binary64 truncation. A dimensionally consistent equation "
            "and one numeric example do not prove an identity, derivation, physical model, "
            "boundary conditions or unit scales."
        ),
    }


def _counts(value: Any, field: str) -> tuple[int, int]:
    counts = _obj(value, field)
    events, total = counts.get("events"), counts.get("total")
    if any(isinstance(x, bool) or not isinstance(x, int) for x in (events, total)):
        raise ValueError(f"{field}.events and .total must be integer counts.")
    if total <= 0 or events < 0 or events > total:
        raise ValueError(f"{field} requires 0 <= events <= total and total >= 1.")
    if total > 2**53:
        raise ValueError(f"{field}.total is too large for precise binary64 risk calculations.")
    return events, total


def _unadjusted_rr(item: Mapping) -> dict:
    a, n1 = _counts(item.get("exposed"), "exposed")
    c, n0 = _counts(item.get("control"), "control")
    if _num(item.get("confidence_level"), "confidence_level") != 0.95:
        raise ValueError("unadjusted_risk_ratio requires confidence_level=0.95.")
    reported = _obj(item.get("reported", {}), "reported")
    allowed = {"risk_ratio", "ci_lower", "ci_upper"}
    if not set(reported).issubset(allowed):
        raise ValueError("Unsupported reported field; only crude risk ratio and 95% CI are supported.")
    checked_reported = {key: _num(value, f"reported.{key}") for key, value in reported.items()}
    if any(v <= 0 for v in checked_reported.values()):
        raise ValueError("Reported crude risk ratio and bounds must be positive.")
    method = "Unadjusted cumulative risk ratio, log-Wald 95% confidence interval"
    limitations = (
        "This unadjusted cumulative risk ratio is NOT a hazard ratio, rate ratio, "
        "adjusted model estimate, time-to-event analysis or causal effect. "
        "The log-Wald CI may be inaccurate with sparse or zero event counts. "
        "It assumes independently sampled groups with fixed denominators."
    )
    if min(a, c, n1-a, n0-c) < 5:
        return {
            "kind": "unadjusted_risk_ratio", "status": "NOT_VERIFIED",
            "method": method, "reason": "Sparse/zero cell: log-Wald approximation not verified.",
            "calculated": None, "limitations": limitations,
        }
    ratio = (a/n1)/(c/n0)
    log_rr = math.log(ratio)
    standard_error = math.sqrt(1/a - 1/n1 + 1/c - 1/n0)
    critical = NormalDist().inv_cdf(0.975)
    bounds = (math.exp(log_rr-critical*standard_error), math.exp(log_rr+critical*standard_error))
    calculated = {"risk_ratio": _num(ratio, "risk_ratio"),
                  "ci_lower": _num(bounds[0], "ci_lower"),
                  "ci_upper": _num(bounds[1], "ci_upper")}
    checks = []
    for key, value in checked_reported.items():
        # Allow a small explicit floating-point computational floor even when
        # the reported value has many displayed digits.
        tol = max(_display_precision_tolerance(reported[key]), 1e-12 * abs(calculated[key]))
        delta = abs(value-calculated[key])
        precision_ratio = tol / max(abs(calculated[key]), 1e-12)
        status = ("FAIL" if delta > tol else
                  "NOT_VERIFIED" if precision_ratio >= 0.10 else "PASS")
        checks.append({"field": key, "status": status,
                       "reported": value, "calculated": calculated[key],
                       "absolute_difference": delta, "absolute_tolerance": tol,
                       "relative_rounding_uncertainty": precision_ratio})
    # A point-like printed CI is inadequate evidence that the actual nonzero
    # interval width was verified, even if individual rounded bounds match.
    if ("ci_lower" in checked_reported and "ci_upper" in checked_reported
            and checked_reported["ci_lower"] == checked_reported["ci_upper"]
            and calculated["ci_lower"] != calculated["ci_upper"]):
        for entry in checks:
            if entry["field"] in ("ci_lower", "ci_upper") and entry["status"] == "PASS":
                entry["status"] = "NOT_VERIFIED"
    return {
        "kind": "unadjusted_risk_ratio",
        "status": "FAIL" if any(x["status"] == "FAIL" for x in checks)
        else "NOT_VERIFIED" if (not checks or any(x["status"] == "NOT_VERIFIED" for x in checks))
        else "PASS",
        "method": method, "calculated": calculated, "reported_checks": checks,
        "reason": ("Insufficient reported precision for full verification."
                   if any(x["status"] == "NOT_VERIFIED" for x in checks)
                   else "Numeric comparison against reported crude values; context requires human review."),
        "limitations": limitations,
    }


_HANDLERS = {
    "semantic_ci": _semantic_ci,
    "dimension_equation": _dimension_equation,
    "unadjusted_risk_ratio": _unadjusted_rr,
}


def verify_scientific_spec(spec: Any, input_sha256: str | None = None) -> dict:
    doc = _obj(spec, "Scientific validation input")
    if doc.get("schema_version") != "1.0":
        raise ValueError("Unsupported scientific validation input schema_version.")
    items = doc.get("checks")
    if not isinstance(items, list) or not items or len(items) > _MAX_CHECKS:
        raise ValueError("checks must be a nonempty array of at most 100 items.")
    output = []
    used: set[str] = set()
    for item in items:
        check = _obj(item, "check")
        identity = check.get("id")
        if not isinstance(identity, str) or not identity or len(identity) > 128 or identity in used:
            raise ValueError("check IDs must be unique nonempty strings of at most 128 characters.")
        used.add(identity)
        kind = check.get("kind")
        if kind not in _HANDLERS:
            raise ValueError("Unsupported scientific check kind.")
        result = _HANDLERS[kind](check)
        result["id"] = identity
        output.append(result)
    return {
        "schema_version": "1.0", "algorithm_version": "advanced-science-pilot-3",
        "input_sha256": input_sha256, "status": _status_summary(output),
        "checks": output,
        "scope_note": (
            "Only explicitly supplied structured claims, bounded SI-dimensional equations "
            "and unadjusted crude risk ratios are examined. No general manuscript "
            "semantic understanding, algebraic proof, causal identification, "
            "unvalidated statistical model, or expert verdict is provided."
        ),
    }


def verify_scientific_file(path: str | Path) -> dict:
    target = Path(path).expanduser().resolve()
    if target.stat().st_size > _MAX_BYTES:
        raise ValueError("Scientific validation JSON exceeds the 1 MiB input bound.")
    raw = target.read_bytes()
    if len(raw) > _MAX_BYTES:
        raise ValueError("Scientific validation JSON exceeds the 1 MiB input bound.")

    def reject_constant(value: str) -> None:
        raise ValueError(f"Non-standard numeric constant {value!r} is not permitted.")

    doc = json.loads(raw.decode("utf-8-sig"), parse_float=Decimal,
                     parse_constant=reject_constant, object_pairs_hook=reject_duplicate_keys)
    input_sha256 = hashlib.sha256(raw).hexdigest()
    report = verify_scientific_spec(doc, input_sha256)
    revision, dirty = _source_revision()
    source_sha, scope, included_files = _source_tree_sha256()
    report["reproducibility_manifest"] = {
        "manifest_schema_version": "1.0",
        "input_sha256": input_sha256,
        "algorithm_version": report["algorithm_version"],
        "source_code_revision": revision,
        "working_tree_dirty": dirty,
        "source_code_sha256": source_sha,
        "source_code_hash_scope": scope,
        "source_code_hash_file_count": len(included_files),
        "software": {
            "auditor_version": __version__,
            "python_version": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "dependencies": {
                "scipy": _package_version("scipy"),
                "jsonschema": _package_version("jsonschema"),
                "pypdf": _package_version("pypdf"),
            },
        },
    }
    return report
