"""CLI behavior exercised in-process under coverage instrumentation."""
import contextlib
import io
import json
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra import cli, stats


TEXT = (
    "# Methods\nThis observational cohort included patients.\n"
    "# Results\nThe intervention increased recovery by five units.\n"
    "# Conclusion\nThe intervention increased recovery by five units."
)


class CliCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.manuscript = self.root / "paper.md"
        self.manuscript.write_text(TEXT, encoding="utf-8")
        self.captured = io.StringIO()

    def call_main(self, *args, expected_code=0):
        with patch.object(sys, "argv", ["sra", *map(str, args)]):
            with contextlib.redirect_stdout(self.captured):
                result = cli.main()
        self.assertEqual(result, expected_code, self.captured.getvalue())
        return self.captured.getvalue()

    def test_audit_generates_json_markdown_and_rejects_bad_import(self):
        prefix = self.root / "audit" / "paper"
        output = self.call_main("audit", self.manuscript, "--out", prefix)
        self.assertIn("Audit complete:", output)
        self.assertTrue(prefix.with_suffix(".json").is_file())
        self.assertTrue(prefix.with_suffix(".md").is_file())
        bad_review = self.root / "bad-review.json"
        bad_review.write_text("{}", encoding="utf-8")
        self.captured = io.StringIO()
        output = self.call_main(
            "audit", self.manuscript, "--semantic-review", bad_review,
            "--out", self.root / "bad-review-audit",
            expected_code=2,
        )
        self.assertIn("Semantic review validation errors:", output)

    def test_audit_catches_source_read_errors(self):
        with patch.object(sys, "argv", ["sra", "audit", str(self.root / "missing.md"),
                                         "--out", str(self.root / "failure")]):
            with contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as exit_code:
                    cli.main()
        self.assertEqual(exit_code.exception.code, 2)
        self.assertIn("Input file not found", err.getvalue())

    def test_review_template_success_and_error(self):
        output = self.root / "templates" / "review.json"
        printed = self.call_main(
            "review-template", self.manuscript, "--mode", "parallel", "--out", output
        )
        self.assertIn("Review mode: parallel", printed)
        self.assertEqual(json.loads(output.read_text())["review_mode"], "parallel")
        with patch.object(sys, "argv", ["sra", "review-template", str(self.root / "absent.md"),
                                         "--out", str(self.root / "failure.json")]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exit_code:
                    cli.main()
        self.assertEqual(exit_code.exception.code, 2)

    def test_stats_pass_and_partial_and_validation_error(self):
        specimen = {
            "test": "welch_t",
            "group_a": {"mean": 2, "sd": 1, "n": 20},
            "group_b": {"mean": 1, "sd": 2, "n": 25},
        }
        calculation = stats.verify_welch_t_test(specimen)["calculated"]
        spec = dict(specimen, reported={"t": calculation["t"]}, tolerances={"default": 1e-10})
        source = self.root / "stats.json"
        source.write_text(json.dumps(spec), encoding="utf-8")
        output = self.root / "results" / "stats.json"
        printed = self.call_main("verify-stats", source, "--out", output)
        self.assertIn("status: PASS", printed)
        self.assertEqual(json.loads(output.read_text())["status"], "PASS")
        spec["reported"]["t"] = calculation["t"] + 1
        source.write_text(json.dumps(spec), encoding="utf-8")
        self.captured = io.StringIO()
        printed = self.call_main("verify-stats", source, "--out", output, expected_code=1)
        self.assertIn("status: FAIL", printed)
        source.write_text("invalid JSON", encoding="utf-8")
        with patch.object(sys, "argv", ["sra", "verify-stats", str(source), "--out", str(output)]):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exit_code:
                    cli.main()
        self.assertEqual(exit_code.exception.code, 2)

    def test_model_review_reports_structural_rejection_and_errors(self):
        output = self.root / "model" / "result.json"
        def fake_model_review(template, manuscript, **kwargs):
            self.assertEqual(manuscript, TEXT)
            return template
        with patch("sra.cli.request_single_model_review", side_effect=fake_model_review):
            with patch("sra.cli.validate_semantic_review", return_value={
                "status": "REJECTED", "errors": ["synthetic structural error"]
            }):
                printed = self.call_main(
                    "review-model", self.manuscript, "--model", "test-only",
                    "--out", output, expected_code=2,
                )
        self.assertIn("- synthetic structural error", printed)
        self.assertTrue(output.is_file())
        self.assertTrue(output.with_name("result.provenance.json").is_file())

    def test_model_review_failure_is_reported_by_argparse(self):
        with patch.object(sys, "argv", [
            "sra", "review-model", str(self.manuscript),
            "--model", "test-only", "--out", str(self.root / "failure.json"),
        ]):
            with patch("sra.cli.request_single_model_review", side_effect=RuntimeError("network unavailable")):
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    with self.assertRaises(SystemExit) as exc:
                        cli.main()
        self.assertEqual(exc.exception.code, 2)
        self.assertIn("network unavailable", errors.getvalue())

    def test_path_resolution_errors_are_closed_before_modification(self):
        with patch.object(sys, "argv", ["sra", "audit", str(self.manuscript),
                                         "--out", str(self.root / "failure")]):
            with patch("sra.cli.Path.resolve", side_effect=OSError("unsafe filesystem path")):
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    with self.assertRaises(SystemExit) as exc:
                        cli.main()
        self.assertEqual(exc.exception.code, 2)
        self.assertIn("Could not safely resolve", errors.getvalue())

    def test_cli_python_module_entrypoint_exits_with_main_status(self):
        prefix = self.root / "module-entry"
        with patch.object(sys, "argv", ["python -m sra.cli", "audit",
                                        str(self.manuscript), "--out", str(prefix)]):
            with contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:
                    runpy.run_module("sra.cli", run_name="__main__")
        self.assertEqual(exc.exception.code, 0)
        self.assertTrue(prefix.with_suffix(".json").exists())
