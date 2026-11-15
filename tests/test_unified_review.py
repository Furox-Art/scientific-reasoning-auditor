"""Behavioral controls for source-bound, cross-disciplinary composition."""
import hashlib
import importlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class UnifiedReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.paper = Path(self.tmp.name) / "paper.md"
        self.paper.write_text(
            "# Introduction\nWe study a mathematical identity.\n"
            "# Proof\nThe boundary condition is fixed at zero.\n"
            "# Conclusion\nThe identity follows under the stated assumptions.\n"
            "# References\nExample doi:10.1234/example\n", encoding="utf-8")

    def api(self):
        self.assertIsNotNone(importlib.util.find_spec("sra.review"),
                             "The unified review API is not implemented")
        return importlib.import_module("sra.review")

    def test_offline_default_reports_unassessed_modules_without_network(self):
        api = self.api()
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            report = api.review_manuscript(self.paper)
        self.assertEqual(report["schema_version"], "cross-disciplinary-review/1.0")
        self.assertEqual(report["execution_status"], "complete")
        self.assertEqual(report["modules"]["model"]["status"], "not_requested")
        self.assertEqual(report["modules"]["statistics"]["status"], "not_requested")
        self.assertTrue(report["applicability"]["review_required"])
        self.assertEqual(report["modules"]["citations"]["result"]["results"][0]["status"], "NOT_CHECKED_OFFLINE")
        self.assertIn("specialist_profile_not_selected", report["coverage_gaps"])

    def test_theoretical_excludes_empirical_structure_visibly_preserving_legacy(self):
        api = self.api()
        from sra.audit import audit_file
        original = audit_file(self.paper).to_dict()
        report = api.review_manuscript(self.paper, study_type="theoretical")
        exclusions = {x["finding"]["check_id"] for x in report["excluded_findings"]}
        self.assertIn("structure.methods_missing", exclusions)
        self.assertIn("structure.results_missing", exclusions)
        included = {x["check_id"] for x in report["modules"]["reasoning"]["result"]["findings"]}
        self.assertNotIn("structure.methods_missing", included)
        self.assertEqual(original, audit_file(self.paper).to_dict() | {"reproducibility_manifest": original["reproducibility_manifest"]})

    def test_empirical_and_unknown_keep_structure_and_mixed_requests_review(self):
        api = self.api()
        for kind in ("quantitative", "qualitative", "computational", "systematic-review", "unknown", "mixed"):
            with self.subTest(kind=kind):
                report = api.review_manuscript(self.paper, study_type=kind)
                ids = {x["check_id"] for x in report["modules"]["reasoning"]["result"]["findings"]}
                self.assertIn("structure.methods_missing", ids)
                self.assertEqual(report["applicability"]["review_required"], kind in ("unknown", "mixed"))
        report = api.review_manuscript(self.paper, study_type="narrative-review")
        self.assertTrue(report["excluded_findings"])

    def test_multiple_profiles_deduplicate_and_preserve_source_identity(self):
        report = self.api().review_manuscript(self.paper, disciplines=["physics", "computing", "physics"])
        self.assertEqual(report["configuration"]["disciplines"], ["physics", "computing"])
        digest = hashlib.sha256(self.paper.read_bytes()).hexdigest()
        self.assertEqual(report["source_sha256"], digest)
        self.assertEqual(report["modules"]["discipline:physics"]["result"]["discipline"], "physics")
        for module in report["modules"].values():
            self.assertEqual(module["source_sha256"], digest)
            self.assertEqual(module["extracted_text_sha256"], report["extracted_text_sha256"])

    def test_invalid_configuration_or_specs_fail_before_network(self):
        api = self.api()
        invalid = [dict(study_type="fiction"), dict(disciplines="physics"),
                   dict(disciplines=["math"]), dict(disciplines=[{}]),
                   dict(online=1), dict(send_to_model=1), dict(model="test"),
                   dict(send_to_model=True), dict(style_language="auto"),
                   dict(statistics_spec='{"test":"welch_t","test":"paired_t"}'),
                   dict(statistics_spec='{"x":NaN}'), dict(scientific_spec="[]"),
                   dict(scientific_spec={"checks": []}),
                   dict(statistics_spec={"test": "unknown"}),
                   dict(scientific_spec=" " * (1024 * 1024 + 1)),
                   dict(timeout=0), dict(chunk_chars=1)]
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            for kwargs in invalid:
                with self.subTest(kwargs=str(kwargs)[:120]), self.assertRaises(ValueError):
                    api.review_manuscript(self.paper, **kwargs)

    def test_parse_once_even_when_original_changes_during_review(self):
        api = self.api()
        from sra.audit import audit_parsed_document
        expected = hashlib.sha256(self.paper.read_bytes()).hexdigest()
        def mutate(document):
            self.paper.write_text("completely changed", encoding="utf-8")
            return audit_parsed_document(document)
        with patch("sra.review.audit_parsed_document", side_effect=mutate):
            result = api.review_manuscript(self.paper, disciplines=["physics"])
        self.assertEqual(result["source_sha256"], expected)
        for entry in result["modules"].values():
            if entry["status"] == "completed" and "source_sha256" in entry["result"]:
                self.assertEqual(entry["result"]["source_sha256"], expected)

    def test_structured_science_and_statistics_are_arithmetic_not_quality_scores(self):
        api = self.api()
        stats = json.loads((Path(__file__).parents[1] / "examples/welch_t_example.json").read_text())
        science = json.loads((Path(__file__).parents[1] / "examples/advanced_scientific_checks.json").read_text())
        result = api.review_manuscript(self.paper, statistics_spec=stats, scientific_spec=science)
        self.assertEqual(result["modules"]["statistics"]["status"], "completed")
        self.assertEqual(result["modules"]["scientific"]["status"], "completed")
        self.assertNotIn("scientific_score", result)
        self.assertNotIn("PASS", result["execution_status"])
        self.assertIn("raw_data_not_validated", result["coverage_gaps"])

    def test_model_failure_is_partial_and_secret_not_returned(self):
        api = self.api()
        with patch("sra.review.review_parsed_paper", side_effect=RuntimeError("SECRET_KEY")):
            result = api.review_manuscript(self.paper, model="fake", send_to_model=True)
        self.assertEqual(result["execution_status"], "partial")
        self.assertEqual(result["modules"]["model"]["status"], "failed")
        self.assertNotIn("SECRET_KEY", json.dumps(result))

    def test_mismatched_model_source_is_hard_error(self):
        api = self.api()
        with patch("sra.review.review_parsed_paper", return_value={"source_sha256": "a" * 64}):
            with self.assertRaisesRegex(ValueError, "source"):
                api.review_manuscript(self.paper, model="fake", send_to_model=True)

    def test_optional_dependency_and_module_failure_remain_visible(self):
        api = self.api()
        for error, status in [(ImportError("scipy"), "unavailable"), (RuntimeError("private"), "failed")]:
            with self.subTest(status=status), patch("sra.review.review_domain", side_effect=error):
                result = api.review_manuscript(self.paper, disciplines=["physics"])
                self.assertEqual(result["execution_status"], "partial")
                self.assertEqual(result["modules"]["discipline:physics"]["status"], status)

    def test_capabilities_are_detached_and_do_not_claim_specialist_coverage(self):
        self.api()
        from sra.capabilities import capabilities
        first = capabilities()
        self.assertEqual(len(first["disciplines"]), 6)
        self.assertIn("theoretical", first["study_types"])
        first["disciplines"].clear()
        self.assertEqual(len(capabilities()["disciplines"]), 6)
        self.assertIn("fisher_exact_2x2", capabilities()["statistics_tests"])

    def test_markdown_displays_modules_exclusions_gaps_and_escapes_source(self):
        api = self.api()
        from sra.review_report import review_markdown
        report = api.review_manuscript(self.paper, study_type="theoretical")
        report["source"] = "<script>alert(1)</script>"
        rendered = review_markdown(report)
        self.assertNotIn("<script>", rendered)
        for label in ("Execution", "Coverage gaps", "Excluded", "not_requested", "structure.methods\\_missing"):
            self.assertIn(label, rendered)

    def test_model_success_uses_same_snapshot_and_renders_verified_quotes(self):
        api = self.api()
        from sra.paper_review import SYNTHESIS_FIELDS
        from sra.review_report import review_markdown
        def fake(template, manuscript, **kwargs):
            payload = kwargs["_payload_override"]
            if payload["task"] == "whole_manuscript_synthesis":
                return {key: "Advisory scientific interpretation." for key in SYNTHESIS_FIELDS}
            return {"explanation": "The assumptions describe a theoretical identity.",
                    "main_points": ["The derivation is conditional."],
                    "critiques": [{"issue": "Check the assumptions", "reason": "Their scope needs review.",
                                   "recommendation": "Inspect the complete derivation.",
                                   "severity": "low", "quote": payload["source_text"][0:35]}]}
        with patch("sra.paper_review.request_single_model_review", side_effect=fake):
            report = api.review_manuscript(self.paper, send_to_model=True, model="fake")
        self.assertEqual(report["execution_status"], "complete")
        self.assertIn("Whole-paper", review_markdown(report))
        result = report["modules"]["model"]["result"]
        self.assertEqual(result["source_sha256"], report["source_sha256"])
        self.assertEqual(result["extracted_text_coverage"], "complete")

    def test_required_reasoning_failure_cannot_produce_complete_report(self):
        api = self.api()
        with patch("sra.review.audit_parsed_document", side_effect=RuntimeError("failure")):
            with self.assertRaises(RuntimeError):
                api.review_manuscript(self.paper)

    def test_spec_bounds_and_non_json_values_and_missing_optional_dependency(self):
        api = self.api()
        huge = Path(self.tmp.name) / "huge.json"
        huge.write_text("x" * (1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            api.load_spec_file(huge)
        with self.assertRaises(ValueError):
            api.review_manuscript(self.paper, statistics_spec={"bad": {1, 2}})
        with patch("sra.review._prepare_spec", side_effect=ImportError("scipy")):
            result = api.review_manuscript(self.paper, statistics_spec={"test": "welch_t"})
        self.assertEqual(result["modules"]["statistics"]["status"], "unavailable")

    def test_pdf_coverage_gap_and_invalid_visual_configuration(self):
        api = self.api()
        from sra.document import load_document
        doc = load_document(self.paper)
        doc.extraction_details = {"pages_without_extractable_text": [2]}
        result = api.review_document(doc)
        self.assertIn("pdf_pages_without_extracted_text", result["coverage_gaps"])
        with self.assertRaises(ValueError):
            api.review_document(doc, send_to_model=True, model="fake", visual_pages=True)
        doc.input_format = "pdf"
        from sra.paper_review import review_parsed_paper
        with patch("sra.paper_review.request_single_model_review", return_value={"explanation":"ok", "main_points":[], "critiques":[]}):
            with self.assertRaisesRegex(ValueError, "snapshot"):
                review_parsed_paper(doc, model="fake", visual_pages=True)

    def test_missing_scipy_is_unavailable_instead_of_aborting_common_review(self):
        api = self.api()
        import builtins
        original = builtins.__import__
        def no_scipy(name, *args, **kwargs):
            if name == "scipy":
                raise ImportError("deliberately absent optional dependency")
            return original(name, *args, **kwargs)
        stats = (Path(__file__).parents[1] / "examples/welch_t_example.json").read_text()
        with patch("builtins.__import__", side_effect=no_scipy):
            report = api.review_manuscript(self.paper, statistics_spec=stats)
        self.assertEqual(report["modules"]["statistics"]["status"], "unavailable")
        self.assertEqual(report["execution_status"], "partial")

    def test_oversized_model_input_blocks_all_outbound_requests(self):
        api = self.api()
        from sra.document import load_document
        document = load_document(self.paper)
        document.source_size_bytes = 20 * 1024 * 1024 + 1
        with patch("sra.review.verify_document_dois", side_effect=AssertionError("outbound")):
            with self.assertRaises(ValueError):
                api.review_document(document, online=True, model="fake", send_to_model=True)

    def test_provenance_subprocess_does_not_inherit_protocol_stdin(self):
        import subprocess
        from sra.provenance import _source_revision
        from types import SimpleNamespace
        with patch("sra.provenance.subprocess.run", return_value=SimpleNamespace(stdout="")) as run:
            _source_revision()
        self.assertTrue(run.call_args_list)
        for call in run.call_args_list:
            self.assertEqual(call.kwargs.get("stdin"), subprocess.DEVNULL)

    def test_human_report_explains_profile_questions_and_preserves_structured_layout(self):
        api = self.api()
        from sra.review_report import review_markdown
        report = api.review_manuscript(self.paper, disciplines=["physics"])
        report["modules"]["extraction"]["result"]["example"] = "```</script>"
        text = review_markdown(report)
        self.assertIn("Is a measurement reported", text)
        self.assertIn("````json\n", text)
        self.assertIn("DOI metadata", text)

    def test_model_duplicate_findings_follow_the_same_applicability_policy(self):
        api = self.api()
        from sra.document import load_document
        digest = load_document(self.paper).sha256
        for study_type in ("theoretical", "narrative-review"):
            fake = {"source_sha256": digest, "rule_based_findings": [
                {"check_id": "structure.methods_missing", "title": "Missing methods"},
                {"check_id": "language.absolute_claim", "title": "Review wording"}]}
            with self.subTest(study_type=study_type), patch("sra.review.review_parsed_paper", return_value=fake):
                result = api.review_manuscript(self.paper, study_type=study_type, send_to_model=True, model="fake")
            self.assertEqual([x["check_id"] for x in result["modules"]["model"]["result"]["rule_based_findings"]], ["language.absolute_claim"])
            self.assertTrue(any(x["module"] == "model" for x in result["excluded_findings"]))

    def test_invalid_extended_statistics_with_missing_scipy_cannot_trigger_outbound_requests(self):
        api = self.api()
        from sra.stats_extended import _scipy_stats
        invalid = [{"test":"paired_t"}, {"test":"one_sample_t","sample":{"mean":1,"sd":0,"n":10}},
                   {"test":"chi_square_2x2","table":[[0,0],[1,2]]},
                   {"test":"fisher_exact_2x2","table":[[1000000,2],[3,4]]},
                   {"test":"paired_t","differences":{"mean":1,"sd":2,"n":10},"reported":{"p_two_sided":0}},
                   {"test":"two_proportion_z","table":[[4,5],[5,6]],"tolerances":{"default":-1}}]
        # Real dependency helper already wraps ImportError in RuntimeError.
        error = RuntimeError("SciPy unavailable")
        error.__cause__ = ImportError("no scipy")
        for spec in invalid:
            with self.subTest(spec=spec), patch("sra.stats_extended._scipy_stats", side_effect=error), \
                 patch("sra.review.verify_document_dois") as registry, patch("sra.review.review_parsed_paper") as model:
                with self.assertRaises(ValueError):
                    api.review_manuscript(self.paper, statistics_spec=spec, online=True,
                                          send_to_model=True, model="fake")
                registry.assert_not_called()
                model.assert_not_called()

    def test_registry_execution_failure_is_partial_while_absent_registration_is_complete(self):
        api = self.api()
        for status, expected in (("UNVERIFIED", "partial"),
                                  ("NOT_FOUND_IN_CROSSREF_OR_DATACITE", "complete"),
                                  ("REGISTERED_IN_CROSSREF", "complete")):
            with self.subTest(status=status), patch("sra.doi._lookup_registry", return_value={"status": status, "reason":"synthetic"}):
                result = api.review_manuscript(self.paper, online=True)
            self.assertEqual(result["execution_status"], expected)
            self.assertEqual(result["modules"]["citations"]["result"]["results"][0]["status"], status)
            if status == "UNVERIFIED":
                from sra.review_report import review_markdown
                self.assertIn("UNVERIFIED", review_markdown(result))

    def test_changed_visual_source_is_a_hard_error_before_external_requests(self):
        api = self.api()
        from sra.document import load_document
        document = load_document(self.paper)
        document.input_format = "pdf"
        self.paper.write_bytes(b"%PDF-1.7 changed source")
        with patch("sra.review.verify_document_dois") as registry, patch("sra.paper_review.request_single_model_review") as model:
            with self.assertRaisesRegex(ValueError, "changed|source"):
                api.review_document(document, visual_pages=True, visual_path=self.paper,
                                    online=True, send_to_model=True, model="fake")
            registry.assert_not_called()
            model.assert_not_called()

    def test_visual_source_exception_escapes_optional_failure_handler(self):
        api = self.api()
        from sra.document import SourceIdentityError
        with patch("sra.review.review_parsed_paper", side_effect=SourceIdentityError("source changed")):
            with self.assertRaises(SourceIdentityError):
                api.review_manuscript(self.paper, send_to_model=True, model="fake")

    def test_visual_review_uses_prevalidated_bytes_when_original_changes_later(self):
        api = self.api()
        from test_pdf_visual_review import fake_pdf_reader
        from sra.paper_review import SYNTHESIS_FIELDS
        pdf = Path(self.tmp.name) / "paper.pdf"
        original = b"%PDF-synthetic-unified-vision-fixture"
        pdf.write_bytes(original)
        rendered_paths = []
        def fake_model(template, manuscript, **kwargs):
            task = kwargs["_payload_override"]["task"]
            if task == "scientific_page_image_review":
                return {"page_summary": "An illustrative page.", "visual_findings": []}
            if task == "whole_manuscript_synthesis":
                return {key: "An advisory interpretation." for key in SYNTHESIS_FIELDS}
            pdf.write_bytes(b"%PDF-the-original-was-changed")
            return {"explanation": "An identity is described.", "main_points": [], "critiques": []}
        def render(path, page):
            self.assertEqual(Path(path).read_bytes(), original)
            rendered_paths.append(Path(path))
            return "data:image/jpeg;base64,AA==", "a" * 64
        with patch.dict("sys.modules", {"pypdf": fake_pdf_reader(["# Proof\nA synthetic identity follows from assumptions."])}), \
             patch("sra.paper_review.request_single_model_review", side_effect=fake_model), \
             patch("sra.paper_review.pdf_page_image_url", side_effect=render):
            report = api.review_manuscript(pdf, model="fake", send_to_model=True, visual_pages=True)
        self.assertEqual(report["execution_status"], "complete")
        self.assertEqual(report["source_sha256"], hashlib.sha256(original).hexdigest())
        self.assertTrue(rendered_paths)
        self.assertFalse(rendered_paths[0].exists())


if __name__ == "__main__":
    unittest.main()
