"""Cases for attribution of observational designs in research-on-research papers."""
import tempfile
import unittest
from pathlib import Path
from sra.audit import audit_file

class MetaResearchControls(unittest.TestCase):
    def run_audit(self, methods, conclusion):
        manuscript = (
            "# Methods\n" + methods + "\n"
            "# Results\nThe review found differences in wording across the articles.\n"
            "# Discussion\n" + conclusion + "\n"
            "# References\nResearch article one.\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "article.md"
            p.write_text(manuscript, encoding="utf-8")
            return audit_file(p)

    def test_review_of_observational_papers_is_not_an_exposure_cohort(self):
        report = self.run_audit(
            "Reviewers screened the abstracts of observational studies. "
            "This is a methodological study (research on research) about causal wording.",
            "Based on screening these papers, this review describes phrases "
            "used to imply a causal effect.",
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertNotIn("reasoning.causal_claim_observational_design", ids)

    def test_methodological_review_of_articles_does_not_imply_cohort(self):
        report = self.run_audit(
            "This methodological review of observational studies examined "
            "how their abstracts describe causal relationships.",
            "These papers suggest that authors sometimes use causal language.",
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertNotIn("reasoning.causal_claim_observational_design", ids)

    def test_own_observational_study_still_requires_causal_review(self):
        report = self.run_audit(
            "This was an observational cohort study of patients exposed to a treatment. "
            "We also conducted a methodological review of published research articles.",
            "The exposure caused the adverse outcome.",
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.causal_claim_observational_design", ids)

    def test_prototypical_observational_study_still_requires_review(self):
        report = self.run_audit(
            "This was a cross-sectional observational study.",
            "The exposure caused the measured outcome.",
        )
        self.assertIn(
            "reasoning.causal_claim_observational_design",
            {f.check_id for f in report.findings},
        )

if __name__ == "__main__":
    unittest.main()
