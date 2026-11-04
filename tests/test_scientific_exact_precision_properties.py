"""Numeric precision and property-based regression checks."""
import math
import random
import unittest
from decimal import Decimal
from sra.scientific_validation import verify_scientific_spec


def check(item):
    return verify_scientific_spec({"schema_version":"1.0","checks":[item]})["checks"][0]


class ScientificPrecisionProperties(unittest.TestCase):
    def test_invalid_numeric_parameter_type_is_rejected(self):
        item={"id":"e","kind":"dimension_equation","left":"x","right":"x",
              "dimensions":{"x":{}},"values":{"x":"not a number"}}
        with self.assertRaisesRegex(ValueError, "finite numeric"):
            check(item)

    def test_nan_or_infinite_numeric_parameters_are_rejected(self):
        for value in (float("nan"),float("inf"),float("-inf")):
            with self.subTest(value=str(value)):
                item={"id":"e","kind":"dimension_equation","left":"x","right":"x",
                      "dimensions":{"x":{}},"values":{"x":value}}
                with self.assertRaisesRegex(ValueError, "finite"):
                    check(item)

    def test_decimal_magnitude_and_precision_limits(self):
        for value in (Decimal("1e-1001"), Decimal("1e1001"),
                      Decimal("1."+"2"*160)):
            with self.subTest(value=str(value)[:20]):
                item={"id":"e","kind":"dimension_equation","left":"x","right":"x",
                      "dimensions":{"x":{}},"values":{"x":value}}
                with self.assertRaisesRegex(ValueError, "bounds"):
                    check(item)

    def test_exact_rational_bit_budget_rejects_extreme_powers(self):
        item={"id":"e","kind":"dimension_equation","left":"x*x","right":"x",
              "dimensions":{"x":{}},"values":{"x":Decimal("1e-1000")}}
        with self.assertRaisesRegex(ValueError, "bit"):
            check(item)

    def test_left_literal_zero_has_polymorphic_dimension(self):
        item={"id":"e","kind":"dimension_equation","left":"0 + force",
              "right":"force","dimensions":{"force":{"kg":1,"m":1,"s":-2}},
              "values":{"force":8},"absolute_tolerance":0}
        self.assertEqual(check(item)["status"],"PASS")

    def test_narrow_reported_collapsed_confidence_interval_not_accepted(self):
        item={"id":"r","kind":"unadjusted_risk_ratio","confidence_level":0.95,
              "exposed":{"events":500000,"total":1000000},
              "control":{"events":500000,"total":1000000},
              "reported":{"risk_ratio":Decimal("1.00"),
                          "ci_lower":Decimal("1.00"),
                          "ci_upper":Decimal("1.00")}}
        row=check(item)
        self.assertEqual(row["status"],"NOT_VERIFIED")
        ci=[f for f in row["reported_checks"] if f["field"].startswith("ci_")]
        self.assertEqual([x["status"] for x in ci],["NOT_VERIFIED","NOT_VERIFIED"])

    def test_tiny_risk_ratio_uses_relative_not_unit_floor_tolerance(self):
        case={"id":"rr","kind":"unadjusted_risk_ratio","confidence_level":0.95,
              "exposed":{"events":1000,"total":2**53},
              "control":{"events":50,"total":100},
              "reported":{"risk_ratio":9e-13}}
        row=check(case)
        self.assertEqual(row["status"],"FAIL")
        self.assertLess(row["reported_checks"][0]["absolute_tolerance"],1e-13)
        case["reported"]["risk_ratio"]=2.22e-13
        self.assertEqual(check(case)["status"],"PASS")

    def test_metaphoric_same_scaling_property_for_exact_values(self):
        rng=random.Random(20261104)
        for _ in range(40):
            exponent=rng.randint(0,100)
            offset=Decimal(str(rng.randint(1,9)))/Decimal(10**rng.randint(1,6))
            x=Decimal(10)**exponent
            item={"id":"identity","kind":"dimension_equation",
                  "left":"(x + y) - x","right":"y",
                  "dimensions":{"x":{},"y":{}},"values":{"x":x,"y":offset},
                  "absolute_tolerance":0}
            with self.subTest(exponent=exponent,offset=str(offset)):
                row=check(item)
                self.assertEqual(row["status"],"PASS")
                self.assertEqual(row["numeric_method"],"exact_rational_from_displayed_inputs")


if __name__ == "__main__":
    unittest.main()
