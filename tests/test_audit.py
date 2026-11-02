import json
import tempfile
import unittest
from pathlib import Path

from sra.audit import audit_file
from sra.stats import verify_stats_file, verify_welch_t_test


class AuditTests(unittest.TestCase):
    def audit_text(self, text: str):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "paper.md"
        path.write_text(text, encoding="utf-8")
        return audit_file(path)

    def test_flags_absolute_claim_and_missing_sections(self):
        report = self.audit_text(
            "# Results\nThe treatment is associated with response.\n"
            "# Conclusion\nThis study proves conclusively that treatment causes response."
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("language.absolute_claim", ids)
        self.assertIn("reasoning.correlation_causation_review", ids)
        self.assertIn("structure.methods_missing", ids)
        self.assertIn("structure.limitations_missing", ids)
        self.assertTrue(report.sha256)

    def test_claim_evidence_candidate_is_explicitly_heuristic(self):
        report = self.audit_text(
            "# Methods\nWe used a randomized design.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nOur findings demonstrate that the intervention increased the score."
        )
        self.assertEqual(len(report.claim_evidence_candidates), 1)
        candidate = report.claim_evidence_candidates[0]
        self.assertIn("not verified", candidate.interpretation)
        self.assertEqual(candidate.match_status, "heuristic_candidate")
        self.assertEqual(candidate.claim_line, 6)
        self.assertEqual(candidate.support_line, 4)
        self.assertEqual(candidate.claim_section, "Conclusion")
        self.assertEqual(candidate.support_section, "Results")

    def test_flags_possible_direction_conflict_between_results_and_conclusion(self):
        report = self.audit_text(
            "# Methods\nA randomized experiment was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention decreased the measured score."
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.directional_contradiction", ids)
        relation = next(
            item for item in report.reasoning_map
            if item["relation"] == "possible_directional_contradiction"
        )
        self.assertEqual(relation["status"], "heuristic_review_required")

    def test_weak_lexical_overlap_is_not_presented_as_support(self):
        report = self.audit_text(
            "# Methods\nA protocol was followed.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Discussion\nThe outcome was correlated with a biomarker."
        )
        candidate = report.claim_evidence_candidates[0]
        self.assertLess(candidate.lexical_overlap, 0.15)
        self.assertEqual(candidate.match_status, "unmatched_review_required")

    def test_flags_causal_claim_in_observational_design(self):
        report = self.audit_text(
            "# Methods\nThis was a cross-sectional observational study.\n"
            "# Results\nExposure was associated with the measured outcome.\n"
            "# Conclusion\nThe exposure caused the measured outcome."
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.causal_claim_observational_design", ids)

    def test_unmatched_conclusion_claim_gets_review_signal(self):
        report = self.audit_text(
            "# Methods\nA standard protocol was followed.\n"
            "# Results\nThe temperature remained stable throughout the experiment.\n"
            "# Conclusion\nOur findings demonstrate that the treatment improves long-term memory."
        )
        candidate = report.claim_evidence_candidates[0]
        self.assertEqual(candidate.match_status, "unmatched_review_required")
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.conclusion_without_lexical_candidate", ids)

    def test_manifest_records_source_and_environment_fingerprints(self):
        report = self.audit_text(
            "# Methods\nA test was performed.\n# Results\nThe result was stable."
        )
        manifest = report.reproducibility_manifest
        self.assertEqual(manifest["input"]["sha256"], report.sha256)
        self.assertEqual(manifest["input"]["format"], "md")
        self.assertEqual(len(manifest["configuration_sha256"]), 64)
        self.assertEqual(len(manifest["environment_fingerprint"]), 64)
        self.assertEqual(manifest["ruleset_version"], "0.2.2")
        self.assertIn("source_code_revision", manifest)
        self.assertIn("working_tree_dirty", manifest)
        self.assertIn("scipy", manifest["runtime"]["dependencies"])
        json.dumps(report.to_dict(), ensure_ascii=False)

    def test_synthetic_logic_demo_emits_the_expected_review_signals(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "logic_review_demo.md"
        report = audit_file(example)
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.causal_claim_observational_design", ids)
        self.assertIn("reasoning.directional_contradiction", ids)
        self.assertIn("reasoning.correlation_causation_review", ids)

    def test_turkish_discussion_is_not_confused_with_results(self):
        report = self.audit_text(
            "# Yöntem\nKontrollü deney.\n"
            "# Bulgular\nUygulama ölçülen skoru artırdı.\n"
            "# Tartışma\nBulgular uygulamanın etkisini desteklemektedir."
        )
        self.assertGreaterEqual(len(report.claim_evidence_candidates), 1)
        self.assertEqual(report.section_names[:3], ["Yöntem", "Bulgular", "Tartışma"])
        self.assertEqual(report.claim_evidence_candidates[0].claim_section, "Tartışma")


class StatisticalVerificationTests(unittest.TestCase):
    def test_welch_recalculation_matches_rounded_reported_values(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {
                "mean_difference": 1.0,
                "t": 3.536,
                "df": 48.0,
                "p_two_sided": 0.001,
            },
            "tolerances": {
                "mean_difference": 0.001,
                "t": 0.01,
                "df": 0.1,
                "p_two_sided": 0.001,
            },
        }
        result = verify_welch_t_test(spec, input_sha256="a" * 64)
        self.assertEqual(result["status"], "PASS")
        self.assertAlmostEqual(result["calculated"]["mean_difference"], 1.0)
        self.assertAlmostEqual(result["calculated"]["df"], 48.0)
        self.assertEqual(len(result["input_sha256"]), 64)

    def test_welch_result_matches_scipy_reference_implementation(self):
        from scipy import stats

        spec = {
            "test": "welch_t",
            "group_a": {"mean": 8.2, "sd": 2.4, "n": 31},
            "group_b": {"mean": 6.7, "sd": 1.8, "n": 27},
        }
        result = verify_welch_t_test(spec)
        reference = stats.ttest_ind_from_stats(
            mean1=8.2, std1=2.4, nobs1=31,
            mean2=6.7, std2=1.8, nobs2=27,
            equal_var=False,
        )
        self.assertAlmostEqual(result["calculated"]["t"], float(reference.statistic), places=12)
        self.assertAlmostEqual(result["calculated"]["p_two_sided"], float(reference.pvalue), places=12)

    def test_welch_recalculation_detects_mismatched_t_statistic(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {"t": 1.2},
            "tolerances": {"t": 0.01},
        }
        result = verify_welch_t_test(spec)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reported_checks"][0]["status"], "FAIL")

    def test_default_tolerance_uses_reported_decimal_precision(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {"p_two_sided": 0.02},
        }
        result = verify_welch_t_test(spec)
        check = result["reported_checks"][0]
        self.assertEqual(check["status"], "FAIL")
        self.assertAlmostEqual(check["absolute_tolerance"], 0.005)

    def test_welch_rejects_zero_reported_p_value(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {"p_two_sided": 0.0},
        }
        with self.assertRaises(ValueError):
            verify_welch_t_test(spec)

    def test_checked_in_welch_example_file_parses_and_passes(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "welch_t_example.json"
        result = verify_stats_file(example)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["input_sha256"]), 64)

    def test_welch_rejects_invalid_sample_sizes(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 1},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
        }
        with self.assertRaises(ValueError):
            verify_welch_t_test(spec)


if __name__ == "__main__":
    unittest.main()
