"""Regression-first scientific checks for explicitly structured assertions.

These tests do not claim manuscript-wide semantic or mathematical proof.
"""
import contextlib
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.scientific_validation import verify_scientific_file, verify_scientific_spec
from sra.cli import main


def spec(*checks):
    return {"schema_version": "1.0", "checks": list(checks)}


def semantic(assertion, lower=0.8, upper=1.2, estimate=1.0):
    return {"id": "s", "kind": "semantic_ci", "claim_type": assertion,
            "effect_measure": "risk_ratio", "confidence_level": 0.95,
            "estimate": estimate, "ci_lower": lower, "ci_upper": upper,
            "claim_text": "Structured claim supplied by the researcher."}


def eq(right="mass * acceleration", force=10, values=True):
    case = {"id": "e", "kind": "dimension_equation",
            "left": "force", "right": right,
            "dimensions": {
                "force": {"kg": 1, "m": 1, "s": -2},
                "mass": {"kg": 1}, "acceleration": {"m": 1, "s": -2}},
            "absolute_tolerance": 1e-9}
    if values:
        case["values"] = {"force": force, "mass": 2, "acceleration": 5}
    return case


def rr(exposed_events=10, exposed_total=75, control_events=12, control_total=225, reported=None):
    return {"id": "r", "kind": "unadjusted_risk_ratio",
            "exposed": {"events": exposed_events, "total": exposed_total},
            "control": {"events": control_events, "total": control_total},
            "confidence_level": 0.95, "reported": reported or {}}


