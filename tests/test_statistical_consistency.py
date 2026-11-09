"""Sentence-scoped statistical consistency checks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sra.audit import audit_file
from sra.statistical_consistency import (
    confidence_interval_p_conflict,
    group_count_test_mismatch,
    impossible_dispersion,
    impossible_p_value,
    mean_outside_interval,
)


class ConfidenceIntervalPConflictTests(unittest.TestCase):
    def test_interval_including_the_null_with_a_small_p_is_flagged(self):
        findings = confidence_interval_p_conflict(
            "The effect was 1.2 (95% CI -0.5 to 2.0, p = 0.002)."
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].check_id, "statistics.confidence_interval_p_conflict")
        self.assertEqual(findings[0].evidence_locations[0]["kind"], "interval_includes_null")

    def test_interval_excluding_the_null_with_a_large_p_is_flagged(self):
        findings = confidence_interval_p_conflict(
            "The difference was 0.2 (95% CI 0.01 to 0.4, p = 0.31)."
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].evidence_locations[0]["kind"], "interval_excludes_null")

    def test_a_ratio_uses_one_as_the_null(self):
        self.assertEqual(
            len(confidence_interval_p_conflict(
                "The odds ratio was 1.9 (95% CI 1.2 to 3.0, p = 0.31)."
            )),
            1,
        )
        self.assertEqual(
            len(confidence_interval_p_conflict(
                "The odds ratio was 1.9 (95% CI 1.2 to 3.0, p = 0.002)."
            )),
            0,
        )

    def test_consistent_numbers_are_silent(self):
        self.assertEqual(
            confidence_interval_p_conflict(
                "The effect was 1.2 (95% CI 0.4 to 2.0, p = 0.002)."
            ),
            [],
        )

    def test_a_descriptive_interval_is_not_compared_with_a_p_value(self):
        self.assertEqual(
            confidence_interval_p_conflict(
                "The mean age was 45 years (95% CI 30 to 60, p = 0.2)."
            ),
            [],
        )

    def test_a_sentence_without_an_interval_is_silent(self):
        self.assertEqual(confidence_interval_p_conflict("The effect was large, p = 0.2."), [])


class MeanOutsideIntervalTests(unittest.TestCase):
    def test_a_mean_outside_its_interval_is_flagged(self):
        findings = mean_outside_interval("Mean score was 4.1 (95% CI 2.0 to 3.0, p = 0.001).")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].check_id, "statistics.mean_outside_confidence_interval")

    def test_a_mean_inside_its_interval_is_silent(self):
        self.assertEqual(
            mean_outside_interval("The mean age was 45 years (95% CI 30 to 60)."),
            [],
        )

    def test_a_sentence_without_a_mean_is_silent(self):
        self.assertEqual(mean_outside_interval("The effect (95% CI 0.1 to 0.2) was small."), [])

    def test_fenced_code_is_ignored(self):
        text = "```\nMean score was 4.1 (95% CI 2.0 to 3.0)\n```\n"
        self.assertEqual(mean_outside_interval(text), [])


class ImpossiblePValueTests(unittest.TestCase):
    def test_rounded_to_zero_is_flagged(self):
        findings = impossible_p_value("The effect was significant, p = 0.000.")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].check_id, "statistics.impossible_p_value")

    def test_a_plain_p_is_silent(self):
        self.assertEqual(impossible_p_value("The effect was significant, p = 0.03."), [])

    def test_a_bound_is_silent(self):
        self.assertEqual(impossible_p_value("The effect was significant, p < 0.001."), [])

    def test_a_bound_above_one_is_flagged(self):
        self.assertEqual(len(impossible_p_value("The test gave p > 1.")), 1)

    def test_a_probability_above_one_is_flagged(self):
        self.assertEqual(len(impossible_p_value("The test gave p = 1.4.")), 1)

    def test_a_negative_probability_is_flagged(self):
        self.assertEqual(len(impossible_p_value("The test gave p = -0.2.")), 1)

    def test_exactly_one_is_a_legitimate_probability(self):
        self.assertEqual(impossible_p_value("The test gave p = 1.0."), [])

    def test_fenced_code_is_ignored(self):
        self.assertEqual(impossible_p_value("```\np = 0.000\n```\n"), [])

    def test_a_negative_bound_is_flagged(self):
        self.assertEqual(len(impossible_p_value("The test gave p < -0.1.")), 1)

    def test_unicode_spellings_are_normalised(self):
        self.assertEqual(len(impossible_p_value("The test gave p ≤ -0.1.")), 1)
        self.assertEqual(len(impossible_p_value("The test gave p = 0·000.")), 1)

    def test_a_bound_at_or_above_one_is_flagged(self):
        self.assertEqual(len(impossible_p_value("The test gave p ≥ 1.2.")), 1)


class ImpossibleDispersionTests(unittest.TestCase):
    def test_a_negative_standard_deviation_is_flagged(self):
        findings = impossible_dispersion("The treated arm reported SD = -1.2.")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].check_id, "statistics.impossible_dispersion")

    def test_a_negative_standard_error_is_flagged(self):
        self.assertEqual(len(impossible_dispersion("The estimate had SE = -0.4.")), 1)

    def test_a_positive_dispersion_is_silent(self):
        self.assertEqual(impossible_dispersion("The arm reported SD = 1.2."), [])

    def test_a_zero_sample_size_is_flagged(self):
        self.assertEqual(len(impossible_dispersion("The final cohort had n = 0.")), 1)

    def test_a_real_sample_size_is_silent(self):
        self.assertEqual(impossible_dispersion("The final cohort had n = 24."), [])


class GroupCountTestMismatchTests(unittest.TestCase):
    def test_three_groups_with_pairwise_tests_are_flagged(self):
        findings = group_count_test_mismatch("We compared three groups with t-tests.")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].check_id, "statistics.group_count_test_mismatch")

    def test_an_omnibus_test_clears_the_signal(self):
        text = "We compared three groups using ANOVA followed by t-tests."
        self.assertEqual(group_count_test_mismatch(text), [])

    def test_an_adjusted_contrast_clears_the_signal(self):
        text = "Four arms were compared; Tukey contrasts were used."
        self.assertEqual(group_count_test_mismatch(text), [])

    def test_two_groups_are_not_a_multiplicity_problem(self):
        self.assertEqual(group_count_test_mismatch("We compared two groups with t-tests."), [])

    def test_more_groups_without_a_named_test_are_silent(self):
        self.assertEqual(group_count_test_mismatch("Six cohorts were enrolled."), [])


class AuditIntegrationTests(unittest.TestCase):
    def test_the_conflict_reaches_the_audit_report(self):
        manuscript = (
            "# Methods\nWe fitted one model.\n"
            "# Results\nEffect size 1.2 (95% CI 0.4 to 2.0, p = 0.31).\n"
            "# Conclusion\nThe effect is positive.\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "paper.md"
            path.write_text(manuscript, encoding="utf-8", newline="")
            report = audit_file(path)
        check_ids = {finding.check_id for finding in report.findings}
        self.assertIn("statistics.confidence_interval_p_conflict", check_ids)


if __name__ == "__main__":
    unittest.main()
