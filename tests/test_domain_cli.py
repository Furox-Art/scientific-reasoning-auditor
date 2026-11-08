"""CLI checks for domain evidence and source-bound review import."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sra.domain_evidence import PROFILES


class DomainEndToEndTests(unittest.TestCase):
    SOURCE = (
        "# Methods\n"
        "The instrument was calibrated against a NIST reference standard.\n"
        "The measured value was repeated n = 12 times.\n"
        "# Results\n"
        "The field was 1.5 ± 0.2 mT.\n"
    )

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "sra.cli", *map(str, args)],
            capture_output=True, text=True, check=False,
        )

    def test_cli_structural_expert_review_requires_full_manual_results(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            original = base / "paper.md"
            original.write_text(self.SOURCE, encoding="utf-8")
            original_bytes = original.read_bytes()
            template_path = base / "domain-template.json"
            result_path = base / "domain-reviewed.json"
            source_quote = "The instrument was calibrated against a NIST reference standard."
            create = self.cli(
                "domain-template", original, "--discipline", "physics",
                "--out", template_path,
            )
            self.assertEqual(create.returncode, 0, create.stderr)
            template = json.loads(template_path.read_text(encoding="utf-8"))
            self.assertEqual(template["source_sha256"], hashlib.sha256(original_bytes).hexdigest())
            self.assertEqual(template["kind"], "manual_domain_expert_assessment_template")
            self.assertTrue(all(not a["reviewer_assessments"] for a in template["assessments"]))
            # Test doubles only: no claim of actual expert evaluation.
            for item in template["assessments"]:
                item["reviewer_assessments"] = [
                    {
                        "reviewer_id": reviewer,
                        "verdict": "partially_reported",
                        "rationale": "Only a source passage candidate has been located, pending review.",
                        "source_quote": source_quote,
                    }
                    for reviewer in ("test-double-A", "test-double-B")
                ]
                item["adjudicated_verdict"] = "partially_reported"
                item["adjudication_rationale"] = (
                    "This test checks that all mandatory structural fields are validated."
                )
            completed = base / "filled-test-double.json"
            completed.write_text(json.dumps(template), encoding="utf-8")
            apply = self.cli(
                "domain-validate", original, completed,
                "--discipline", "physics", "--out", result_path,
            )
            self.assertEqual(apply.returncode, 0, apply.stderr)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "STRUCTURALLY_ACCEPTED_FOR_EXPERT_OVERSIGHT")
            self.assertEqual(result["declared_reviewer_count"], 2)
            self.assertEqual(result["rule_count"], len(PROFILES["physics"]["rules"]))
            self.assertEqual(original.read_bytes(), original_bytes)

    def test_domain_review_writes_source_grounded_candidates(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            manuscript = base / "paper.md"
            manuscript.write_text(self.SOURCE, encoding="utf-8")
            out = base / "results" / "domain.json"
            completed = self.cli(
                "domain-review", manuscript, "--discipline", "physics", "--out", out,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(out.read_text())
            self.assertEqual(report["discipline"], "physics")
            self.assertEqual(report["summary"]["expert_verified_items"], 0)
            self.assertGreaterEqual(report["summary"]["textual_candidates"], 2)
            self.assertTrue(all(a["expert_assessment"] == "REQUIRED" for a in report["items"]))

    def test_domain_cli_does_not_overwrite_manuscripts_or_templates(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            manuscript = base / "paper.md"
            manuscript.write_text(self.SOURCE, encoding="utf-8")
            before = manuscript.read_bytes()
            result = self.cli(
                "domain-review", manuscript, "--discipline", "physics",
                "--out", manuscript,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must not overwrite", result.stderr)
            self.assertEqual(manuscript.read_bytes(), before)

    def test_incomplete_adjudication_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            manuscript = base / "paper.md"
            manuscript.write_text(self.SOURCE, encoding="utf-8")
            template_path = base / "template.json"
            out = base / "result.json"
            self.assertEqual(self.cli(
                "domain-template", manuscript, "--discipline", "physics",
                "--out", template_path,
            ).returncode, 0)
            result = self.cli(
                "domain-validate", manuscript, template_path, "--discipline", "physics",
                "--out", out,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("reviewer assessments", result.stderr)
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
