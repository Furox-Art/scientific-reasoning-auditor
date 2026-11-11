"""Regression coverage for independently reproduced parsing and validation defects."""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.doi import _lookup_datacite
from sra.labeling import _load_benchmark, build_validation_pack
from sra.statistical_consistency import (
    confidence_interval_p_conflict, impossible_p_value, mean_outside_interval,
)
from sra.statistics_review import multiplicity_finding
from sra.tabular_values import table_findings
from sra.validation import evaluate_blinded_labels
from sra.writing import writing_report_markdown


class IndependentBugRegressions(unittest.TestCase):
    def test_multilingual_mean_extraction_does_not_crash(self):
        for keyword in ("mean", "moyenne", "平均", "평균", "ortalaması"):
            with self.subTest(keyword=keyword):
                text = f"{keyword} 5.0 (95% CI [1.0, 3.0])."
                self.assertEqual(len(mean_outside_interval(text)), 1)
                self.assertEqual(mean_outside_interval(
                    f"{keyword} 2.0 (95% CI [1.0, 3.0])."), [])

    def test_p_inequality_is_not_misread_as_exact_p(self):
        effect = "The difference was 0.2 (95% CI [0.01, 0.4], p {} 0.05)."
        for op in ("<", "<=", "≤"):
            with self.subTest(op=op):
                self.assertEqual(confidence_interval_p_conflict(effect.format(op)), [])
        self.assertEqual(len(confidence_interval_p_conflict(
            "The difference was 0.2 (95% CI [-0.01, 0.4], p < 0.05).")), 1)
        for op in (">", ">=", "≥", "="):
            with self.subTest(op=op):
                self.assertEqual(len(confidence_interval_p_conflict(
                    effect.format(op))), 1)
        self.assertEqual(confidence_interval_p_conflict(
            "The difference was 0.2 (95% CI [0.01, 0.4], p > 0.01)."), [])

    def test_impossible_probability_open_and_closed_boundaries(self):
        for statement in ("p < 0", "p < -0.1", "p <= -0.1", "p > 1", "p >= 1.1"):
            with self.subTest(statement=statement):
                self.assertEqual(len(impossible_p_value(statement)), 1)
        for statement in ("p <= 1", "p >= 1", "p < 0.05", "p <= 0.05", "p >= 0"):
            with self.subTest(statement=statement):
                self.assertEqual(impossible_p_value(statement), [])

    def test_periods_in_table_statistic_headers(self):
        for heading in ("S.D.", "S.E.", "No."):
            with self.subTest(heading=heading):
                sample = f"Group  {heading}  p\nA  -1.2  0.03" if heading != "No." else (
                    "Group  No.  p\nA  0  0.03")
                findings = table_findings(sample)
                self.assertEqual(len(findings), 1)
                self.assertEqual(findings[0].evidence_locations[0]["column"], heading)

    def test_negated_multiple_testing_adjustment_is_not_credit(self):
        self.assertIsNotNone(multiplicity_finding(
            "p = 0.01, p = 0.02, and p = 0.03. Bonferroni correction was not performed."))
        self.assertIsNotNone(multiplicity_finding(
            "No Holm correction was applied. p = 0.01, p = 0.02, and p = 0.03."))
        self.assertIsNone(multiplicity_finding(
            "Bonferroni correction was performed. p = 0.01, p = 0.02, and p = 0.03."))
        self.assertIsNone(multiplicity_finding(
            "Bonferroni correction was not performed. Holm correction was performed. "
            "p = 0.01, p = 0.02, and p = 0.03."))

    def test_labels_require_real_nonnull_source_hashes(self):
        benchmark = {"kind": "unlabeled_real_paper_smoke_test",
                     "paper_results": [{"pmcid": "PMC12345", "status": "PROCESSED",
                                        "response_sha256": "a" * 64,
                                        "writing_finding_codes": []}]}
        labels = {"finding_codes": ["c"],
                  "cases": [{"pmcid": "PMC12345", "code": "c", "source_sha256": "a" * 64,
                             "expert_label": False, "reviewer_ids": ["A", "B"],
                             "adjudicated": True}]}
        with tempfile.TemporaryDirectory() as tmp:
            b, l = Path(tmp) / "benchmark.json", Path(tmp) / "labels.json"
            def evaluate():
                b.write_text(json.dumps(benchmark), encoding="utf-8")
                l.write_text(json.dumps(labels), encoding="utf-8")
                return evaluate_blinded_labels(b, l)
            self.assertEqual(evaluate()["labelled_units"], 1)
            for invalid in (None, "", "g" * 64, "A" * 64):
                with self.subTest(source_hash=invalid):
                    labels["cases"][0]["source_sha256"] = invalid
                    with self.assertRaisesRegex(ValueError, "SHA-256"):
                        evaluate()
            labels["cases"][0]["source_sha256"] = "a" * 64
            for invalid in (None, "bad", "A" * 64):
                with self.subTest(benchmark_hash=invalid):
                    benchmark["paper_results"][0]["response_sha256"] = invalid
                    with self.assertRaisesRegex(ValueError, "SHA-256"):
                        evaluate()
            benchmark["paper_results"][0]["response_sha256"] = "b" * 64
            with self.assertRaisesRegex(ValueError, "differs"):
                evaluate()

    def test_pmcid_traversal_rejected_before_network_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            location = Path(tmp) / "benchmark.json"
            for bad in ("../outside", "../../outside", "/tmp/file", "PMC12/../../outside", "ＰＭＣ12345"):
                with self.subTest(bad=bad):
                    location.write_text(json.dumps(
                        {"kind": "unlabeled_real_paper_smoke_test",
                         "paper_results": [{"pmcid": bad, "status": "PROCESSED",
                                            "response_sha256": "a" * 64,
                                            "writing_finding_codes": []}]}
                    ), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "PMCID"):
                        _load_benchmark(location)
            location.write_text(json.dumps(
                {"kind": "unlabeled_real_paper_smoke_test",
                 "paper_results": [{"pmcid": "PMC12345", "status": "PROCESSED",
                                    "response_sha256": "a" * 64,
                                    "writing_finding_codes": []}]}
            ), encoding="utf-8")
            self.assertEqual(_load_benchmark(location)[1][0]["pmcid"], "PMC12345")

    def test_papers_containment_rejects_escaped_output_path(self):
        source_hash = "a" * 64
        with tempfile.TemporaryDirectory() as tmp:
            benchmark = Path(tmp) / "benchmark.json"
            benchmark.write_text(json.dumps({
                "kind": "unlabeled_real_paper_smoke_test",
                "paper_results": [{"pmcid": "PMC12345", "status": "PROCESSED",
                                   "response_sha256": source_hash,
                                   "writing_finding_codes": []}],
            }), encoding="utf-8")
            with patch("sra.labeling._get_article", return_value=(
                "article", {"response_sha256": source_hash})), patch.object(
                    Path, "is_relative_to", return_value=False):
                with self.assertRaisesRegex(ValueError, "papers directory"):
                    build_validation_pack(
                        benchmark, Path(tmp) / "pack", ["A", "B"], ["x"], online=True)

    def test_academic_report_treats_markdown_links_as_plain_text(self):
        payload = {"source": "file.md", "source_sha256": "a" * 64, "status": "REVIEW",
                   "genre": "original-research", "metrics": {"words": 50},
                   "findings": [{"line": 2, "code": "sample", "message":
                                 "[click](https://example.invalid/)"}],
                   "style_suggestions": [{"line": 2, "code": "suggestion",
                                          "excerpt": "[click](https://example.invalid/)",
                                          "suggestion": "reword"}],
                   "limitations": ["Automated review only."]}
        md = writing_report_markdown(payload)
        self.assertNotIn("[click](https://example.invalid/)", md)
        self.assertIn("\\[click\\](https://example.invalid/)", md)

    def test_malformed_datacite_payload_is_unverified(self):
        class FakeOpener:
            def __init__(self, body):
                self.body = body
            def open(self, *_args, **_kwargs):
                return io.BytesIO(json.dumps(self.body).encode("utf-8"))
        ok = {"data": {"attributes": {"doi": "10.1234/example", "titles":
               [{"title": "Valid title"}], "creators": [{"familyName": "Doe"}],
               "types": {"resourceTypeGeneral": "Text"}}}}
        for body in ([], {"data": []}, {"data": {"attributes": []}},
                     {"data": {"attributes": {**ok["data"]["attributes"], "titles": {}}}},
                     {"data": {"attributes": {**ok["data"]["attributes"], "creators": {}}}},
                     {"data": {"attributes": {**ok["data"]["attributes"], "types": []}}}):
            with self.subTest(body=str(body)[:100]), patch(
                "sra.doi.build_opener", return_value=FakeOpener(body)
            ):
                self.assertEqual(_lookup_datacite("10.1234/example", timeout=1)["status"],
                                 "UNVERIFIED")
        with patch("sra.doi.build_opener", return_value=FakeOpener(ok)):
            self.assertEqual(_lookup_datacite("10.1234/example", timeout=1)["status"],
                             "REGISTERED_IN_DATACITE")


if __name__ == "__main__":
    unittest.main()
