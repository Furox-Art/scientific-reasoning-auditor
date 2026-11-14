"""CLI execution semantics and input/output protection."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.cli import main


class UnifiedCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paper = self.root / "paper.md"
        self.paper.write_text("# Proof\nSuppose all assumptions hold.\n", encoding="utf-8")

    def call(self, *args):
        output = io.StringIO()
        with patch("sys.argv", ["sra", *map(str, args)]), contextlib.redirect_stdout(output):
            code = main()
        return code, output.getvalue()

    def test_capabilities_outputs_machine_readable_contract(self):
        code, output = self.call("capabilities")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["schema_version"], "cross-disciplinary-review/1.0")

    def test_review_produces_both_outputs_and_zero_is_only_execution_success(self):
        code, output = self.call("review", self.paper, "--study-type", "theoretical",
                                 "--discipline", "physics", "--out", self.root / "out/report")
        self.assertEqual(code, 0)
        report = json.loads((self.root / "out/report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["configuration"]["study_type"], "theoretical")
        self.assertEqual(report['criteria_matrix']['declared_study_type'],'theoretical')
        criteria={row['id']:row for row in report['criteria_matrix']['criteria']}
        self.assertEqual(criteria['proof_completeness']['execution_status'],'human_review_required')
        self.assertIn("not scientific", output)
        self.assertTrue((self.root / "out/report.md").is_file())

    def test_inputs_are_protected_before_any_analysis(self):
        with patch("sra.cli.review_manuscript") as run:
            with self.assertRaises(SystemExit):
                self.call("review", self.paper, "--out", self.paper)
            run.assert_not_called()
        spec = self.root / "spec.json"
        spec.write_text("{}")
        with self.assertRaises(SystemExit):
            self.call("review", self.paper, "--statistics-spec", spec, "--out", spec)

    def test_bad_spec_and_missing_file_exit_two_without_writing(self):
        for path in (self.root / "missing.json", self.paper):
            with self.subTest(path=path), self.assertRaises(SystemExit) as caught:
                self.call("review", self.paper, "--scientific-spec", path, "--out", self.root / "bad")
            self.assertEqual(caught.exception.code, 2)
        self.assertFalse((self.root / "bad.json").exists())

    def test_requested_model_failure_writes_partial_report_exit_one(self):
        with patch("sra.review.review_parsed_paper", side_effect=RuntimeError("private")):
            code, _ = self.call("review", self.paper, "--send-to-model", "--model", "fake", "--out", self.root / "partial")
        self.assertEqual(code, 1)
        result = json.loads((self.root / "partial.json").read_text())
        self.assertEqual(result["execution_status"], "partial")

    def test_output_aliases_cannot_merge_json_and_markdown(self):
        original = self.root / "report.json"
        original.write_text("preserve me")
        os.link(original, self.root / "report.md")
        with self.assertRaises(SystemExit):
            self.call("review", self.paper, "--out", self.root / "report")
        self.assertEqual(original.read_text(), "preserve me")


if __name__ == "__main__":
    unittest.main()
