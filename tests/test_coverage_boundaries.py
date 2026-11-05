"""Boundary and failure-path regression tests for production Python modules.

Each test targets an observable input/error contract; mock-only tests force rare
OS, package-discovery or floating-point failures that cannot be reproduced
reliably on ordinary supported test hosts.
"""
import io
import json
import os
import tempfile
import unittest
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sra import checks, document, graph, model_client, provenance, report, stats
from sra.audit import audit_file


MANUSCRIPT = (
    "# Methods\nThis observational cohort included patients.\n"
    "# Results\nThe intervention increased recovery by five units.\n"
    "# Conclusion\nThe intervention increased recovery by five units."
)


def manuscript_report():
    folder = tempfile.TemporaryDirectory()
    path = Path(folder.name) / "paper.md"
    path.write_text(MANUSCRIPT, encoding="utf-8")
    return folder, audit_file(path)


def welch_spec():
    return {
        "test": "welch_t",
        "group_a": {"mean": 2.0, "sd": 1.0, "n": 20},
        "group_b": {"mean": 1.0, "sd": 2.0, "n": 25},
    }


class StatisticsBoundaryTests(unittest.TestCase):
    def test_value_validation_rejects_unrepresentable_and_unsupported_values(self):
        class ExplodingDecimal(Decimal):
            def __float__(self):
                raise OverflowError("synthetic float conversion failure")

        for value in (True, None, "2"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "must be a number"):
                stats._finite_number(value, "value")
        with self.assertRaisesRegex(ValueError, "supported numeric range"):
            stats._finite_number(ExplodingDecimal("2"), "value")
        with self.assertRaisesRegex(ValueError, "must be finite"):
            stats._finite_number(float("inf"), "value")
        for group in ({}, "not an object"):
            with self.subTest(group=group), self.assertRaises(ValueError):
                stats._group({"group_a": group}, "group_a")
        with self.assertRaisesRegex(ValueError, ">= 0"):
            stats._group({"group_a": {"mean": 0, "sd": -1, "n": 2}}, "group_a")

    def test_precision_parsing_rejects_nonfinite_invalid_exponent_and_bad_decimal(self):
        class FakeExponentDecimal(Decimal):
            def as_tuple(self):
                return SimpleNamespace(exponent="bad")

        with self.assertRaisesRegex(ValueError, "must be finite"):
            stats._display_precision_tolerance(Decimal("NaN"))
        with self.assertRaisesRegex(ValueError, "invalid decimal exponent"):
            stats._display_precision_tolerance(FakeExponentDecimal("1.2"))
        with self.assertRaisesRegex(ValueError, "precision exceeds"):
            stats._display_precision_tolerance("bad numeric precision")

    def test_report_value_normalization_handles_nested_json_and_rejects_objects(self):
        with self.assertRaisesRegex(ValueError, "must be finite"):
            stats._json_safe_report_value(Decimal("Infinity"), "other")
        with self.assertRaisesRegex(ValueError, "JSON-compatible"):
            stats._json_safe_report_value(set(), "other")
        normal = stats._json_safe_report_value(
            {"array": [1.25, 2, "x", True, None]}, "other"
        )
        self.assertEqual(normal, {"array": [1.25, 2, "x", True, None]})
        with self.assertRaisesRegex(ValueError, "p_two_sided"):
            stats._compare_reported({"p_two_sided": 0.5}, {"p_two_sided": 0}, {})
        with self.assertRaisesRegex(ValueError, "p_two_sided"):
            invalid = welch_spec()
            invalid["reported"] = {"p_two_sided": 0}
            stats.verify_welch_t_test(invalid)

    def test_hedges_correction_checks_bounds_and_math_failure(self):
        with self.assertRaisesRegex(ValueError, ">= 2"):
            stats._hedges_correction(1)
        with patch("sra.stats.math.exp", side_effect=OverflowError):
            with self.assertRaisesRegex(ValueError, "numeric range"):
                stats._hedges_correction(4)
        with patch("sra.stats.math.exp", return_value=1.25):
            with self.assertRaisesRegex(ValueError, "interval"):
                stats._hedges_correction(4)

    def test_welch_rejects_invalid_and_nonfinite_inputs(self):
        wrong = welch_spec()
        wrong["test"] = "unsupported"
        with self.assertRaisesRegex(ValueError, "Only test"):
            stats.verify_welch_t_test(wrong)
        zero = welch_spec()
        zero["group_a"]["sd"] = 0
        zero["group_b"]["sd"] = 0
        with self.assertRaisesRegex(ValueError, "zero standard error"):
            stats.verify_welch_t_test(zero)
        bad = welch_spec()
        bad["group_b"].update(sd=5e-324, n=1000)
        with self.assertRaisesRegex(ValueError, "group_b standard-error contribution"):
            stats.verify_welch_t_test(bad)
        tiny = welch_spec()
        tiny["group_a"]["mean"] = 5e-324
        tiny["group_b"]["mean"] = 0
        tiny["group_a"]["sd"] = 1000
        tiny["group_b"]["sd"] = 1000
        with self.assertRaisesRegex(ValueError, "Welch t statistic underflowed"):
            stats.verify_welch_t_test(tiny)

    def test_welch_validates_tolerance_and_reported_type(self):
        for field, bad in (("tolerances", []), ("reported", [])):
            spec = welch_spec()
            spec[field] = bad
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "must be an object"):
                stats.verify_welch_t_test(spec)
        spec = welch_spec()
        spec["tolerances"] = {"default": -0.1}
        with self.assertRaisesRegex(ValueError, "non-negative"):
            stats.verify_welch_t_test(spec)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stats.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "JSON object"):
                stats.verify_stats_file(path)

    def test_scipy_missing_is_reported(self):
        with patch.dict("sys.modules", {"scipy": None}):
            with self.assertRaisesRegex(RuntimeError, "require SciPy"):
                stats.verify_welch_t_test(welch_spec())

    def test_rare_numeric_failures_fail_closed(self):
        baseline = stats._finite_result
        def zero_denominator(value, field):
            return 0.0 if field == "Welch-Satterthwaite denominator" else baseline(value, field)
        def negative_df(value, field):
            return -1.0 if field == "Welch-Satterthwaite degrees of freedom" else baseline(value, field)
        def zero_pooled(value, field):
            return 0.0 if field == "pooled standard deviation" else baseline(value, field)
        def zero_d(value, field):
            return 0.0 if field == "pooled Cohen's d" else baseline(value, field)
        def zero_g(value, field):
            return 0.0 if field == "Hedges' g" else baseline(value, field)
        for transform, expected in (
            (zero_denominator, "degrees of freedom are outside"),
            (negative_df, "must be positive"),
            (zero_pooled, "pooled variance underflowed"),
            (zero_d, "Cohen's d underflowed"),
            (zero_g, "Hedges' g underflowed"),
        ):
            with self.subTest(error=expected):
                with patch("sra.stats._finite_result", side_effect=transform):
                    with self.assertRaisesRegex(ValueError, expected):
                        stats.verify_welch_t_test(welch_spec())


