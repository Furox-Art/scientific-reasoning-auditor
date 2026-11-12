"""Synthetic cross-field behavior controls, not an expert accuracy benchmark."""
import hashlib
import json
import unittest
from pathlib import Path

import jsonschema

from sra.review import review_manuscript
from sra.review_report import review_markdown


class CrossFieldExampleTests(unittest.TestCase):
    def test_six_scientific_workflows_have_valid_source_bound_reports(self):
        root = Path(__file__).parents[1]
        examples = root / "examples/unified_review"
        schema = json.loads((root / "schemas/cross-disciplinary-review.schema.json").read_text())
        for case in json.loads((examples / "cases.json").read_text())["cases"]:
            with self.subTest(case=case["file"]):
                source = examples / case["file"]
                report = review_manuscript(source, study_type=case["study_type"], disciplines=case["disciplines"])
                jsonschema.validate(report, schema)
                self.assertEqual(report["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
                self.assertEqual(report["execution_status"], "complete")
                self.assertIn("Coverage gaps", review_markdown(report))
                if case["study_type"] == "theoretical":
                    self.assertEqual(len(report["excluded_findings"]), 2)
                if case["study_type"] == "unknown":
                    self.assertTrue(report["applicability"]["review_required"])

    def test_schema_rejects_false_completion_and_malformed_source_identity(self):
        root = Path(__file__).parents[1]
        schema = json.loads((root / "schemas/cross-disciplinary-review.schema.json").read_text())
        report = review_manuscript(root / "examples/unified_review/theoretical_math.md")
        report["modules"]["model"]["status"] = "completed"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(report, schema)
        report["source_sha256"] = "not-a-hash"
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(report, schema)


if __name__ == "__main__":
    unittest.main()
