"""The three-stage expert-validation pipeline, end to end, on synthetic labels.

The labels here are synthetic: this test proves the machinery the runbook
prescribes works and keeps producing the pre-registered metrics. It is not
evidence about the tool's accuracy, and nothing it prints may be read as such.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from sra.labeling import merge_adjudicated_labels
from sra.validation import evaluate_blinded_labels

CODES = ["language.hedging", "language.passive_voice"]
PAPERS = [
    {
        "pmcid": "PMC1000001",
        "status": "PROCESSED",
        "response_sha256": "a" * 64,
        "writing_finding_codes": ["language.hedging"],
    },
    {
        "pmcid": "PMC1000002",
        "status": "PROCESSED",
        "response_sha256": "b" * 64,
        "writing_finding_codes": [],
    },
]
TRUTH = {
    ("PMC1000001", "language.hedging"): True,
    ("PMC1000001", "language.passive_voice"): False,
    ("PMC1000002", "language.hedging"): True,
    ("PMC1000002", "language.passive_voice"): False,
}
DISAGREEMENT = ("PMC1000002", "language.hedging")


class ValidationPipelineTests(unittest.TestCase):
    def _write(self, folder: Path, name: str, payload: dict) -> Path:
        path = folder / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _sheet(self, folder: Path, reviewer: str, benchmark_sha: str, flip: bool) -> Path:
        cases = []
        for paper in PAPERS:
            for code in CODES:
                key = (paper["pmcid"], code)
                verdict = TRUTH[key]
                if flip and key == DISAGREEMENT:
                    verdict = not verdict
                cases.append({
                    "pmcid": paper["pmcid"],
                    "code": code,
                    "source_sha256": paper["response_sha256"],
                    "verdict": verdict,
                })
        return self._write(folder, f"{reviewer}.json", {
            "kind": "blinded_validation_worksheet",
            "benchmark_sha256": benchmark_sha,
            "reviewer_id": reviewer,
            "finding_codes": CODES,
            "cases": cases,
        })

    def test_two_reviewers_one_adjudicator_and_a_metric_report(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            benchmark = self._write(folder, "benchmark.json", {
                "kind": "unlabeled_real_paper_smoke_test",
                "paper_results": PAPERS,
            })
            sha = hashlib.sha256(benchmark.read_bytes()).hexdigest()
            sheet_a = self._sheet(folder, "reviewer-a", sha, flip=False)
            sheet_b = self._sheet(folder, "reviewer-b", sha, flip=True)
            adjudications = self._write(folder, "adjudications.json", {
                "kind": "reviewer_adjudications",
                "adjudicator_id": "adjudicator-1",
                "decisions": [{
                    "pmcid": DISAGREEMENT[0],
                    "code": DISAGREEMENT[1],
                    "expert_label": TRUTH[DISAGREEMENT],
                    "rationale": "Synthetic adjudication for a pipeline test, not a judgement.",
                }],
            })

            merged = merge_adjudicated_labels(benchmark, sheet_a, sheet_b, adjudications)
            report = evaluate_blinded_labels(
                benchmark, self._write(folder, "merged.json", merged)
            )

        agreement = merged["inter_reviewer_agreement"]
        self.assertEqual(agreement["units"], 4)
        self.assertEqual(agreement["disagreements"], 1)
        self.assertEqual(agreement["raw_exact_agreement"], 0.75)
        self.assertAlmostEqual(agreement["cohen_kappa"], 0.5)

        self.assertEqual(report["kind"], "conditional_expert_label_comparison")
        self.assertEqual(report["labelled_units"], 4)
        self.assertEqual(report["micro_average"]["tp"], 1)
        self.assertEqual(report["micro_average"]["fn"], 1)
        self.assertEqual(report["micro_average"]["precision"], 1.0)
        self.assertEqual(report["micro_average"]["recall"], 0.5)
        self.assertEqual(len(report["micro_average"]["recall_ci95_wilson"]), 2)
        self.assertEqual(
            set(report["metrics_by_finding_code"]), set(CODES)
        )
        self.assertTrue(any("not verified" in line for line in report["limitations"]))

    def test_incomplete_coverage_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            benchmark = self._write(folder, "benchmark.json", {
                "kind": "unlabeled_real_paper_smoke_test",
                "paper_results": PAPERS,
            })
            sha = hashlib.sha256(benchmark.read_bytes()).hexdigest()
            partial = self._write(folder, "partial.json", {
                "kind": "blinded_validation_worksheet",
                "benchmark_sha256": sha,
                "reviewer_id": "reviewer-a",
                "finding_codes": CODES,
                "cases": [{
                    "pmcid": PAPERS[0]["pmcid"],
                    "code": CODES[0],
                    "source_sha256": PAPERS[0]["response_sha256"],
                    "verdict": True,
                }],
            })
            complete = self._sheet(folder, "reviewer-b", sha, flip=False)
            adjudications = self._write(folder, "adjudications.json", {
                "kind": "reviewer_adjudications",
                "adjudicator_id": "adjudicator-1",
                "decisions": [],
            })
            with self.assertRaisesRegex(ValueError, "coverage incomplete"):
                merge_adjudicated_labels(benchmark, partial, complete, adjudications)


if __name__ == "__main__":
    unittest.main()