class DocumentBoundaryTests(unittest.TestCase):
    def test_sections_without_headers_and_with_preamble(self):
        plain = document.parse_document_text("Ordinary introductory prose.", sha256="a" * 64)
        self.assertEqual(plain.sections, {"full_text": "Ordinary introductory prose."})
        with_header = document.parse_document_text(
            "Preamble has material.\n# Methods\nData were gathered.",
            sha256="a" * 64,
        )
        self.assertEqual(with_header.sections["preamble"], "Preamble has material.")
        self.assertEqual(with_header.section_start_lines["preamble"], 1)

    def test_invalid_files_and_nonstrings_fail_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                document.load_document(Path(d) / "absent.md")
            unknown = Path(d) / "paper.bin"
            unknown.write_bytes(b"not a manuscript")
            with self.assertRaisesRegex(ValueError, "Supported formats"):
                document.load_document(unknown)
            empty = Path(d) / "empty.md"
            empty.write_text("    ")
            with self.assertRaisesRegex(ValueError, "No extractable text"):
                document.load_document(empty)
            with self.assertRaisesRegex(TypeError, "string"):
                document.parse_document_text(None, sha256="a" * 64)

    def test_pdf_dependency_absent_fails_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "paper.pdf"
            path.write_bytes(b"not used; import is intercepted")
            import builtins
            real_import = builtins.__import__
            def reject_pypdf(name, *args, **kwargs):
                if name == "pypdf":
                    raise ImportError("not available")
                return real_import(name, *args, **kwargs)
            with patch("builtins.__import__", side_effect=reject_pypdf):
                with self.assertRaisesRegex(RuntimeError, "PDF support is optional"):
                    document.load_document(path)


