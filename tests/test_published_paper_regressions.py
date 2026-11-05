"""Regression controls derived from pilot failures; no copyrighted manuscript copies."""
import tempfile
import unittest
from pathlib import Path

from sra.audit import audit_file
from sra.checks import _direction


class PublishedPaperRegressionTests(unittest.TestCase):
    def _findings(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manuscript.md"
            path.write_text(text, encoding="utf-8")
            report = audit_file(str(path))
        return {item.check_id: item for item in report.findings}

    @staticmethod
    def _document(first, second):
        return (
            "# Methods\nA randomised controlled clinical study was conducted.\n"
            "# Results\n" + first + "\n"
            "# Discussion\n" + second + "\n"
            "# References\nA cited reference.\n"
        )

    def test_repeated_rate_ratio_conflicting_ci_requires_review(self):
        original = (
            "For the primary endpoint the rate ratio 0.87; "
            "95% CI 0.64–1.18; p = 0.37."
        )
        changed = (
            "For the primary endpoint the rate ratio 0.87; "
            "95% CI 0.64–1.33; p = 0.37."
        )
        findings = self._findings(self._document(original, changed))
        self.assertIn("statistics.repeated_rate_ratio_ci_conflict", findings)
        finding = findings["statistics.repeated_rate_ratio_ci_conflict"]
        self.assertEqual(finding.status, "review_required")
        self.assertEqual(len(finding.evidence), 2)
        self.assertIn("0.64–1.18", finding.evidence[0])
        self.assertIn("0.64–1.33", finding.evidence[1])
        self.assertEqual([loc["line"] for loc in finding.evidence_locations], [4, 6])

    def test_repeated_rate_ratio_consistent_ci_is_not_flagged(self):
        statement = (
            "The primary outcome rate ratio 0.87; "
            "95% CI 0.64–1.18; p = 0.37."
        )
        self.assertNotIn(
            "statistics.repeated_rate_ratio_ci_conflict",
            self._findings(self._document(statement, statement)),
        )

    def test_distinct_effect_estimates_or_p_values_are_not_conflated(self):
        a = "The primary outcome rate ratio 0.87; 95% CI 0.64–1.18; p = 0.37."
        b = "The secondary outcome rate ratio 0.88; 95% CI 0.64–1.33; p = 0.37."
        c = "The subgroup outcome rate ratio 0.87; 95% CI 0.64–1.33; p = 0.23."
        for other in (b, c):
            with self.subTest(other=other):
                self.assertNotIn(
                    "statistics.repeated_rate_ratio_ci_conflict",
                    self._findings(self._document(a, other)),
                )

    def test_numeric_conflict_inside_fenced_code_is_not_scientific_evidence(self):
        a = "The primary outcome rate ratio 0.87; 95% CI 0.64–1.18; p = 0.37."
        body = self._document(a, a)
        body += (
            "\n```text\n"
            "The primary outcome rate ratio 0.87; 95% CI 0.64–1.33; p = 0.37.\n"
            "```\n"
        )
        self.assertNotIn(
            "statistics.repeated_rate_ratio_ci_conflict",
            self._findings(body),
        )

    def test_dosage_group_names_are_not_outcome_directions(self):
        self.assertEqual(_direction("higher dose corticosteroids were allocated"), 0)
        self.assertEqual(_direction("the lower-dose group received usual care"), 0)
        self.assertEqual(_direction("higher dose increased the primary outcome"), 1)
        self.assertEqual(_direction("the lower-dose group reduced mortality"), -1)
        self.assertEqual(_direction("higher mortality was observed"), 1)
        self.assertEqual(_direction("lower mortality was observed"), -1)


if __name__ == "__main__":
    unittest.main()
