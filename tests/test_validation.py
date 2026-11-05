"""Tests for independent expert label completeness and metrics calculations."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.validation import evaluate_blinded_labels
from sra.benchmark import _get_article


def fixtures(tmp):
    b = Path(tmp) / "benchmark.json"
    l = Path(tmp) / "labels.json"
    doc_hashes = {"PMC1790863": "a"*64, "PMC10217082": "b"*64}
    benchmark = {
        "kind": "unlabeled_real_paper_smoke_test",
        "paper_results": [
            {"pmcid": "PMC1790863", "status": "PROCESSED",
             "response_sha256": doc_hashes["PMC1790863"],
             "writing_finding_codes": ["missing_section"]},
            {"pmcid": "PMC10217082", "status": "PROCESSED",
             "response_sha256": doc_hashes["PMC10217082"],
             "writing_finding_codes": ["unmatched_numeric_citation"]},
        ],
    }
    labels = {"finding_codes": ["missing_section", "unmatched_numeric_citation"],
              "cases": []}
    truth = {
        ("PMC1790863", "missing_section"): True,
        ("PMC1790863", "unmatched_numeric_citation"): False,
        ("PMC10217082", "missing_section"): True,
        ("PMC10217082", "unmatched_numeric_citation"): False,
    }
    for (pmcid, code), label in truth.items():
        labels["cases"].append({
            "pmcid": pmcid, "code": code,
            "source_sha256": doc_hashes[pmcid], "expert_label": label,
            "reviewer_ids": ["blind_A", "blind_B"], "adjudicated": True,
        })
    b.write_text(json.dumps(benchmark), encoding="utf-8")
    l.write_text(json.dumps(labels), encoding="utf-8")
    return b, l, labels


class IndependentValidationTests(unittest.TestCase):
    def test_confusion_matrix_metrics_and_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, labels = fixtures(tmp)
            result = evaluate_blinded_labels(b, l)
        self.assertEqual(result["paper_count"], 2)
        self.assertEqual(result["labelled_units"], 4)
        m = result["micro_average"]
        self.assertEqual((m["tp"], m["fp"], m["fn"], m["tn"]), (1, 1, 1, 1))
        self.assertEqual(m["precision"], 0.5)
        self.assertEqual(m["recall"], 0.5)
        self.assertEqual(m["specificity"], 0.5)
        self.assertLess(m["precision_ci95_wilson"][0], 0.5)
        self.assertGreater(m["precision_ci95_wilson"][1], 0.5)
        self.assertEqual(len(result["source_benchmark_sha256"]), 64)

    def test_incomplete_annotation_coverage_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, labels = fixtures(tmp)
            labels["cases"].pop()
            l.write_text(json.dumps(labels), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "coverage incomplete"):
                evaluate_blinded_labels(b, l)

    def test_duplicate_annotation_units_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, labels = fixtures(tmp)
            labels["cases"].append(dict(labels["cases"][0]))
            l.write_text(json.dumps(labels), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "repeated"):
                evaluate_blinded_labels(b, l)

    def test_invalid_hash_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, labels = fixtures(tmp)
            labels["cases"][0]["source_sha256"] = "0"*64
            l.write_text(json.dumps(labels), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source hash"):
                evaluate_blinded_labels(b, l)

    def test_reviewer_independence_declaration_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, labels = fixtures(tmp)
            for reviewers in (["same", "same"], ["one"], [], None):
                with self.subTest(reviewers=reviewers):
                    labels["cases"][0]["reviewer_ids"] = reviewers
                    l.write_text(json.dumps(labels), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "two declared"):
                        evaluate_blinded_labels(b, l)

    def test_adjudication_is_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, labels = fixtures(tmp)
            labels["cases"][0]["adjudicated"] = False
            l.write_text(json.dumps(labels), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "adjudication"):
                evaluate_blinded_labels(b, l)

    def test_bool_labels_not_coerced(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, labels = fixtures(tmp)
            labels["cases"][0]["expert_label"] = "true"
            l.write_text(json.dumps(labels), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "boolean"):
                evaluate_blinded_labels(b, l)

    def test_cli_writes_metric_report_without_overwriting_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, _ = fixtures(tmp)
            out = Path(tmp) / "comparison.json"
            original = l.read_bytes()
            process = subprocess.run(
                [sys.executable, "-m", "sra.cli", "evaluate-labels", str(b), str(l),
                 "--out", str(out)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(original, l.read_bytes())
            self.assertEqual(json.loads(out.read_text())["labelled_units"], 4)

    def test_malformed_json_roots_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, labels = fixtures(tmp)
            l.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON objects"):
                evaluate_blinded_labels(b, l)

    def test_duplicate_pmcid_in_frozen_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, labels = fixtures(tmp)
            data = json.loads(b.read_text(encoding="utf-8"))
            data["paper_results"].append(dict(data["paper_results"][0]))
            b.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate processed PMCIDs"):
                evaluate_blinded_labels(b, l)

    def test_no_processed_papers_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            b, l, _ = fixtures(tmp)
            b.write_text(json.dumps({
                "kind": "unlabeled_real_paper_smoke_test", "paper_results": []
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No processed papers"):
                evaluate_blinded_labels(b, l)


class BioCApiIdFormatTests(unittest.TestCase):
    def test_alternate_bioc_pmcid_field_is_accepted(self):
        from unittest.mock import Mock
        info = {"article-id_pmc": None,
                "article-id_pmcid": "PMC8793676",
                "article-id_doi": "10.1371/test",
                "license": "CC BY"}
        passages = [{"infons": dict(info, section_type="TITLE"), "text": "A study", "type": "front"}]
        for section in ("INTRO", "METHODS", "RESULTS", "DISCUSS", "CONCL"):
            passages.append({"infons": {"section_type": section},
                             "text": "Study measured relevant evidence.", "type": "paragraph"})
        body = json.dumps([{"documents": [{"id": "unknown", "passages": passages}]}]).encode()
        response = Mock()
        response.read.return_value = body
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        with patch("sra.benchmark.urlopen", return_value=response):
            text, meta = _get_article("PMC8793676")
        self.assertEqual(meta["pmcid"], "PMC8793676")
        self.assertIn("# Methods", text)
        self.assertIn("# Results", text)

    def test_wrong_bioc_identifier_is_rejected(self):
        from unittest.mock import Mock
        passages = [{"infons": {"article-id_pmcid": "PMC1111111",
                                "article-id_doi": "10.1234/a",
                                "section_type": "TITLE"},
                     "text": "A wrong study"}]
        body = json.dumps([{"documents": [{"id": "unknown", "passages": passages}]}]).encode()
        response = Mock()
        response.read.return_value = body
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        with patch("sra.benchmark.urlopen", return_value=response):
            with self.assertRaisesRegex(ValueError, "does not match"):
                _get_article("PMC8793676")


if __name__ == "__main__":
    unittest.main()