class ScientificVerificationTests(unittest.TestCase):
    def verify(self, *checks):
        return verify_scientific_spec(spec(*checks))

    def test_structured_semantic_significant_increase_supported(self):
        row = self.verify(semantic("significant_increase", 1.1, 1.6, 1.3))["checks"][0]
        self.assertEqual(row["status"], "PASS")
        self.assertIn("conditional", row["limitations"].lower())

    def test_structured_semantic_significant_decrease_supported(self):
        row = self.verify(semantic("significant_decrease", 0.5, 0.9, 0.7))["checks"][0]
        self.assertEqual(row["status"], "PASS")

    def test_structured_semantic_significant_assertion_crossing_null_fails(self):
        row = self.verify(semantic("significant_increase"))["checks"][0]
        self.assertEqual(row["status"], "FAIL")

    def test_structured_semantic_no_significant_difference_supported(self):
        row = self.verify(semantic("not_significant"))["checks"][0]
        self.assertEqual(row["status"], "PASS")

    def test_structured_semantic_no_significant_difference_fails_if_excluded(self):
        row = self.verify(semantic("not_significant", 1.1, 1.6, 1.3))["checks"][0]
        self.assertEqual(row["status"], "FAIL")

    def test_no_effect_never_inferred_from_nonsignificance(self):
        row = self.verify(semantic("no_effect"))["checks"][0]
        self.assertEqual(row["status"], "NOT_VERIFIED")
        self.assertEqual(self.verify(semantic("no_effect"))["status"], "PARTIAL")

    def test_equivalence_requires_separate_inferential_design(self):
        row = self.verify(semantic("equivalent"))["checks"][0]
        self.assertEqual(row["status"], "NOT_VERIFIED")

    def test_additive_effects_use_zero_as_null(self):
        case = semantic("significant_increase", 0.5, 2.0, 1.2)
        case["effect_measure"] = "mean_difference"
        self.assertEqual(self.verify(case)["checks"][0]["status"], "PASS")

    def test_ratio_effects_reject_negative_bounds(self):
        with self.assertRaises(ValueError):
            self.verify(semantic("significant_decrease", -1.0, 0.9, 0.7))

    def test_estimate_must_be_inside_interval(self):
        with self.assertRaises(ValueError):
            self.verify(semantic("not_significant", 0.8, 1.2, 1.4))

    def test_math_dimension_and_numeric_equality(self):
        row = self.verify(eq())["checks"][0]
        self.assertEqual(row["status"], "PASS")
        self.assertEqual(row["dimension_status"], "PASS")
        self.assertEqual(row["numeric_status"], "PASS")

    def test_math_dimension_mismatch_detected(self):
        row = self.verify(eq("mass + acceleration"))["checks"][0]
        self.assertEqual(row["status"], "FAIL")
        self.assertEqual(row["dimension_status"], "FAIL")

    def test_math_lhs_rhs_units_mismatch(self):
        row = self.verify(eq("mass"))["checks"][0]
        self.assertEqual(row["dimension_status"], "FAIL")

    def test_math_numeric_mismatch_detected(self):
        row = self.verify(eq(force=11))["checks"][0]
        self.assertEqual(row["dimension_status"], "PASS")
        self.assertEqual(row["numeric_status"], "FAIL")

    def test_math_missing_values_is_partial_not_mathematical_proof(self):
        row = self.verify(eq(values=False))["checks"][0]
        self.assertEqual(row["status"], "NOT_VERIFIED")
        self.assertEqual(row["dimension_status"], "PASS")

    def test_math_dimensionless_factor_and_powers(self):
        sample = eq("0.5 * mass * (2 * acceleration)", values=False)
        self.assertEqual(self.verify(sample)["checks"][0]["dimension_status"], "PASS")

    def test_math_forbids_executable_syntax(self):
        for expression in ("__import__('os').system('false')",
                           "mass.__class__", "[1, 2]", "mass ** 10000"):
            with self.subTest(expression=expression):
                with self.assertRaises(ValueError):
                    self.verify(eq(expression))

    def test_math_division_by_zero_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(eq("mass / 0"))

    def test_math_rejects_unknown_name_and_unrecognized_unit(self):
        with self.assertRaises(ValueError):
            self.verify(eq("electron_charge"))
        sample = eq()
        sample["dimensions"]["force"] = {"__illegal__": 1}
        with self.assertRaises(ValueError):
            self.verify(sample)

    def test_risk_ratio_independent_reference_scipy(self):
        from scipy.stats.contingency import relative_risk
        reference = relative_risk(10, 75, 12, 225)
        interval = reference.confidence_interval(0.95)
        row = self.verify(rr(reported={
            "risk_ratio": reference.relative_risk,
            "ci_lower": interval.low,
            "ci_upper": interval.high,
        }))["checks"][0]
        self.assertEqual(row["status"], "PASS")
        self.assertAlmostEqual(row["calculated"]["risk_ratio"], reference.relative_risk, places=12)
        self.assertAlmostEqual(row["calculated"]["ci_lower"], interval.low, places=10)
        self.assertAlmostEqual(row["calculated"]["ci_upper"], interval.high, places=10)

    def test_risk_ratio_wrong_reported_value_fails(self):
        row = self.verify(rr(reported={"risk_ratio": 42}))["checks"][0]
        self.assertEqual(row["status"], "FAIL")

    def test_risk_ratio_without_reported_values_is_partial(self):
        row = self.verify(rr())["checks"][0]
        self.assertEqual(row["status"], "NOT_VERIFIED")

    def test_risk_ratio_sparse_table_marks_not_verified(self):
        row = self.verify(rr(exposed_events=1))["checks"][0]
        self.assertEqual(row["status"], "NOT_VERIFIED")
        self.assertIn("sparse", row["reason"].lower())

    def test_risk_ratio_invalid_counts(self):
        for e, n in ((-1, 20), (21, 20), (True, 20), (1, 0)):
            with self.subTest(e=e, n=n):
                with self.assertRaises(ValueError):
                    self.verify(rr(exposed_events=e, exposed_total=n))

    def test_risk_ratio_is_not_adjusted_hazard_or_rate_ratio(self):
        row = self.verify(rr(reported={"risk_ratio": 2.5}))["checks"][0]
        self.assertIn("unadjusted", row["method"].lower())
        self.assertIn("not", row["limitations"].lower())

    def test_mixed_summary_aggregates_fail_partial_pass(self):
        output = self.verify(eq(), semantic("no_effect"), rr(reported={"risk_ratio": 42}))
        self.assertEqual(output["status"], "FAIL")
        self.assertEqual([x["status"] for x in output["checks"]], ["PASS","NOT_VERIFIED","FAIL"])

    def test_duplicate_check_id_and_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            self.verify(eq(), eq())
        case = eq()
        case["kind"] = "untrusted"
        with self.assertRaises(ValueError):
            self.verify(case)

    def test_input_file_source_hash_and_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "input.json"
            p.write_text(json.dumps(spec(eq())), encoding="utf-8")
            got = verify_scientific_file(p)
            self.assertEqual(len(got["input_sha256"]), 64)
            p.write_text('{"schema_version":"1.0","checks":[],"checks":[]}')
            with self.assertRaises(ValueError):
                verify_scientific_file(p)

    def test_cli_separate_output_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"input.json"
            dest=Path(tmp)/"result.json"
            p.write_text(json.dumps(spec(eq())), encoding="utf-8")
            with patch.object(sys,"argv",["sra","verify-science",str(p),"--out",str(dest)]):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(main(),0)
            self.assertTrue(dest.exists())
            self.assertEqual(json.loads(dest.read_text())["status"],"PASS")
            with patch.object(sys,"argv",["sra","verify-science",str(p),"--out",str(p)]):
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as x:
                        main()
            self.assertEqual(x.exception.code,2)

if __name__=="__main__":
    unittest.main()
