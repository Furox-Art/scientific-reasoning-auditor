"""Numeric and confidence-interval boundary regression tests."""
import unittest
from decimal import Decimal

from sra.scientific_validation import verify_scientific_spec


def check(case):
    return verify_scientific_spec({"schema_version":"1.0","checks":[case]})["checks"][0]


def eq(left, right, vals, dims=None):
    return {"id":"eq","kind":"dimension_equation",
            "left":left,"right":right,"absolute_tolerance":0,
            "dimensions":dims or {"x":{}},"values":vals}


def ci(kind, lo, hi, estimate, measure="risk_ratio", claim_text=None):
    spec={"id":"ci","kind":"semantic_ci","claim_type":kind,
          "effect_measure":measure,"confidence_level":0.95,
          "ci_lower":lo,"ci_upper":hi,"estimate":estimate}
    if claim_text is not None:
        spec["claim_text"]=claim_text
    return spec


class ScientificNumericCIRegressions(unittest.TestCase):
    def test_cancellation_is_not_falsely_approved(self):
        row=check(eq("(x + 1) - x","0",{"x":10**16}))
        self.assertEqual(row["numeric_status"],"FAIL")
        self.assertEqual(row["status"],"FAIL")

    def test_underflow_is_not_falsely_approved(self):
        row=check(eq("x*x","0*x*x",{"x":1e-200},{"x":{"kg":1}}))
        self.assertEqual(row["numeric_status"],"FAIL")

    def test_exact_rational_arithmetic_of_decimal_values(self):
        row=check(eq("1/3 + 1/3 + 1/3","1",{"x":1}))
        self.assertEqual(row["status"],"PASS")
        self.assertEqual(row["numeric_method"],"exact_rational_from_displayed_inputs")

    def test_additive_literal_zero_is_dimensionally_neutral(self):
        row=check(eq("force","mass*acceleration+0",
              {"force":10,"mass":2,"acceleration":5},
              {"force":{"kg":1,"m":1,"s":-2},"mass":{"kg":1},
               "acceleration":{"m":1,"s":-2}}))
        self.assertEqual(row["status"],"PASS")

    def test_zero_difference_matches_literal_zero(self):
        row=check(eq("force-force","0",{"force":10},{"force":{"kg":1}}))
        self.assertEqual(row["status"],"PASS")

    def test_zero_literal_not_wrongly_makes_any_equation_true(self):
        row=check(eq("force","0",{"force":10},{"force":{"kg":1}}))
        self.assertEqual(row["numeric_status"],"FAIL")

    def test_rounding_at_null_is_indeterminate_not_false_fail(self):
        for claim in ("significant_increase","not_significant"):
            with self.subTest(claim=claim):
                row=check(ci(claim,1.0,1.4,1.2))
                self.assertEqual(row["status"],"NOT_VERIFIED")

    def test_unrounded_null_exclusion_preserves_significance(self):
        row=check(ci("significant_increase",1.01,1.4,1.2))
        self.assertEqual(row["status"],"PASS")
        row=check(ci("significant_increase",0.95,1.4,1.2))
        self.assertEqual(row["status"],"FAIL")

    def test_difference_null_boundary_is_indeterminate(self):
        row=check(ci("not_significant",0.0,0.5,0.2,"mean_difference"))
        self.assertEqual(row["status"],"NOT_VERIFIED")

    def test_published_rate_ratio_measure_is_supported(self):
        row=check(ci("not_significant",0.64,1.18,0.87,"rate_ratio"))
        self.assertEqual(row["status"],"PASS")

    def test_printed_high_precision_ci_not_rounded_to_the_null(self):
        high = Decimal("1.0000000000000001")
        row = check(ci("significant_increase", high, Decimal("1.2"), Decimal("1.1")))
        self.assertEqual(row["status"], "PASS")
        self.assertEqual(row["reported_interval_exact"][0], str(high))
        self.assertEqual(row["estimate_exact"], "1.1")
        at_null = check(ci("significant_increase", Decimal("1.0000000000000000"),
                           Decimal("1.2"), Decimal("1.1")))
        self.assertEqual(at_null["status"], "NOT_VERIFIED")
        below = check(ci("significant_increase", Decimal("0.9999999999999999"),
                         Decimal("1.2"), Decimal("1.1")))
        self.assertEqual(below["status"], "FAIL")

    def test_displayed_risk_difference_just_above_physical_bound_rejected(self):
        with self.assertRaises(ValueError):
            check(ci("significant_increase", Decimal("0.5"),
                     Decimal("1.1"), Decimal("1.0000000000000001"),
                     "risk_difference"))

    def test_decimal_confidence_level_is_not_silently_rounded_to_95_percent(self):
        case=ci("not_significant", Decimal("0.8"),Decimal("1.2"),Decimal("1.0"))
        case["confidence_level"]=Decimal("0.9500000000000001")
        with self.assertRaises(ValueError):
            check(case)
        case["confidence_level"]=Decimal("0.95")
        self.assertEqual(check(case)["status"], "PASS")

    def test_semantic_ci_rejects_unsupported_decimal_precision_and_types(self):
        cases = [
            "1.01",
            float("nan"),
            Decimal("NaN"),
            Decimal("1e301"),
            Decimal("1." + "3"*105),
        ]
        for lower in cases:
            with self.subTest(lower=str(lower)[:22]), self.assertRaises(ValueError):
                check(ci("significant_increase", lower, Decimal("1.2"), Decimal("1.1")))

    def test_exact_decimal_ci_survives_json_file_and_serialization(self):
        import json
        import tempfile
        from pathlib import Path
        from sra.scientific_validation import verify_scientific_file
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "check.json"
            source.write_text(
                '{"schema_version":"1.0","checks":[{"id":"ci","kind":"semantic_ci",'
                '"confidence_level":0.95,"claim_type":"significant_increase",'
                '"effect_measure":"risk_ratio","ci_lower":1.0000000000000001,'
                '"ci_upper":1.2,"estimate":1.1}]}', encoding="utf-8",
            )
            result = verify_scientific_file(source)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(
                result["checks"][0]["reported_interval_exact"][0], "1.0000000000000001"
            )
            self.assertEqual(
                json.loads(json.dumps(result))["checks"][0]["null_value"], 1.0
            )

    def test_semantic_ci_all_status_paths_json_serializable(self):
        import json
        cases = [
            ci("no_effect", 0.8, 1.2, 1),
            ci("significant_increase", 1.0, 1.5, 1.2),
            ci("exact_null_effect", 1.2, 1.5, 1.3),
            ci("exact_null_effect", 0.9, 1.1, 1),
        ]
        for case in cases:
            with self.subTest(kind=case["claim_type"]):
                result=check(case)
                self.assertIsInstance(json.loads(json.dumps(result))["null_value"], float)

    def test_risk_difference_point_estimate_must_be_physical(self):
        with self.assertRaises(ValueError):
            check(ci("significant_increase",4.0,6.0,5.0,"risk_difference"))

    def test_nonverified_claim_text_is_machine_readable(self):
        row=check(ci("not_significant",0.8,1.2,1.0,
             claim_text="The therapy has a proven statistically significant benefit."))
        self.assertEqual(row["status"],"PASS")
        self.assertIs(row["claim_text_checked"],False)
        self.assertIn("not evaluated",row["limitations"].lower())

    def test_exact_null_claim_contradicted_by_excluding_interval(self):
        row=check(ci("exact_null_effect",2,3,2.5))
        self.assertEqual(row["status"],"FAIL")

    def test_exact_null_claim_not_proved_by_non_significance(self):
        row=check(ci("exact_null_effect",0.8,1.2,1.0))
        self.assertEqual(row["status"],"NOT_VERIFIED")

    def test_rounded_integer_crude_ci_cannot_be_full_pass(self):
        row=check({"id":"r","kind":"unadjusted_risk_ratio",
                   "confidence_level":0.95,
                   "exposed":{"events":500,"total":1000},
                   "control":{"events":500,"total":1000},
                   "reported":{"risk_ratio":1,"ci_lower":1,"ci_upper":1}})
        self.assertEqual(row["status"],"NOT_VERIFIED")
        self.assertIn("precision",str(row).lower())

    def test_precise_crude_reference_remains_pass(self):
        row=check({"id":"r","kind":"unadjusted_risk_ratio",
                   "confidence_level":0.95,
                   "exposed":{"events":10,"total":75},
                   "control":{"events":12,"total":225},
                   "reported":{"risk_ratio":2.5,
                               "ci_lower":1.1261564003469628,
                               "ci_upper":5.549850800541033}})
        self.assertEqual(row["status"],"PASS")


if __name__=="__main__":
    unittest.main()
