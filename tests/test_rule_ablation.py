"""Rule ablation on the committed synthetic corpus.

The report is committed, so these tests fail when a rule stops firing on the case
that plants it, when a rule starts firing where nothing was planted, or when the
documented numbers drift away from a fresh run.
"""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from sra.rule_ablation import evaluate_rule_corpus

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "benchmarks" / "rule_ablation"
REPORT = CORPUS / "report.json"


def all_rule_ids() -> list[str]:
    ids: set[str] = set()
    for path in sorted((ROOT / "src" / "sra").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in {"Finding", "_finding"} or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                if "." in first.value:
                    ids.add(first.value)
    return sorted(ids)


class SpecValidationTests(unittest.TestCase):
    def _write(self, folder: Path, payload: object) -> Path:
        path = folder / "cases.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_a_spec_without_cases_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self._write(Path(directory), {"cases": []})
            with self.assertRaisesRegex(ValueError, "no cases"):
                evaluate_rule_corpus(spec, ["structure.methods_missing"])

    def test_a_case_without_a_document_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self._write(Path(directory), {"cases": [{"expected": []}]})
            with self.assertRaisesRegex(ValueError, "document path"):
                evaluate_rule_corpus(spec, ["structure.methods_missing"])

    def test_a_spec_that_is_not_an_object_with_cases_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self._write(Path(directory), {"cases": "not-a-list"})
            with self.assertRaisesRegex(ValueError, "object with a cases list"):
                evaluate_rule_corpus(spec, ["structure.methods_missing"])

    def test_a_case_that_is_not_an_object_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            spec = self._write(Path(directory), {"cases": ["paper.md"]})
            with self.assertRaisesRegex(ValueError, "case must be an object"):
                evaluate_rule_corpus(spec, ["structure.methods_missing"])

    def test_an_expected_list_of_non_strings_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "paper.md").write_text("# Methods\nx\n", encoding="utf-8")
            spec = self._write(folder, {
                "cases": [{"document": "paper.md", "expected": [1]}],
            })
            with self.assertRaisesRegex(ValueError, "expected list"):
                evaluate_rule_corpus(spec, ["structure.methods_missing"])

    def test_an_expected_rule_that_does_not_exist_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "paper.md").write_text("# Methods\nx\n", encoding="utf-8")
            spec = self._write(folder, {
                "cases": [{"document": "paper.md", "expected": ["no.such_rule"]}],
            })
            with self.assertRaisesRegex(ValueError, "do not exist"):
                evaluate_rule_corpus(spec, ["structure.methods_missing"])


class CommittedCorpusTests(unittest.TestCase):
    def test_the_corpus_still_exercises_the_rules_it_plants(self):
        report = evaluate_rule_corpus(CORPUS / "cases.json", all_rule_ids())
        summary = report["summary"]
        self.assertEqual(summary["missed_planted"], [], "a planted rule stopped firing")
        self.assertGreaterEqual(
            summary["exercised"], 21, "the corpus stopped exercising the rules it used to"
        )
        self.assertEqual(
            summary["never_fired"],
            [],
            "a rule stopped firing on the case that plants it",
        )

    def test_the_committed_report_matches_a_fresh_run(self):
        fresh = evaluate_rule_corpus(CORPUS / "cases.json", all_rule_ids())
        committed = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(
            committed["summary"], fresh["summary"],
            "benchmarks/rule_ablation/report.json is stale; rerun the ablation",
        )
        self.assertEqual(committed["per_rule"], fresh["per_rule"])


if __name__ == "__main__":
    unittest.main()
