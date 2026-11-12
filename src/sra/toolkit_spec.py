"""Bounded, dependency-independent input validation. No executable expressions."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from decimal import Decimal
from fractions import Fraction

from sra.document import SourceIdentityError
from sra.json_utils import reject_duplicate_keys
from sra.extended_inspection import EXTRA_KINDS

KINDS = ("polynomial_identity", "derivative", "antiderivative", "unit_conversion",
         "statistical_replay", "claim_candidates", "citation_match") + EXTRA_KINDS
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,31}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE]([+-]?[0-9]+))?\Z")


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def number(value):
    token = str(value)
    match = _DECIMAL.fullmatch(token)
    if type(value) not in (str, int, float, Decimal) or len(token) > 64 or not match or abs(int(match.group(1) or "0")) > 64:
        raise ValueError("Numbers require finite decimal notation, at most 64 characters and exponent in [-64,64].")
    return Decimal(token)


def _fields(item, required, optional=()):
    if not isinstance(item, dict) or set(item) - set(required) - set(optional) or set(required) - set(item):
        raise ValueError("Missing or unsupported structured fields.")


def _text(value, maximum):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError("Text is empty or exceeds its bound.")
    return value


def _poly_bound(poly):
    if len(poly) > 256 or any(sum(key) > 12 or max(value.numerator.bit_length(), value.denominator.bit_length()) > 512 for key, value in poly.items()):
        raise ValueError("Polynomial exceeds degree 12, 256 terms or 512-bit coefficients.")
    return {key:value for key,value in poly.items() if value}


def polynomial(expression, variables):
    """Compile a tiny arithmetic AST to exact sparse coefficients before SymPy."""
    expression = _text(expression, 512).strip()
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("Invalid polynomial expression.") from exc
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ValueError("Polynomial exceeds 128 syntax nodes.")
    zero = (0,) * len(variables)

    def multiply(left, right):
        result = {}
        for a, av in left.items():
            for b, bv in right.items():
                key = tuple(x+y for x,y in zip(a,b))
                result[key] = result.get(key, Fraction(0)) + av*bv
            _poly_bound(result)
        return _poly_bound(result)

    def visit(node, depth=0):
        if depth > 24:
            raise ValueError("Polynomial nesting exceeds 24 levels.")
        if isinstance(node, ast.Name) and node.id in variables:
            key = tuple(int(i == variables.index(node.id)) for i in range(len(variables)))
            return {key:Fraction(1)}
        if isinstance(node, ast.Constant) and type(node.value) in (int,float):
            return _poly_bound({zero:Fraction(number(ast.get_source_segment(expression,node)))})
        if isinstance(node, ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            return {k:v*(-1 if isinstance(node.op,ast.USub) else 1) for k,v in visit(node.operand,depth+1).items()}
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            if not isinstance(node.right,ast.Constant) or type(node.right.value) is not int or not 0 <= node.right.value <= 8:
                raise ValueError("Powers require an integer literal from 0 to 8.")
            base, result = visit(node.left,depth+1), {zero:Fraction(1)}
            for _ in range(node.right.value):
                result = multiply(result,base)
            return result
        if isinstance(node, ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            left, right = visit(node.left,depth+1), visit(node.right,depth+1)
            if isinstance(node.op, ast.Mult):
                return multiply(left,right)
            if isinstance(node.op, ast.Div):
                if set(right) != {zero}:
                    raise ValueError("Division requires a nonzero constant polynomial.")
                return _poly_bound({k:v/right[zero] for k,v in left.items()})
            result = dict(left)
            for key, value in right.items():
                result[key] = result.get(key,Fraction(0)) + value*(-1 if isinstance(node.op,ast.Sub) else 1)
            return _poly_bound(result)
        raise ValueError("Only declared variables and bounded polynomial arithmetic are permitted.")

    return visit(tree.body)


def unit_expression(expression):
    """Return an inert unit AST: names, products, ratios and small integer powers."""
    expression = _text(expression,128).strip()
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError,RecursionError) as exc:
        raise ValueError("Invalid unit expression.") from exc
    if sum(1 for _ in ast.walk(tree)) > 48:
        raise ValueError("Unit expression exceeds 48 nodes.")

    def visit(node):
        if isinstance(node,ast.Name) and _NAME.fullmatch(node.id):
            return ("unit",node.id)
        if isinstance(node,ast.Constant) and type(node.value) is int and node.value == 1:
            return ("unit","dimensionless")
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Mult,ast.Div)):
            return ("mul" if isinstance(node.op,ast.Mult) else "div",visit(node.left),visit(node.right))
        if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Pow):
            exponent = node.right
            sign = -1 if isinstance(exponent,ast.UnaryOp) and isinstance(exponent.op,ast.USub) else 1
            if sign == -1:
                exponent = exponent.operand
            if isinstance(exponent,ast.Constant) and type(exponent.value) is int and 0 <= exponent.value <= 8:
                return ("pow",visit(node.left),sign*exponent.value)
        raise ValueError("Unsupported unit expression; use unit names and powers in [-8,8].")

    return visit(tree.body)


def _check(item, document):
    if isinstance(item,dict) and item.get('kind') in EXTRA_KINDS:
        if not isinstance(item.get('id'),str) or not _NAME.fullmatch(item['id']):
            raise ValueError('Check ID must be a simple identifier.')
        from sra.extended_inspection import prepare_extra
        return prepare_extra(item,document)
    _fields(item,("id","kind"),set().union(*[
        {"variables","left","right","variable"}, {"value","from_unit","to_unit","reported","atol","rtol"},
        {"test","groups"}, {"text","language"}, {"claim","passages"}]))
    if not isinstance(item["id"],str) or not _NAME.fullmatch(item["id"]) or item["kind"] not in KINDS:
        raise ValueError("Unsupported check identifier or kind.")
    kind = item["kind"]
    base = ("id","kind")
    result = dict(item)
    if kind in KINDS[:3]:
        _fields(item,base+("variables","left","right")+ (() if kind == "polynomial_identity" else ("variable",)))
        variables = item["variables"]
        if not isinstance(variables,list) or not 1 <= len(variables) <= 4 or any(not isinstance(v,str) or not _NAME.fullmatch(v) for v in variables) or len(set(variables)) != len(variables):
            raise ValueError("Declare one to four distinct variable identifiers.")
        if kind != "polynomial_identity" and item["variable"] not in variables:
            raise ValueError("Calculus variable must be declared.")
        result["polynomials"] = [polynomial(item[key],variables) for key in ("left","right")]
    elif kind == "unit_conversion":
        _fields(item,base+("value","from_unit","to_unit","reported"),("atol",))
        result["units"] = [unit_expression(item[key]) for key in ("from_unit","to_unit")]
        for key in ("value","reported"):
            result[key] = str(number(item[key]))
        result["atol"] = str(number(item.get("atol","1e-9")))
        if number(result["atol"]) < 0:
            raise ValueError("Tolerance must be nonnegative.")
    elif kind == "statistical_replay":
        _fields(item,base+("test","groups"),("reported","atol","rtol"))
        groups = item["groups"]
        if item["test"] not in ("welch_t","paired_t","pearson","one_way_anova") or not isinstance(groups,list) or not 2 <= len(groups) <= 8 or (item["test"] != "one_way_anova" and len(groups) != 2):
            raise ValueError("Unsupported replay test or group count.")
        if any(not isinstance(g,list) or not 2 <= len(g) <= 2000 for g in groups) or sum(map(len,groups)) > 10000:
            raise ValueError("Replay needs 2..2000 values per group and at most 10000 values total.")
        if item["test"] in ("paired_t","pearson") and len(groups[0]) != len(groups[1]):
            raise ValueError("Paired observations must have equal lengths.")
        result["groups"] = [[str(number(v)) for v in group] for group in groups]
        reported = item.get("reported",{})
        if not isinstance(reported,dict) or set(reported)-{"statistic","p_value"} or ("reported" in item and not reported):
            raise ValueError("Reported replay metrics must name statistic or p_value.")
        result["reported"] = {key:str(number(v)) for key,v in reported.items()}
        if "p_value" in reported and not 0 <= number(reported["p_value"]) <= 1:
            raise ValueError("Reported p_value must be between zero and one.")
        for key,default in (("atol","1e-9"),("rtol","1e-7")):
            result[key] = str(number(item.get(key,default)))
            if number(result[key]) < 0:
                raise ValueError("Tolerance must be nonnegative.")
    elif kind == "claim_candidates":
        _fields(item,base,("text","language"))
        if document is not None and "text" in item:
            raise ValueError("Bound candidate extraction uses manuscript text; do not supply alternate text.")
        result["text"] = _text(document.text if document is not None else item.get("text"),100000)
        result["language"] = item.get("language","xx")
        if result["language"] not in ("xx","en","tr"):
            raise ValueError("Sentence tokenizer language must be xx, en or tr.")
    else:
        _fields(item,base+("claim","passages"))
        _text(item["claim"],2000)
        if document is not None and item["claim"] not in document.text:
            raise SourceIdentityError("Citation query is absent from the bound manuscript text.")
        passages = item["passages"]
        if not isinstance(passages,list) or not 1 <= len(passages) <= 16:
            raise ValueError("Supply 1..16 local cited passages.")
        seen = set()
        for row in passages:
            _fields(row,("id","text","sha256"))
            if not isinstance(row["id"],str) or not _NAME.fullmatch(row["id"]) or row["id"] in seen:
                raise ValueError("Passage identifiers must be distinct simple names.")
            seen.add(row["id"])
            if digest(_text(row["text"],2000)) != row["sha256"]:
                raise ValueError("Cited passage hash mismatch.")
    return result


def prepare_toolkit_spec(value, document=None):
    def reject(token):
        raise ValueError("Non-finite JSON constants are not permitted.")
    try:
        raw = value if isinstance(value,str) else json.dumps(value,allow_nan=False,ensure_ascii=False)
        if len(raw) > 1024*1024 or len(raw.encode("utf-8")) > 1024*1024:
            raise ValueError("Toolkit input exceeds 1 MiB.")
        spec = json.loads(raw,parse_float=Decimal,parse_constant=reject,object_pairs_hook=reject_duplicate_keys)
    except (TypeError,RecursionError,UnicodeError) as exc:
        raise ValueError("Toolkit input must be bounded JSON.") from exc
    _fields(spec,("schema_version","checks"),("source_sha256","extracted_text_sha256"))
    if spec["schema_version"] != "1.0" or not isinstance(spec["checks"],list) or not 1 <= len(spec["checks"]) <= 32:
        raise ValueError("Toolkit schema 1.0 requires 1..32 checks.")
    for key in ("source_sha256","extracted_text_sha256"):
        if key in spec and (not isinstance(spec[key],str) or not _HASH.fullmatch(spec[key])):
            raise ValueError("Source identities must be lowercase SHA-256 digests.")
    text_hash = digest(document.text) if document is not None else None
    if document is not None and (spec.get("source_sha256") != document.sha256 or spec.get("extracted_text_sha256") != text_hash):
        raise SourceIdentityError("Toolkit specification does not match manuscript identities.")
    checks = [_check(item,document) for item in spec["checks"]]
    if sum(item['kind'].startswith('symbolic_') for item in checks)>8:
        raise ValueError('At most eight bounded symbolic checks per report.')
    if len({item["id"] for item in checks}) != len(checks):
        raise ValueError("Check identifiers must be unique.")
    canonical = json.dumps(spec,sort_keys=True,ensure_ascii=False,default=str,separators=(",",":"))
    return {"checks":checks,"input_sha256":digest(canonical),
            "source_binding":{"status":"source_matched" if document is not None else "unbound",
                              "source_sha256":document.sha256 if document is not None else None,
                              "extracted_text_sha256":text_hash,"semantic_mapping_verified":False}}
