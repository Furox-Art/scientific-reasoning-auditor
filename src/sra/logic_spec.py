"""Dependency-independent validation of bounded formal logic inputs; never eval."""
from __future__ import annotations

import ast
import hashlib
import json
import keyword
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from sra.document import ParsedDocument, SourceIdentityError
from sra.json_utils import reject_duplicate_keys

MAX_BYTES = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_NUMERIC = {"Int", "Real"}


@dataclass(frozen=True)
class Term:
    kind: str
    sort: str
    value: Any = None
    args: tuple[Term, ...] = ()


@dataclass(frozen=True)
class LogicProblem:
    variables: dict[str, str]
    assumptions: tuple[dict, ...]
    claims: tuple[dict, ...]
    terms: dict[str, Term]
    input_sha256: str
    source_binding: dict


def _reject_constant(token: str) -> None:
    raise ValueError("Nonstandard JSON constants are not allowed.")


def _number(value: Fraction, sort: str) -> Term:
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > 256:
        raise ValueError("Numeric expression exceeds the 256-bit bound.")
    return Term("number", sort, str(value))


def parse_expression(expression: str, variables: dict[str, str]) -> tuple[Term, int]:
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 512:
        raise ValueError("Expressions must contain 1 to 512 characters.")
    expression = expression.strip()
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("Invalid bounded logic expression.") from exc
    nodes = sum(1 for _ in ast.walk(tree))
    if nodes > 128:
        raise ValueError("Expression exceeds the 128-node bound.")

    def visit(node: ast.AST, depth: int = 0) -> Term:
        if depth > 32:
            raise ValueError("Expression nesting exceeds 32 levels.")
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise ValueError("Expression uses an undeclared variable.")
            return Term("variable", variables[node.id], node.id)
        if isinstance(node, ast.Constant):
            if type(node.value) is bool:
                return Term("boolean", "Bool", node.value)
            if type(node.value) not in (int, float):
                raise ValueError("Only Boolean and numeric literals are supported.")
            token = ast.get_source_segment(expression, node)
            if len(token) > 64:
                raise ValueError("Numeric literal exceeds 64 characters.")
            decimal = re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE]([+-]?[0-9]+))?", token)
            if decimal is None or abs(int(decimal.group(1) or "0")) > 64:
                raise ValueError("Numeric literal requires decimal notation and an exponent in [-64,64].")
            value = Fraction(token)
            return _number(value, "Int" if type(node.value) is int else "Real")
        if isinstance(node, ast.BoolOp):
            terms = tuple(visit(part, depth + 1) for part in node.values)
            if any(part.sort != "Bool" for part in terms):
                raise ValueError("Boolean operators require Boolean arguments.")
            return Term("and" if isinstance(node.op, ast.And) else "or", "Bool", args=terms)
        if isinstance(node, ast.UnaryOp):
            term = visit(node.operand, depth + 1)
            if isinstance(node.op, ast.Not) and term.sort == "Bool":
                return Term("not", "Bool", args=(term,))
            if term.sort in _NUMERIC and isinstance(node.op, (ast.UAdd, ast.USub)):
                if isinstance(node.op, ast.UAdd):
                    return term
                return _number(-Fraction(term.value), term.sort) if term.kind == "number" else Term("neg", term.sort, args=(term,))
            raise ValueError("Unsupported unary operator or operand type.")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ("implies", "iff") or len(node.args) != 2 or node.keywords:
                raise ValueError("Only implies(a,b) and iff(a,b) calls are allowed.")
            terms = tuple(visit(part, depth + 1) for part in node.args)
            if any(part.sort != "Bool" for part in terms):
                raise ValueError("Logical relations require Boolean arguments.")
            return Term(node.func.id, "Bool", args=terms)
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left, depth + 1), visit(node.right, depth + 1)
            if left.sort not in _NUMERIC or right.sort not in _NUMERIC:
                raise ValueError("Arithmetic requires numeric arguments.")
            operators = {ast.Add: "add", ast.Sub: "sub", ast.Mult: "mul", ast.Div: "div"}
            op = operators.get(type(node.op))
            if op is None or (op == "mul" and left.kind != "number" and right.kind != "number"):
                raise ValueError("Only linear arithmetic is supported.")
            if op == "div" and (right.kind != "number" or Fraction(right.value) == 0):
                raise ValueError("Division requires a nonzero constant divisor.")
            sort = "Real" if op == "div" or "Real" in (left.sort, right.sort) else "Int"
            if left.kind == right.kind == "number":
                a, b = Fraction(left.value), Fraction(right.value)
                value = {"add": lambda: a+b, "sub": lambda: a-b,
                         "mul": lambda: a*b, "div": lambda: a/b}[op]()
                return _number(value, sort)
            return Term(op, sort, args=(left, right))
        if isinstance(node, ast.Compare):
            terms = [visit(node.left, depth + 1)] + [visit(part, depth + 1) for part in node.comparators]
            operations = {ast.Eq: "eq", ast.NotEq: "ne", ast.Lt: "lt", ast.LtE: "le", ast.Gt: "gt", ast.GtE: "ge"}
            comparisons = []
            for left, right, operation in zip(terms, terms[1:], node.ops):
                op = operations.get(type(operation))
                numeric = left.sort in _NUMERIC and right.sort in _NUMERIC
                if op is None or not (numeric or left.sort == right.sort == "Bool" and op in ("eq", "ne")):
                    raise ValueError("Incompatible comparison types or operator.")
                comparisons.append(Term(op, "Bool", args=(left, right)))
            return comparisons[0] if len(comparisons) == 1 else Term("and", "Bool", args=tuple(comparisons))
        raise ValueError("Unsupported expression syntax; attributes, indexing and code are forbidden.")

    result = visit(tree.body)
    if result.sort != "Bool":
        raise ValueError("Assumptions and claims must be Boolean formulas.")
    return result, nodes