class GraphAndChecksBoundaryTests(unittest.TestCase):
    def test_graph_rejects_malformed_collection_types(self):
        result = graph.validate_reasoning_graph_object(None)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["invalid_schema_version"], [None])
        invalid = graph.validate_reasoning_graph(None, None, metadata="bad")
        self.assertEqual(invalid["status"], "FAIL")
        self.assertEqual(invalid["invalid_node_entries"], [-1])
        self.assertEqual(invalid["invalid_edge_entries"], [-1])
        self.assertEqual(invalid["invalid_schema_metadata"], ["metadata"])

    def test_scope_matching_and_negated_qualifiers(self):
        parts = checks._sentences("# Child heading\nThe U.S. recovered. Another result.", 2, "Results")
        self.assertEqual(len(parts), 2)
        self.assertTrue(checks._has_affirmed_direction("not only increased.", checks.INCREASE))
        self.assertTrue(checks._has_affirmed_match("not only caused.", checks.CAUSAL))
        result = {"text": "For women, glucose increased.", "line": 1}
        conclusion = {"text": "For men, glucose decreased.", "line": 2}
        self.assertEqual(checks._direction_conflicts([result], [conclusion]), [])

    def test_additional_graph_relation_for_directional_contradiction(self):
        source = (
            "# Methods\nGlucose measures were collected.\n"
            "# Results\nThe treatment increased glucose in patients.\n"
            "# Conclusion\nThe treatment decreased glucose in patients."
        )
        doc = document.parse_document_text(source, sha256="a" * 64)
        findings, candidates, relations = checks.build_findings(doc)
        self.assertTrue(any(r["relation"] == "possible_directional_contradiction" for r in relations))
        g = graph.build_reasoning_graph(doc, candidates, relations)
        self.assertTrue(any(e["relation"] == "possible_contradiction_candidate" for e in g["edges"]))


class ModelBoundaryTests(unittest.TestCase):
    def test_model_json_invalid(self):
        with self.assertRaisesRegex(ValueError, "not valid JSON"):
            model_client._extract_json_object("{not json}")

    def test_model_response_requires_valid_content_and_metadata(self):
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "unit-secret"}):
            for bad in ({"choices": []}, {"choices": [{"message": {"content": 42}}]}):
                with self.subTest(body=bad):
                    raw = json.dumps(bad).encode()
                    response = io.BytesIO(raw)
                    with patch("sra.model_client._open_api_request", return_value=nullcontext(response)):
                        with self.assertRaises(ValueError):
                            model_client.request_single_model_review(
                                {"review_mode": "single"}, "sample", model="x",
                                base_url="https://api.example.test/v1",
                                api_key_env="TEST_MODEL_KEY",
                            )

    def test_invalid_base_urls_and_model_names(self):
        for model, url, match in (
            ("", "https://example.test", "model name"),
            ("x", " https://example.test", "base_url"),
            ("x", "https://example.test:bad", "valid HTTP"),
            ("x", "ftp://example.test", "valid absolute HTTP"),
        ):
            with self.subTest(model=model, url=url):
                with self.assertRaisesRegex(ValueError, match):
                    model_client.request_single_model_review(
                        {"review_mode": "single"}, "text", model=model,
                        base_url=url,
                    )

    def test_failed_network_io_produces_redacted_error(self):
        with patch.dict(os.environ, {"TEST_MODEL_KEY": "unit-secret"}):
            with patch("sra.model_client._open_api_request", side_effect=OSError("secret network payload")):
                with self.assertRaisesRegex(RuntimeError, "request failed") as exc:
                    model_client.request_single_model_review(
                        {"review_mode": "single"}, "sample", model="x",
                        base_url="https://api.example.test/v1",
                        api_key_env="TEST_MODEL_KEY",
                    )
            self.assertNotIn("secret network payload", str(exc.exception))

    def test_response_limit_must_be_positive(self):
        with self.assertRaisesRegex(ValueError, "positive"):
            model_client._read_bounded_response(io.BytesIO(b"ok"), maximum=0)


