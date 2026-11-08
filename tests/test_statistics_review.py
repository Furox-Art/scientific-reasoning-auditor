"""Screening rules for multiplicity and design/test adequacy."""

from __future__ import annotations

import unittest

from sra.statistics_review import design_test_mismatch_finding, multiplicity_finding


UNCORRECTED = (
    "# Methods\nWe compared four groups with t-tests.\n"
    "# Results\nGroup A differed (p = 0.01). Group B differed (p = 0.03). "
    "Group C differed (p = 0.049).\n"
)


class MultiplicityTests(unittest.TestCase):
    def test_several_p_values_without_a_correction_are_flagged(self):
        finding = multiplicity_finding(UNCORRECTED)
        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertEqual(finding.check_id, "statistics.multiplicity_unaddressed")
        self.assertEqual(finding.severity, "warning")
        self.assertEqual(finding.status, "review_required")
        self.assertIn("3 reported p-values", finding.title)
        self.assertEqual(len(finding.evidence), 3)
        self.assertEqual(finding.evidence_locations[0]["kind"], "reported_p_value")

    def test_a_single_test_is_not_a_multiplicity_problem(self):
        text = "# Results\nOne comparison was made (p = 0.04).\n"
        self.assertIsNone(multiplicity_finding(text))

    def test_an_adjustment_statement_clears_the_signal(self):
        for statement in (
            "Bonferroni correction was applied.",
            "Tukey HSD was used for the pairwise contrasts.",
            "Controlled by the Benjamini-Hochberg false discovery rate.",
            "Çoklu karşılaştırma düzeltmesi uygulandı.",
        ):
            with self.subTest(statement=statement):
                self.assertIsNone(multiplicity_finding(UNCORRECTED + statement + "\n"))

    def test_p_values_inside_code_fences_are_ignored(self):
        text = (
            "# Results\nThe outcome improved.\n"
            "```\np = 0.01\np = 0.02\np = 0.03\n```\n"
        )
        self.assertIsNone(multiplicity_finding(text))


PAIRED_UNCORRECTED = (
    "# Methods\nEach participant was measured before and after the intervention: a "
    "paired design.\n"
    "# Results\nScores rose, independent-samples t-test p = 0.02.\n"
)


class DesignTestMismatchTests(unittest.TestCase):
    def test_paired_design_with_an_independent_test_is_flagged(self):
        finding = design_test_mismatch_finding(PAIRED_UNCORRECTED)
        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertEqual(finding.check_id, "statistics.design_test_mismatch")
        kinds = {location["kind"] for location in finding.evidence_locations}
        self.assertEqual(kinds, {"paired_design_wording", "independent_test_name"})

    def test_a_paired_test_for_a_paired_design_is_silent(self):
        text = PAIRED_UNCORRECTED.replace("independent-samples t-test", "paired t-test")
        self.assertIsNone(design_test_mismatch_finding(text))

    def test_an_independent_test_without_a_paired_design_is_silent(self):
        text = "# Methods\nTwo independent groups.\n# Results\nindependent-samples t-test p = 0.03.\n"
        self.assertIsNone(design_test_mismatch_finding(text))

    def test_a_paired_design_without_a_named_test_is_silent(self):
        text = "# Methods\nA within-subjects design was used.\n# Results\nScores rose.\n"
        self.assertIsNone(design_test_mismatch_finding(text))


class AuditIntegrationTests(unittest.TestCase):
    def test_the_signal_reaches_the_audit_report(self):
        import tempfile
        from pathlib import Path

        from sra.audit import audit_file

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper.md"
            path.write_text(UNCORRECTED, encoding="utf-8", newline="")
            report = audit_file(path)

        check_ids = {finding.check_id for finding in report.findings}
        self.assertIn("statistics.multiplicity_unaddressed", check_ids)

    def test_a_manuscript_naming_both_tests_is_silent(self):
        text = PAIRED_UNCORRECTED + "We also ran a paired t-test as a check.\n"
        self.assertIsNone(design_test_mismatch_finding(text))


if __name__ == "__main__":
    unittest.main()