def prepare_logic_spec(value: dict | str, document: ParsedDocument | None = None) -> LogicProblem:
    """Validate every input and source mapping before importing the solver."""
    try:
        raw = value if isinstance(value, str) else json.dumps(value, allow_nan=False, ensure_ascii=False)
        if len(raw) > MAX_BYTES or len(raw.encode("utf-8")) > MAX_BYTES:
            raise ValueError("Logic specification exceeds the 1 MiB bound.")
        spec = json.loads(raw, parse_constant=_reject_constant, object_pairs_hook=reject_duplicate_keys)
    except (TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("Logic specification must be bounded JSON.") from exc
    allowed = {"schema_version", "variables", "assumptions", "claims", "source_sha256", "extracted_text_sha256"}
    if not isinstance(spec, dict) or set(spec) - allowed or spec.get("schema_version") != "1.0":
        raise ValueError("Unsupported logic schema or fields.")
    variables = spec.get("variables")
    if not isinstance(variables, dict) or len(variables) > 64:
        raise ValueError("variables must be an object with at most 64 entries.")
    for name, sort in variables.items():
        if not _IDENTIFIER.fullmatch(name) or keyword.iskeyword(name) or name in ("implies", "iff") or sort not in ("Bool", "Int", "Real"):
            raise ValueError("Variables require simple identifiers and Bool, Int or Real sorts.")
    for key in ("source_sha256", "extracted_text_sha256"):
        if key in spec and (not isinstance(spec[key], str) or not _DIGEST.fullmatch(spec[key])):
            raise ValueError("Source identities must be lowercase SHA-256 digests.")
    text_hash = hashlib.sha256(document.text.encode("utf-8")).hexdigest() if document else None
    if document and (spec.get("source_sha256") != document.sha256 or spec.get("extracted_text_sha256") != text_hash):
        raise SourceIdentityError("Logic specification does not match the manuscript source identities.")
    seen, terms, groups, total_nodes = set(), {}, {}, 0
    for name, maximum in (("assumptions", 64), ("claims", 32)):
        items = spec.get(name)
        if not isinstance(items, list) or len(items) > maximum or name == "claims" and not items:
            raise ValueError(f"{name} must be a bounded array; at least one claim is required.")
        records = []
        for item in items:
            if not isinstance(item, dict) or set(item) - {"id", "expression", "source_quote", "line"}:
                raise ValueError("Invalid statement object or fields.")
            identity = item.get("id")
            if not isinstance(identity, str) or not _IDENTIFIER.fullmatch(identity) or identity in seen:
                raise ValueError("Statement IDs must be unique simple identifiers.")
            seen.add(identity)
            term, nodes = parse_expression(item.get("expression"), variables)
            total_nodes += nodes
            if total_nodes > 5000:
                raise ValueError("Logic problem exceeds the total 5000-node bound.")
            terms[identity] = term
            source = {"status": "not_provided"}
            line = item.get("line")
            if line is not None and (type(line) is not int or line < 1):
                raise ValueError("Source line must be a positive integer.")
            if "source_quote" in item:
                quote = item["source_quote"]
                if not isinstance(quote, str) or not 12 <= len(quote) <= 2000:
                    raise ValueError("Source quotes require 12 to 2000 characters.")
                source = {"status": "unbound", "quote": quote, "line": line}
                if document:
                    offsets = [match.start() for match in re.finditer(re.escape(quote), document.text)]
                    positions = [(offset, document.text.count("\n", 0, offset) + 1) for offset in offsets]
                    found = next((position for position in positions if line is None or position[1] == line), None)
                    if found is None:
                        raise SourceIdentityError("Source quote or its line does not match the manuscript.")
                    source = {"status": "quote_present_semantics_unverified", "quote": quote,
                              "line": found[1], "occurrences": len(positions)}
            elif line is not None:
                raise ValueError("Source line requires a source_quote.")
            records.append({"id": identity, "expression": item["expression"].strip(), "source": source})
        groups[name] = tuple(records)
    canonical = json.dumps(spec, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    binding = {"status": "source_matched" if document else "unbound",
               "source_sha256": document.sha256 if document else None,
               "extracted_text_sha256": text_hash, "formalization_semantics_verified": False}
    return LogicProblem(dict(sorted(variables.items())), groups["assumptions"], groups["claims"], terms,
                        hashlib.sha256(canonical.encode("utf-8")).hexdigest(), binding)
