"""Reproducible sentence-level scientific-writing annotation evaluation.

Fixtures are explicitly *synthetic test doubles*, not human-labelled
scientific benchmark evidence. The frozen real-paper report is separate.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sra.academic_benchmark import evaluate_arxiv_edit_pairs

COLUMNS = [
    "id", "sentence-1", "sentence-2", "arxiv-id",
    "edits-combination-0", "edits-combination-1", "edits-combination-2",
]
GRAMMAR = "{'0': {'intention': 'Improve-grammar-Typo', 'type': 'Substitute'}}"
LANGUAGE = "{'0': {'intention': 'Lang-professional-Improve-style', 'type': 'Substitute'}}"
CONTENT = "{'0': {'intention': 'Content', 'type': 'Substitute'}}"
FORMAT = "{'0': {'intention': 'Format', 'type': 'Substitute'}}"


def small_dataset(path: Path) -> bytes:
    rows = [
        ("1", "We performed a analysis of the outcome.",
         "We performed an analysis of the outcome.", GRAMMAR),
        ("2", "The effect was much stronger.",
         "The effect was notably stronger.", LANGUAGE),
        ("3", "The sample is recorded for treatment.",
         "The sample is recorded for placebo treatment.", CONTENT),
        ("4", "The results indicates the outcome.",
         "The result indicates the outcome.", CONTENT),
        ("5", "The measured field was 5 tesla.",
         "The measured magnetic field was 5 tesla.", FORMAT),
        ("6", "We used in order to classify the subjects.",
         "We used a method to classify the subjects.", GRAMMAR),
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for ident, source, target, label in rows:
            writer.writerow([ident, source, target, "1901.000" + ident, label, "{}", "{}"])
    return path.read_bytes()


class LanguageBenchmarkTests(unittest.TestCase):
    def test_confusion_matrix_and_safe_limitation_terms(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            raw = small_dataset(file)
            report = evaluate_arxiv_edit_pairs(
                file, expected_sha256=hashlib.sha256(raw).hexdigest(),
            )
        self.assertEqual(report["rows_evaluated"], 6)
        self.assertEqual(report["unique_papers"], 6)
        self.assertEqual(
            report["confusion_matrix_against_revision_intents"],
            {"tp": 2, "fp_proxy": 1, "fn": 1, "tn_proxy": 2},
        )
        self.assertAlmostEqual(report["conditional_detection"]["positive_recall"], 2/3)
        self.assertAlmostEqual(report["conditional_detection"]["precision_proxy"], 2/3)
        self.assertAlmostEqual(
            report["conditional_detection"]["nonlanguage_revision_specificity_proxy"], 2/3,
        )
        self.assertEqual(report["suggested_replacements"]["machine_string_substitution_candidates"], 3)
        self.assertTrue(any("not" in item.lower() for item in report["limitations"]))
        self.assertIn("precision_proxy", report["conditional_detection"])

    def test_hash_mismatch_blocks_misleading_comparison(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            small_dataset(file)
            with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
                evaluate_arxiv_edit_pairs(file, expected_sha256="0"*64)

    def test_invalid_hash_format(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            small_dataset(file)
            with self.assertRaisesRegex(ValueError, "lowercase hex"):
                evaluate_arxiv_edit_pairs(file, expected_sha256="not_a_hash")

    def test_truncation_is_never_silently_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            small_dataset(file)
            with self.assertRaisesRegex(ValueError, "biased prefix"):
                evaluate_arxiv_edit_pairs(file, max_rows=3)

    def test_duplicate_ids_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            small_dataset(file)
            lines = file.read_text().splitlines()
            # Duplicate first data row, including original identifier.
            file.write_text("\n".join(lines + [lines[1]]) + "\n")
            with self.assertRaisesRegex(ValueError, "unique"):
                evaluate_arxiv_edit_pairs(file)

    def test_no_annotations_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            small_dataset(file)
            rows = list(csv.DictReader(file.read_text(encoding="utf-8").splitlines()))
            rows[0]["edits-combination-0"] = "{}"
            with file.open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "No original human"):
                evaluate_arxiv_edit_pairs(file)

    def test_malicious_nonliteral_annotation_is_rejected_not_executed(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            small_dataset(file)
            rows = list(csv.DictReader(file.read_text(encoding="utf-8").splitlines()))
            rows[0]["edits-combination-0"] = "__import__('os').system('false')"
            with file.open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises((ValueError, SyntaxError)):
                evaluate_arxiv_edit_pairs(file)

    def test_invalid_rows_limits_and_schema(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            small_dataset(file)
            with self.assertRaisesRegex(ValueError, "max_rows"):
                evaluate_arxiv_edit_pairs(file, max_rows=0)
            file.write_text("sentence,label\nHello,1\n")
            with self.assertRaisesRegex(ValueError, "schema"):
                evaluate_arxiv_edit_pairs(file)

    def test_identical_sentence_pair_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            small_dataset(file)
            rows = list(csv.DictReader(file.read_text(encoding="utf-8").splitlines()))
            rows[0]["sentence-2"] = rows[0]["sentence-1"]
            with file.open("w", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=COLUMNS)
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaisesRegex(ValueError, "identical"):
                evaluate_arxiv_edit_pairs(file)

    def test_cli_writes_report_without_overwriting_human_labels(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            data = small_dataset(file)
            output = Path(root) / "report.json"
            process = subprocess.run([
                sys.executable, "-m", "sra.cli", "benchmark-language", str(file),
                "--expected-sha256", hashlib.sha256(data).hexdigest(),
                "--out", str(output),
            ], capture_output=True, text=True, check=False)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(file.read_bytes(), data)
            result = json.loads(output.read_text())
            self.assertEqual(result["rows_evaluated"], 6)
            self.assertIn("not", process.stdout.lower())

    def test_cli_refuses_to_overwrite_corpus(self):
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "edits.csv"
            data = small_dataset(file)
            process = subprocess.run([
                sys.executable, "-m", "sra.cli", "benchmark-language", str(file),
                "--expected-sha256", hashlib.sha256(data).hexdigest(),
                "--out", str(file),
            ], capture_output=True, text=True, check=False)
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("overwrite", process.stderr)
            self.assertEqual(file.read_bytes(), data)

    def test_frozen_aggregated_real_paper_report_contains_no_raw_sentences(self):
        report_path = Path(__file__).resolve().parents[1] / "benchmarks/arxivedits_style_test_20261105.json"
        if not report_path.is_file():
            self.skipTest("External benchmark not yet materialized.")
        report = json.loads(report_path.read_text())
        self.assertEqual(report["source_csv_sha256"], "6541dce4c7f82019e8f24dc0259a1a04e20dd853d87b465adeb1febc2cbf0220")
        self.assertEqual(report["rows_evaluated"], 200)
        self.assertEqual(report["unique_papers"], 69)
        matrix = report["confusion_matrix_against_revision_intents"]
        self.assertEqual(sum(matrix.values()), 200)
        self.assertEqual(report["split"], "test")
        self.assertLess(report_path.stat().st_size, 15_000)


if __name__ == "__main__":
    unittest.main()
