"""Meaningful negative controls and safe-boundary checks for advanced pilot."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sra.scientific_validation import (
    _MAX_BYTES, verify_scientific_file, verify_scientific_spec,
)


def math_case(left="force", right="mass * acceleration", values=None):
    return {
        "id": "eq", "kind": "dimension_equation", "left": left, "right": right,
        "dimensions": {
            "force": {"kg": 1, "m": 1, "s": -2},
            "mass": {"kg": 1},
            "acceleration": {"m": 1, "s": -2},
        },
        **({"values": values} if values is not None else {}),
    }


def semantic_case():
    return {"id": "sem", "kind": "semantic_ci", "claim_type": "not_significant",
            "effect_measure": "risk_ratio", "confidence_level": 0.95,
            "estimate": 1.0, "ci_lower": 0.8, "ci_upper": 1.2}


def rr_case():
    return {"id": "rr", "kind": "unadjusted_risk_ratio",
            "confidence_level": 0.95,
            "exposed": {"events": 10, "total": 75},
            "control": {"events": 12, "total": 225}}


class AdvancedScienceBoundaryTests(unittest.TestCase):
    def check(self, *items):
        return verify_scientific_spec({"schema_version": "1.0", "checks": list(items)})

    def test_semantic_rejects_unknown_categories_measure_and_level(self):
        for name, value in (
            ("claim_type", "indisputable_causation"),
            ("effect_measure", "generic_effect"),
            ("confidence_level", 0.9),
        ):
            case = semantic_case()
            case[name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.check(case)

    def test_science_spec_rejects_bad_schema_empty_and_oversized(self):
        for doc in (
            {}, {"schema_version": "9.9", "checks": [semantic_case()]},
            {"schema_version": "1.0", "checks": []},
            {"schema_version": "1.0", "checks": {}},
            {"schema_version": "1.0", "checks": [dict(semantic_case(), id=str(i)) for i in range(101)]},
        ):
            with self.subTest(doc=str(doc)[:50]), self.assertRaises(ValueError):
                verify_scientific_spec(doc)

    def test_science_spec_rejects_broken_input_check_types(self):
        for item in (4, [], "str", None):
            with self.subTest(item=item), self.assertRaises(ValueError):
                self.check(item)

    def test_dimensions_bound_variables_units_and_exponents(self):
        base = math_case()
        mutants = []
        c = dict(base); c["dimensions"] = {}; mutants.append(c)
        c = dict(base); c["dimensions"] = {f"var{i}": {} for i in range(33)}; mutants.append(c)
        c = dict(base); c["dimensions"] = {"_hidden": {}}; mutants.append(c)
        c = dict(base); c["dimensions"] = {"force": {"Newton": 1}}; mutants.append(c)
        c = dict(base); c["dimensions"] = {"force": {"kg": True}}; mutants.append(c)
        c = dict(base); c["dimensions"] = {"force": {"kg": 13}}; mutants.append(c)
        for bad in mutants:
            with self.subTest(dimensions=bad["dimensions"]), self.assertRaises(ValueError):
                self.check(bad)

    def test_expression_rejects_invalid_type_syntax_and_excessive_ast(self):
        for expr in (None, "", 123, "a" * 257, "force+", "1+"*70+"1"):
            c = math_case(right=expr)
            with self.subTest(expr=str(expr)[:20]), self.assertRaises(ValueError):
                self.check(c)

    def test_numeric_literals_reject_nonnumeric_data(self):
        for expr in ("True", "None", "'x'", "False"):
            c=math_case(right=expr)
            with self.subTest(expr=expr),self.assertRaises(ValueError):
                self.check(c)

    def test_unary_negation_and_add_subtract(self):
        c=math_case(left="force", right="mass * -acceleration",
                    values={"force":-10, "mass":2, "acceleration":5})
        self.assertEqual(self.check(c)["checks"][0]["status"],"PASS")
        c["right"]="mass * +acceleration"
        self.assertEqual(self.check(c)["checks"][0]["numeric_status"],"FAIL")
        c=math_case(left="force+force",right="2*force",
                    values={"force":10,"mass":2,"acceleration":5})
        self.assertEqual(self.check(c)["checks"][0]["status"],"PASS")
        c["left"]="force-force";c["right"]="0*force"
        self.assertEqual(self.check(c)["checks"][0]["status"],"PASS")
        c.pop("values")
        self.assertEqual(self.check(c)["checks"][0]["status"],"NOT_VERIFIED")

    def test_numeric_division_and_dimensional_units(self):
        c=math_case(left="force/mass",right="acceleration",
                    values={"force":10,"mass":2,"acceleration":5})
        self.assertEqual(self.check(c)["checks"][0]["status"],"PASS")
        c["left"]="force/(mass*2)"
        self.assertEqual(self.check(c)["checks"][0]["numeric_status"],"FAIL")
        c.pop("values")
        self.assertEqual(self.check(c)["checks"][0]["status"],"NOT_VERIFIED")

    def test_valid_integer_powers_and_negative_powers(self):
        c=math_case(left="mass*mass",right="mass**2",
                    values={"force":10,"mass":2,"acceleration":5})
        self.assertEqual(self.check(c)["checks"][0]["status"],"PASS")
        c["left"]="1/mass";c["right"]="mass**-1"
        self.assertEqual(self.check(c)["checks"][0]["status"],"PASS")
        c.pop("values")
        self.assertEqual(self.check(c)["checks"][0]["status"],"NOT_VERIFIED")

    def test_dimension_exponent_combination_and_power_are_bounded(self):
        c=math_case(left="high*high*high",right="high")
        c["dimensions"]["high"]={"kg":12}
        with self.assertRaises(ValueError):
            self.check(c)
        c["left"]="high**8"
        with self.assertRaises(ValueError):
            self.check(c)

    def test_numeric_power_overflow_and_zero_negative_power_rejected(self):
        c=math_case(left="mass",right="mass**8",
                    values={"force":10,"mass":1e80,"acceleration":5})
        with self.assertRaises(ValueError):
            self.check(c)
        c["values"]["mass"]=0
        c["right"]="mass**-1"
        with self.assertRaises(ValueError):
            self.check(c)

    def test_power_requires_literal_bounded_integer(self):
        for right in ("mass**acceleration","mass**1.5","mass**9"):
            c=math_case(left="mass",right=right)
            with self.subTest(right=right),self.assertRaises(ValueError):
                self.check(c)

    def test_math_validation_requires_exact_values_and_tolerance(self):
        case=math_case(values={"mass":2,"force":10})
        with self.assertRaises(ValueError):
            self.check(case)
        case=math_case(values={"mass":2,"force":10,"acceleration":5},
                       right="mass*acceleration")
        case["absolute_tolerance"]=-0.001
        with self.assertRaises(ValueError):
            self.check(case)

    def test_ratio_parameters_and_reported_values_rejected(self):
        mutants=[]
        for field, bad in (
            ("confidence_level",0.90), ("reported",{"hazard_ratio":2.5}),
            ("reported",{"risk_ratio":-2.5})):
            case=rr_case();case[field]=bad;mutants.append(case)
        for case in mutants:
            with self.subTest(case=case),self.assertRaises(ValueError):
                self.check(case)

    def test_reported_ratio_passes_and_input_is_immutable(self):
        case=rr_case()
        case["reported"]={"risk_ratio":2.5}
        copy=json.loads(json.dumps(case))
        row=self.check(case)["checks"][0]
        self.assertEqual(row["status"],"PASS")
        self.assertEqual(case,copy)

    def test_unreasonably_large_contingency_denominators_are_rejected(self):
        case = rr_case()
        case["exposed"] = {"events": 10, "total": 10**30}
        with self.assertRaisesRegex(ValueError, "precise"):
            self.check(case)

    def test_zero_event_or_non_event_sparse_cells_not_inferred(self):
        c=rr_case()
        for a,n1,ctrl, n0 in ((0,75,12,225),(75,75,12,225),(10,75,0,225),(10,75,225,225)):
            c["exposed"]={"events":a,"total":n1}
            c["control"]={"events":ctrl,"total":n0}
            with self.subTest(a=a,ctrl=ctrl):
                self.assertEqual(self.check(c)["checks"][0]["status"],"NOT_VERIFIED")

    def test_json_decimal_confidence_level_is_accepted_and_checked(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "json_decimal.json"
            case = semantic_case()
            path.write_text(json.dumps({
                "schema_version":"1.0", "checks":[case, rr_case()]
            }), encoding="utf-8")
            result = verify_scientific_file(path)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertEqual(result["checks"][0]["status"], "PASS")
            self.assertEqual(result["checks"][1]["status"], "NOT_VERIFIED")

    def test_file_size_and_nonstandard_constants_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"payload.json"
            p.write_bytes(b" " * (_MAX_BYTES+1))
            with self.assertRaises(ValueError):
                verify_scientific_file(p)
            p.write_text('{"schema_version":"1.0","checks":[NaN]}')
            with self.assertRaises(ValueError):
                verify_scientific_file(p)

    def test_concurrent_file_growth_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"payload.json"
            p.write_text("{}")
            with patch.object(Path,"stat",return_value=SimpleNamespace(st_size=2)):
                with patch.object(Path,"read_bytes",return_value=b"x"*(_MAX_BYTES+1)):
                    with self.assertRaisesRegex(ValueError,"1 MiB"):
                        verify_scientific_file(p)


if __name__=="__main__":
    unittest.main()