class ProvenanceAndReportBoundaryTests(unittest.TestCase):
    def test_optional_package_missing_and_git_unavailable(self):
        with patch("sra.provenance.version", side_effect=provenance.PackageNotFoundError):
            self.assertIsNone(provenance._package_version("not-installed"))
        with patch("sra.provenance.subprocess.run", side_effect=OSError):
            self.assertEqual(provenance._source_revision(), (None, None))

    def test_source_inventory_fallback_no_files_or_unreadable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(Path, "rglob", return_value=[]):
                self.assertEqual(provenance._source_tree_sha256(root), (
                    None, provenance.INSTALLED_PACKAGE_HASH_SCOPE, []
                ))
            (root / "README.md").write_text("content")
            with patch.object(Path, "read_bytes", side_effect=OSError("permission")):
                digest, scope, inventory = provenance._source_tree_sha256(root)
            self.assertIsNone(digest)
            self.assertEqual(inventory, ["README.md"])
        with tempfile.TemporaryDirectory() as directory:
            digest, scope, inventory = provenance._source_tree_sha256(Path(directory))
            self.assertIsNotNone(digest)
            self.assertEqual(scope, provenance.INSTALLED_PACKAGE_HASH_SCOPE)
            self.assertTrue(inventory)

    def test_report_handles_absent_screening_and_detailed_review(self):
        folder, audited = manuscript_report()
        self.addCleanup(folder.cleanup)
        audited.findings = []
        audited.claim_evidence_candidates = []
        audited.reasoning_graph["validation"]["inferences_without_lexical_evidence"] = ["unmatched-inference"]
        audited.reasoning_map = [{"relation": "test", "note": "Source context"}]
        audited.semantic_review = {
            "status": "REJECTED",
            "assessment_count": 1,
            "validated_assessments": [{
                "relation": "contradicted", "confidence": 0.2, "rationale": "inconsistent",
                "missing_assumptions": ["Exchangeability"],
                "reviewer_selected_evidence_node_ids": ["evidence1"],
            }],
            "errors": ["invalid source"],
        }
        output = report.to_markdown(audited)
        for fragment in (
            "No configured screening signals",
            "No matching Discussion",
            "Inferences without a lexical evidence edge",
            "Source context", "Missing assumptions",
            "Reviewer-selected evidence IDs",
        ):
            self.assertIn(fragment, output)


class FinalStatementCoverageTests(unittest.TestCase):
    def test_duplicate_contradiction_inputs_are_deduplicated(self):
        result = {"text": "The treatment increased glucose.", "line": 3}
        conclusion = {"text": "The treatment decreased glucose.", "line": 5}
        conflicts = checks._direction_conflicts([result, dict(result)], [conclusion], limit=5)
        self.assertEqual(len(conflicts), 1)

    def test_association_and_causality_in_same_conclusion(self):
        source = (
            "# Methods\nAn observational cohort was followed.\n"
            "# Results\nThe exposure was associated with the measured outcome.\n"
            "# Conclusion\nThe exposure was associated with illness and caused the measured outcome."
        )
        doc = document.parse_document_text(source, sha256="a" * 64)
        findings, _, _ = checks.build_findings(doc)
        self.assertIn("reasoning.association_and_causal_claims",
                      {item.check_id for item in findings})

    def test_randomized_trial_qualified_as_unrelated_is_not_current_design(self):
        source = (
            "# Methods\nThis is an observational cohort study. "
            "We conducted a randomized trial unrelated to the current study.\n"
            "# Results\nThe intervention increased recovery.\n"
            "# Conclusion\nThe intervention caused recovery."
        )
        doc = document.parse_document_text(source, sha256="a" * 64)
        findings, _, _ = checks.build_findings(doc)
        self.assertIn("reasoning.causal_claim_observational_design",
                      {item.check_id for item in findings})

    def test_limitation_claim_lexical_relation_in_graph(self):
        source = (
            "# Methods\nThe study measured recovery.\n"
            "# Results\nThe intervention increased recovery by five units.\n"
            "# Limitations\nThe intervention increased recovery by five units.\n"
            "# Conclusion\nThe intervention increased recovery by five units."
        )
        doc = document.parse_document_text(source, sha256="a" * 64)
        findings, candidates, relations = checks.build_findings(doc)
        built = graph.build_reasoning_graph(doc, candidates, relations)
        self.assertIn(
            "qualifies_claim_candidate",
            [edge["relation"] for edge in built["edges"]]
        )

    def test_welch_wraps_sample_size_float_overflow(self):
        input_spec = welch_spec()
        input_spec["group_a"]["n"] = 10 ** 400
        with self.assertRaisesRegex(ValueError, "exceeded the supported floating-point range"):
            stats.verify_welch_t_test(input_spec)


class OptionalPdfCoverageTests(unittest.TestCase):
    def test_pdf_loader_path_with_stubbed_optional_dependency(self):
        """Keep loader coverage independent of whether the optional PDF extra is installed."""
        import sys
        from types import ModuleType

        fake_pypdf = ModuleType("pypdf")
        class Reader:
            def __init__(self, filename):
                self.pages = [
                    SimpleNamespace(extract_text=lambda: "# Results\nThe score increased."),
                    SimpleNamespace(extract_text=lambda: None),
                ]
        fake_pypdf.PdfReader = Reader
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.pdf"
            path.write_bytes(b"%PDF-fixture-for-stub-only")
            with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
                loaded = document.load_document(path)
        self.assertEqual(loaded.parser_backend, "pypdf")
        self.assertEqual(loaded.sections["Results"], "The score increased.")
