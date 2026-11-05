"""Blinded domain template and conditional reliability/aggregation tests.

All assessments below are synthetic *test fixtures*, NOT real experts.
"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from sra.document import load_document
from sra.domain_adjudication import make_domain_template, validate_domain_adjudication
from sra.domain_cohort import aggregate_domain_reports
from sra.domain_evidence import review_domain


def document(folder: Path, idx: int):
    path = folder / f"science_{idx}.md"
    path.write_text(
        f"# Methods\nThe instrument was calibrated with a NIST reference {idx}.\n"
        f"Measurements were repeated n = {idx+10} times.\n"
        f"# Results\nA measured signal was 3.2 ± 0.2 mV.\n", encoding="utf-8"
    )
    return load_document(path)


def complete_mock_template(doc, *, disagreements: bool = False):
    obj = make_domain_template(doc, "physics")
    for idx, rule in enumerate(obj["assessments"]):
        positive = idx % 2 == 0
        verdict = "partially_reported" if positive else "not_reported"
        quote = "The instrument was calibrated with a NIST reference"
        rule["reviewer_assessments"] = [
            {
                "reviewer_id": "test-double-A",
                "verdict": verdict,
                "rationale": "This test fixture is checking review contract integrity only.",
                "source_quote": quote if positive else None,
            },
            {
                "reviewer_id": "test-double-B",
                "verdict": ("uncertain" if disagreements and idx == 0 else verdict),
                "rationale": "This is a synthetic test double, not independent scientific review.",
                "source_quote": quote if positive and not (disagreements and idx == 0) else None,
            },
        ]
        rule["adjudicated_verdict"] = verdict
        rule["adjudication_rationale"] = (
            "The final label in this synthetic unit test is not real expert evidence."
        )
    return obj


class BlindedDomainAndReliabilityTests(unittest.TestCase):
    def test_blinded_template_excludes_system_predictions_and_quotes(self):
        with tempfile.TemporaryDirectory() as root:
            doc = document(Path(root), 1)
            unblinded = review_domain(doc, "physics")
            blinded = make_domain_template(doc, "physics")
        self.assertTrue(blinded["blinded"])
        self.assertEqual(len(unblinded["items"]), len(blinded["assessments"]))
        for item in blinded["assessments"]:
            self.assertNotIn("automated_status", item)
            self.assertNotIn("source_candidates", item)
            self.assertEqual(item["reviewer_assessments"], [])

    def test_structurally_accepted_review_reports_per_rule_confusion_and_kappa(self):
        with tempfile.TemporaryDirectory() as root:
            doc = document(Path(root), 2)
            outcome = validate_domain_adjudication(
                doc, "physics", complete_mock_template(doc),
            )
        self.assertEqual(outcome["reviewer_agreement"]["raw_exact_agreement"], 1)
        self.assertEqual(outcome["reviewer_agreement"]["cohen_kappa"], 1)
        self.assertEqual(outcome["declared_reviewer_count"], 2)
        self.assertEqual(len(outcome["ruleset_sha256"]), 64)
        self.assertTrue(outcome["blinded_template"])
        metrics = outcome["comparison_against_adjudicated_verdicts"]
        self.assertEqual(sum(metrics["confusion_matrix"].values()), outcome["rule_count"])
        self.assertEqual(len(metrics["per_rule"]), outcome["rule_count"])
        self.assertIn("Not scientific correctness", metrics["interpretation"])

    def test_disagreements_lower_raw_agreement_and_kappa(self):
        with tempfile.TemporaryDirectory() as root:
            doc = document(Path(root), 3)
            completed = complete_mock_template(doc, disagreements=True)
            report = validate_domain_adjudication(doc, "physics", completed)
        self.assertGreater(report["reviewer_agreement"]["disagreements"], 0)
        self.assertLess(report["reviewer_agreement"]["raw_exact_agreement"], 1)

    def test_different_assessor_pairs_across_rules_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            doc = document(Path(root), 4)
            completed = complete_mock_template(doc)
            completed["assessments"][1]["reviewer_assessments"][1]["reviewer_id"] = "other-test-double"
            with self.assertRaisesRegex(ValueError, "same two reviewer IDs"):
                validate_domain_adjudication(doc, "physics", completed)

    def test_unblinded_or_prediction_prefilled_review_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            doc = document(Path(root), 5)
            for mutation in ("blind_flag", "model_predictions"):
                with self.subTest(mutation=mutation):
                    completed = complete_mock_template(doc)
                    if mutation == "blind_flag":
                        completed["blinded"] = False
                    else:
                        completed["assessments"][0]["automated_status"] = "TEXTUAL_EVIDENCE_CANDIDATE"
                    with self.assertRaisesRegex(ValueError, "[Bb]lind"):
                        validate_domain_adjudication(doc, "physics", completed)

    def test_two_report_cohort_is_conditional_and_source_bound(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            paths = []
            for idx in (6, 7):
                doc = document(folder, idx)
                result = validate_domain_adjudication(
                    doc, "physics", complete_mock_template(doc),
                )
                path = folder / f"out{idx}.json"
                path.write_text(json.dumps(result), encoding="utf-8")
                paths.append(path)
            cohort = aggregate_domain_reports(paths)
        self.assertEqual(cohort["manuscripts"], 2)
        self.assertEqual(cohort["adjudicated_rule_units"], cohort["reviewer_agreement"]["pooled_raw_agreement"]["denominator"])
        self.assertEqual(cohort["reviewer_agreement"]["pooled_raw_agreement"]["value"], 1)
        self.assertEqual(len(cohort["source_provenance"]), 2)
        self.assertIn("NOT scientific truth", cohort["limitations"][2])
        self.assertEqual(
            sum(cohort["confusion_matrix"].values()),
            cohort["adjudicated_rule_units"],
        )

    def test_duplicate_manuscript_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            doc = document(folder, 8)
            result = validate_domain_adjudication(doc, "physics", complete_mock_template(doc))
            a, b = folder / "a.json", folder / "b.json"
            payload = json.dumps(result)
            a.write_text(payload)
            b.write_text(payload)
            with self.assertRaisesRegex(ValueError, "Duplicate manuscript"):
                aggregate_domain_reports([a, b])

    def test_mixed_rulesets_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            paths = []
            for idx in (9, 10):
                doc = document(folder, idx)
                outcome = validate_domain_adjudication(doc, "physics", complete_mock_template(doc))
                if idx == 10:
                    outcome["ruleset_sha256"] = "0" * 64
                path = folder / f"out{idx}.json"
                path.write_text(json.dumps(outcome))
                paths.append(path)
            with self.assertRaisesRegex(ValueError, "identical discipline"):
                aggregate_domain_reports(paths)

    def test_mutated_confusion_counts_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            docs = [document(folder, 11), document(folder, 12)]
            paths = []
            for idx, doc in enumerate(docs):
                outcome = validate_domain_adjudication(doc, "physics", complete_mock_template(doc))
                if idx == 1:
                    outcome["comparison_against_adjudicated_verdicts"]["confusion_matrix"]["tp"] += 1
                path = folder / f"out{idx}.json"
                path.write_text(json.dumps(outcome))
                paths.append(path)
            with self.assertRaisesRegex(ValueError, "confusion matrix conflicts"):
                aggregate_domain_reports(paths)

    def test_rejects_unverified_or_single_report(self):
        with self.assertRaisesRegex(ValueError, "between 2"):
            aggregate_domain_reports([])
        with tempfile.TemporaryDirectory() as root:
            a, b = Path(root) / "a.json", Path(root) / "b.json"
            a.write_text(json.dumps({"status": "DRAFT"}))
            b.write_text(json.dumps({"status": "DRAFT"}))
            with self.assertRaisesRegex(ValueError, "accepted blinded"):
                aggregate_domain_reports([a, b])


if __name__ == "__main__":
    unittest.main()
