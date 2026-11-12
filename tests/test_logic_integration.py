"""Read-only CLI/unified-review integration for formal logic."""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.cli import main
from sra.document import load_document
from sra.logic_report import logic_markdown
from sra.review import review_manuscript
from sra.review_report import review_markdown
from test_logic import boolean_problem


class LogicIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paper = self.root / "paper.md"
        self.paper.write_text("# Assumptions\nThe hypothesis is assumed true for this example.\n", encoding="utf-8")
        document = load_document(self.paper)
        self.problem = boolean_problem()
        self.problem.update(source_sha256=document.sha256,
                            extracted_text_sha256=hashlib.sha256(document.text.encode()).hexdigest())
        self.problem["claims"][0].update(source_quote="The hypothesis is assumed true for this example.", line=2)
        self.spec = self.root / "spec.json"
        self.spec.write_text(json.dumps(self.problem), encoding="utf-8")

    def call(self, *args):
        with patch("sys.argv", ["sra", *map(str,args)]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return main()

    def test_cli_outputs_separate_findings_and_never_changes_inputs(self):
        before = self.paper.read_bytes(), self.spec.read_bytes()
        code = self.call("verify-logic", self.spec, "--manuscript", self.paper, "--out", self.root / "report")
        self.assertEqual(code, 0)
        report = json.loads((self.root / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["source_binding"]["status"], "source_matched")
        text = (self.root / "report.md").read_text(encoding="utf-8")
        self.assertIn("Findings for the user", text)
        self.assertIn("Line 2", text)
        self.assertEqual((self.paper.read_bytes(),self.spec.read_bytes()), before)

    def test_cli_protects_both_specification_and_manuscript(self):
        for out in (self.spec, self.paper):
            with self.subTest(out=out), self.assertRaises(SystemExit) as caught:
                self.call("verify-logic", self.spec, "--manuscript", self.paper, "--out", out)
            self.assertEqual(caught.exception.code, 2)
        path = self.root / "alias.json"
        path.write_text("existing")
        os.link(path, self.root / "alias.md")
        with self.assertRaises(SystemExit):
            self.call("verify-logic", self.spec, "--out", self.root / "alias")
        self.assertEqual(path.read_text(), "existing")

    def test_standalone_cli_unbound_and_partial_budget_and_invalid_input(self):
        self.assertEqual(self.call("verify-logic", self.spec, "--out", self.root / "unbound"),0)
        with patch("sra.logic._check", return_value="unknown"):
            self.assertEqual(self.call("verify-logic", self.spec, "--out", self.root / "partial"),1)
        self.spec.write_text("[]")
        with self.assertRaises(SystemExit):
            self.call("verify-logic", self.spec, "--out", self.root / "bad")
        self.assertFalse((self.root / "bad.json").exists())

    def test_unified_source_bound_logic_is_an_additional_module_and_separate_report(self):
        report = review_manuscript(self.paper, logic_spec=self.problem)
        self.assertEqual(report["execution_status"], "complete")
        self.assertEqual(report["modules"]["logic"]["result"]["claims"][0]["status"], "VERIFIED")
        self.assertIn("Deterministic formal logic review", review_markdown(report))
        self.assertIn("formalization_semantics_not_verified", report["coverage_gaps"])
        self.assertEqual(self.call("review", self.paper, "--logic-spec", self.spec, "--out", self.root / "combined"),0)

    def test_unified_budget_and_missing_dependency_do_not_masquerade_as_complete(self):
        with patch("sra.logic._check", return_value="unknown"):
            report = review_manuscript(self.paper, logic_spec=self.problem)
        self.assertEqual(report["execution_status"], "partial")
        self.assertEqual(report["modules"]["logic"]["status"], "failed")
        error = RuntimeError("optional solver missing")
        error.__cause__ = ImportError("z3")
        with patch("sra.logic._load_z3", side_effect=error):
            report = review_manuscript(self.paper, logic_spec=self.problem)
        self.assertEqual(report["modules"]["logic"]["status"], "unavailable")

    def test_invalid_logic_blocks_registry_and_model_requests(self):
        with patch("sra.doi._lookup_registry") as registry, patch("sra.paper_review.request_single_model_review") as model:
            with self.assertRaises(ValueError):
                review_manuscript(self.paper, logic_spec={**self.problem, "claims":[]},
                                  online=True, send_to_model=True, model="fake")
        registry.assert_not_called()
        model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
