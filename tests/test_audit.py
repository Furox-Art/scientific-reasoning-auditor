import tempfile
import unittest
from pathlib import Path

from sra.audit import audit_file


class AuditTests(unittest.TestCase):
    def test_flags_absolute_claim_and_missing_sections(self):
        text = (
            "# Results\nThe treatment is associated with response.\n"
            "# Conclusion\nThis study proves conclusively that treatment causes response."
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.md"
            path.write_text(text, encoding="utf-8")
            report = audit_file(path)
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("language.absolute_claim", ids)
        self.assertIn("reasoning.correlation_causation_review", ids)
        self.assertIn("structure.methods_missing", ids)
        self.assertIn("structure.limitations_missing", ids)
        self.assertTrue(report.sha256)

    def test_claim_evidence_candidate_is_explicitly_heuristic(self):
        text = (
            "# Methods\nWe used a randomized design.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nOur findings demonstrate that the intervention increased the score."
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.md"
            path.write_text(text, encoding="utf-8")
            report = audit_file(path)
        self.assertEqual(len(report.claim_evidence_candidates), 1)
        self.assertIn("not verified", report.claim_evidence_candidates[0].interpretation)


if __name__ == "__main__":
    unittest.main()
