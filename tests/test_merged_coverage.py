"""Coverage for merged validation branches and in-process CLI handlers.

These tests exercise error paths and command handlers that the end-to-end
subprocess tests cannot measure under coverage instrumentation.
"""
import contextlib
import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from sra import cli
from sra.academic_benchmark import _parse_annotation, _wilson, evaluate_arxiv_edit_pairs
from sra.benchmark import _get_article, run_pmc_benchmark
from sra.discipline import reporting_cues
from sra.document import ParsedDocument, load_document
from sra.doi import (
    _NoRedirect as DoiNoRedirect,
    _lookup_crossref,
    _lookup_datacite,
    _title_context_overlap,
    normalize_doi,
    verify_dois,
)
from sra.domain_adjudication import make_domain_template, validate_domain_adjudication
from sra.domain_cohort import aggregate_domain_reports
from sra.domain_evidence import audit_domain_file
from sra.grammar_engine import (
    _NoRedirect as GrammarNoRedirect,
    _prepare_prose,
    check_local_languagetool,
)
from sra.provenance import _source_revision
from sra.stats_extended import _valid_probability, verify_extended_stats
from sra.validation import evaluate_blinded_labels
from sra.writing import audit_academic_writing
from sra.writing_style import style_review

ROOT = Path(__file__).resolve().parents[1]
TEXT = (
    "# Methods\nThis observational cohort included patients.\n"
    "# Results\nThe intervention increased recovery by five units.\n"
    "# Conclusion\nThe intervention increased recovery by five units."
)


def _document(text: str, sections: dict[str, str] | None = None) -> ParsedDocument:
    return ParsedDocument(
        source="<test>",
        text=text,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        sections=sections if sections is not None else {"Excerpt": text},
        section_start_lines={name: 1 for name in (sections or {"Excerpt": text})},
        input_format="test",
        source_size_bytes=len(text.encode("utf-8")),
        parser_backend="test",
    )


class _Response:
    def __init__(self, body: bytes = b"", status: int = 200):
        self.body = body
        self.status = status

    def read(self, _size: int = -1) -> bytes:
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return None


class _Opener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def open(self, *_args, **_kwargs):
        if self.error is not None:
            raise self.error
        return self.response


class _ReportedValidationTests(unittest.TestCase):
    def test_wilson_returns_none_for_empty_denominator(self):
        self.assertIsNone(_wilson(0, 0))

    def test_annotation_size_and_shape_errors(self):
        cases = {
            "too_long": "x" * 25_001,
            "not_dict": "[1]",
            "too_many": repr({str(index): {"intention": "Lang-x"} for index in range(201)}),
            "edit_not_dict": repr({"e": 5}),
            "intention_not_string": repr({"e": {"intention": 5}}),
        }
        for name, cell in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    _parse_annotation(cell)

    def test_annotation_none_intention_is_skipped(self):
        self.assertEqual(
            _parse_annotation(repr({"a": {"intention": None}, "b": {"intention": "Content"}})),
            ["Content"],
        )


class _AcademicBenchmarkCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def _row(self, sample_id="1", source="This are a test sentence.",
             target="This is a test sentence.", paper="2401.00001",
             intention="Lang-grammar"):
        return {
            "id": sample_id, "sentence-1": source, "sentence-2": target,
            "arxiv-id": paper,
            "edits-combination-0": repr({"e": {"intention": intention}}),
            "edits-combination-1": "{}",
            "edits-combination-2": "{}",
        }

    def _write(self, rows, name="corpus.csv"):
        path = self.root / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(self._row()))
            writer.writeheader()
            writer.writerows(rows)
        return path

    def _evaluate(self, path, **kwargs):
        return evaluate_arxiv_edit_pairs(path, max_rows=10, **kwargs)

    def test_empty_and_oversized_corpora_are_rejected(self):
        empty = self.root / "empty.csv"
        empty.write_bytes(b"")
        with self.assertRaisesRegex(ValueError, "nonempty"):
            self._evaluate(empty)
        huge = self.root / "huge.csv"
        huge.write_bytes(b"x" * 10_000_001)
        with self.assertRaisesRegex(ValueError, "10 MB"):
            self._evaluate(huge)

    def test_malformed_missing_and_long_rows_are_rejected(self):
        malformed = self.root / "malformed.csv"
        malformed.write_text(
            ",".join(list(self._row()) + ["extra"]) + "\n" + "x" * 5 + ","
            + ",".join(["1", "a", "b", "p", "{}", "{}", "{}", "unexpected"]) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "Malformed CSV row"):
            self._evaluate(malformed)
        for name, kwargs, message in (
            ("missing", {"paper": "   "}, "Missing revision"),
            ("long", {"source": "x" * 10_001}, "Unreasonably long"),
        ):
            path = self._write([self._row(**kwargs)], name + ".csv")
            with self.assertRaisesRegex(ValueError, message):
                self._evaluate(path)

    def test_empty_and_single_class_corpora_are_rejected(self):
        header_only = self._write([], "header.csv")
        with self.assertRaisesRegex(ValueError, "No annotated examples"):
            self._evaluate(header_only)
        positives = self._write([self._row()], "positive.csv")
        with self.assertRaisesRegex(ValueError, "both language-tagged"):
            self._evaluate(positives)

    def test_excessive_suggestions_are_rejected(self):
        path = self._write([self._row()], "suggestions.csv")
        with patch(
            "sra.academic_benchmark.style_review",
            return_value=[{"code": "x", "suggestion": "a", "excerpt": "b"}] * 51,
        ):
            with self.assertRaisesRegex(ValueError, "Excessive suggestions"):
                self._evaluate(path)

    def test_excluded_and_empty_suggestions_are_skipped(self):
        corpus = self._write([
            self._row(),
            self._row(sample_id="2", intention="Content"),
        ], "two.csv")
        suggestions = [
            {"code": "long_line", "suggestion": "a", "excerpt": "b"},
            {"code": "other", "suggestion": "", "excerpt": ""},
        ]
        with patch("sra.academic_benchmark.style_review", side_effect=[[], suggestions]):
            result = self._evaluate(corpus)
        self.assertEqual(
            result["confusion_matrix_against_revision_intents"],
            {"tp": 0, "fp_proxy": 1, "fn": 1, "tn_proxy": 0},
        )
        self.assertEqual(result["suggested_replacements"]["machine_string_substitution_candidates"], 0)
        self.assertEqual(result["rule_trigger_counts"], {"long_line": 1, "other": 1})


class _BenchmarkCoverageTests(unittest.TestCase):
    def _response(self, body: bytes):
        response = Mock()
        response.read.return_value = body
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=None)
        return response

    def test_bioc_oversize_and_empty_payloads_are_rejected(self):
        with patch("sra.benchmark.urlopen", return_value=self._response(b"x" * 6_000_001)):
            with self.assertRaisesRegex(ValueError, "6 MB"):
                _get_article("PMC1234567")
        for payload in (b"{}", b"[]"):
            with patch("sra.benchmark.urlopen", return_value=self._response(payload)):
                with self.assertRaises(ValueError):
                    _get_article("PMC1234567")

    def test_non_dict_and_title_passages_are_skipped(self):
        passages = [
            {"infons": {"article-id_pmc": "PMC1234567", "article-id_doi": "10.1000/x"},
             "text": "Article title", "type": "title"},
            5,
            {"infons": {"section_type": "METHODS", "type": "title"}, "text": "Title"},
        ]
        for section in ("INTRO", "METHODS", "RESULTS", "CONCL"):
            passages.append({"infons": {"section_type": section}, "text": "Body evidence.", "type": "paragraph"})
        body = json.dumps([{"documents": [{"passages": passages}]}]).encode()
        with patch("sra.benchmark.urlopen", return_value=self._response(body)):
            text, metadata = _get_article("PMC1234567")
        self.assertNotIn("Title", text)
        self.assertNotIn("Article title", text)
        self.assertIn("# Methods", text)
        self.assertEqual(metadata["title"], "Article title")

    def test_run_pmc_rejects_invalid_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps({"pmcids": ["PMC1234567"]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "limit"):
                run_pmc_benchmark(manifest, online=True, limit=0)

    def test_run_pmc_sleeps_between_multiple_articles(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(
                json.dumps({"pmcids": ["PMC1234567", "PMC7654321"]}), encoding="utf-8"
            )
            text = (
                "# Methods\nA randomized study measured outcomes.\n"
                "# Results\nThe value increased.\n# Conclusion\nThe value increased.\n"
            )
            with patch("sra.benchmark._get_article", return_value=(text, {"pmcid": "PMC1234567"})):
                # Replace the module reference rather than ``time.sleep`` on the
                # shared module: that patch is global, so any unrelated sleep in
                # the audit path was counted as the benchmark's pause and the
                # assertion read "called 2 times" on a busy runner.
                clock = Mock()
                with patch("sra.benchmark.time", clock):
                    result = run_pmc_benchmark(manifest, online=True, limit=2)
        self.assertEqual(result["processed"], 2)
        clock.sleep.assert_called_once_with(0.38)


class _DoiCoverageTests(unittest.TestCase):
    def test_redirect_handler_and_normalization_edges(self):
        self.assertIsNone(DoiNoRedirect().redirect_request(None, None, 302, "", {}, "http://x"))
        self.assertEqual(normalize_doi("10.1234/abc)"), "10.1234/abc")
        self.assertIsNone(normalize_doi("10.1234/abç"))

    def test_crossref_branches(self):
        with self.assertRaisesRegex(ValueError, "timeout"):
            _lookup_crossref("10.1234/x", timeout=0.1)
        with patch("sra.doi.build_opener", return_value=_Opener(_Response(b"", 500))):
            result = _lookup_crossref("10.1234/x")
        self.assertEqual(result["status"], "UNVERIFIED")
        with patch(
            "sra.doi.build_opener",
            return_value=_Opener(_Response(json.dumps({"message": []}).encode())),
        ):
            result = _lookup_crossref("10.1234/x")
        self.assertEqual(result["status"], "UNVERIFIED")
        error = HTTPError("http://x", 500, "server error", None, None)
        with patch("sra.doi.build_opener", return_value=_Opener(error=error)):
            result = _lookup_crossref("10.1234/x")
        self.assertEqual(result["status"], "UNVERIFIED")
        with patch("sra.doi.build_opener", return_value=_Opener(error=error)):
            result = _lookup_datacite("10.1234/x")
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_title_overlap_without_title_and_invalid_online_flag(self):
        self.assertEqual(_title_context_overlap(None, "Reference text", "10.1/x")["status"], "NOT_EVALUATED")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.md"
            path.write_text("A DOI: 10.1234/abc.\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "boolean"):
                verify_dois(path, online="yes")


class _DomainCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def _document(self, name="paper.md", text=TEXT) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def _completed(self, path: Path) -> dict:
        template = make_domain_template(load_document(path), "physics")
        for item in template["assessments"]:
            item["reviewer_assessments"] = [
                {
                    "reviewer_id": reviewer,
                    "verdict": "not_applicable",
                    "rationale": "This test double records a structural non-applicability decision.",
                    "source_quote": None,
                }
                for reviewer in ("test-double-A", "test-double-B")
            ]
            item["adjudicated_verdict"] = "not_applicable"
            item["adjudication_rationale"] = (
                "This test checks structural completeness rather than scientific content."
            )
        return template

    def test_domain_cli_commands_in_process(self):
        path = self._document()
        template_path = self.root / "template.json"
        review_path = self.root / "domain.json"
        completed_path = self.root / "completed.json"
        result_path = self.root / "validated.json"
        with patch.object(sys, "argv", ["sra", "domain-template", str(path), "--discipline", "physics", "--out", str(template_path)]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 0)
        completed = json.loads(template_path.read_text(encoding="utf-8"))
        for item in completed["assessments"]:
            item["reviewer_assessments"] = [
                {
                    "reviewer_id": reviewer, "verdict": "not_applicable",
                    "rationale": "This test double records a structural non-applicability decision.",
                    "source_quote": None,
                }
                for reviewer in ("test-double-A", "test-double-B")
            ]
            item["adjudicated_verdict"] = "not_applicable"
            item["adjudication_rationale"] = "This test checks structural completeness rather than scientific content."
        completed_path.write_text(json.dumps(completed), encoding="utf-8")
        with patch.object(sys, "argv", ["sra", "domain-review", str(path), "--discipline", "physics", "--out", str(review_path)]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 0)
        with patch.object(sys, "argv", ["sra", "domain-validate", str(path), str(completed_path), "--discipline", "physics", "--out", str(result_path)]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 0)
        self.assertEqual(json.loads(result_path.read_text())["status"], "STRUCTURALLY_ACCEPTED_FOR_EXPERT_OVERSIGHT")

    def test_domain_adjudication_validation_errors(self):
        path = self._document()
        document = load_document(path)
        valid = self._completed(path)
        cases = []
        cases.append(([], "JSON object"))
        mutated = json.loads(json.dumps(valid)); mutated["assessments"] = {}; cases.append((mutated, "must be a list"))
        mutated = json.loads(json.dumps(valid)); mutated["assessments"][0]["adjudicated_verdict"] = "invalid"; cases.append((mutated, "adjudicated verdict"))
        mutated = json.loads(json.dumps(valid)); mutated["assessments"][0]["reviewer_assessments"] = [None, valid["assessments"][0]["reviewer_assessments"][0]]; cases.append((mutated, "must be an object"))
        mutated = json.loads(json.dumps(valid)); mutated["assessments"][0]["reviewer_assessments"][0] = {}; cases.append((mutated, "reviewer_id"))
        mutated = json.loads(json.dumps(valid)); mutated["assessments"][0]["reviewer_assessments"][0]["verdict"] = "not_reported"; mutated["assessments"][0]["reviewer_assessments"][0]["source_quote"] = "absent quotation"; cases.append((mutated, "absent from manuscript"))
        for completed, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_domain_adjudication(document, "physics", completed)

    def test_domain_cohort_validation_errors(self):
        first = self._document("a.md")
        second = self._document("b.md", TEXT + "\n# Limitations\nThe sample was small.\n")
        reports = []
        for path in (first, second):
            completed = self._completed(path)
            reports.append(validate_domain_adjudication(load_document(path), "physics", completed))
        paths = []
        for index, report in enumerate(reports):
            path = self.root / f"report-{index}.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            paths.append(path)
        self.assertEqual(aggregate_domain_reports(paths)["manuscripts"], 2)

        oversized = self.root / "oversized.json"
        oversized.write_bytes(b"{" + b"x" * 2_000_001)
        with self.assertRaisesRegex(ValueError, "2 MB"):
            aggregate_domain_reports([oversized, paths[1]])

        mutations = []
        mutated = json.loads(json.dumps(reports[0])); mutated["source_sha256"] = "short"; mutations.append((mutated, "Missing report"))
        mutated = json.loads(json.dumps(reports[0])); mutated["reviewer_agreement"] = None; mutations.append((mutated, "Missing reviewer"))
        mutated = json.loads(json.dumps(reports[0])); mutated["reviewer_agreement"]["rule_count"] = 0; mutations.append((mutated, "Malformed per-rule"))
        mutated = json.loads(json.dumps(reports[0])); mutated["comparison_against_adjudicated_verdicts"]["per_rule"][0] = 5; mutations.append((mutated, "Malformed domain per-rule"))
        mutated = json.loads(json.dumps(reports[0])); mutated["comparison_against_adjudicated_verdicts"]["per_rule"][0]["outcome"] = "bogus"; mutations.append((mutated, "Repeated/invalid"))
        for index, (mutated, message) in enumerate(mutations):
            bad = self.root / f"bad-{index}.json"
            bad.write_text(json.dumps(mutated), encoding="utf-8")
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    aggregate_domain_reports([bad, paths[1]])

    def test_domain_aggregate_cli_in_process(self):
        first = self._document("c.md")
        second = self._document("d.md", TEXT + "\n# Limitations\nThe sample was small.\n")
        report_paths = []
        for index, path in enumerate((first, second)):
            report = validate_domain_adjudication(load_document(path), "physics", self._completed(path))
            report_path = self.root / f"cli-report-{index}.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            report_paths.append(report_path)
        output = self.root / "cohort.json"
        with patch.object(sys, "argv", ["sra", "domain-aggregate", *map(str, report_paths), "--out", str(output)]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(), 0)
        self.assertEqual(json.loads(output.read_text())["manuscripts"], 2)

    def test_domain_evidence_wrapper(self):
        path = self._document()
        self.assertEqual(audit_domain_file(str(path), "physics")["discipline"], "physics")

    def test_reporting_cues_reject_unknown_design(self):
        with self.assertRaisesRegex(ValueError, "design must be"):
            reporting_cues(_document_object(TEXT), "bogus")


def _document_object(text: str) -> ParsedDocument:
    return _document(text)


class _GrammarCoverageTests(unittest.TestCase):
    def _run(self, payload: dict | bytes, text: str = "This are test.", sections=None):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        with patch("sra.grammar_engine.build_opener", return_value=_Opener(_Response(body))):
            return check_local_languagetool(_document(text, sections), language="en")

    def test_redirect_handler_and_prepare_prose_separator(self):
        self.assertIsNone(GrammarNoRedirect().redirect_request(None, None, 302, "", {}, "http://x"))
        prepared, spans = _prepare_prose(
            _document("First.\nSecond.", {"First": "First.", "Second": "Second."}), set()
        )
        self.assertIn("\n\n", prepared)
        self.assertEqual(len(spans), 2)

    def test_empty_prose_returns_no_suggestions(self):
        self.assertEqual(check_local_languagetool(_document("   "), language="en"), [])

    def test_response_size_json_and_structure_errors(self):
        for payload, message in (
            (b"x" * 3_000_001, "3 MB"),
            (b"not json", "not valid JSON"),
            (b"[]", "unexpected structure"),
            ({"matches": [{}] * 1501}, "too many matches"),
            ({"matches": [5]}, "malformed match"),
        ):
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self._run(payload)

    def test_match_field_errors(self):
        base = {"offset": 0, "length": 4, "replacements": [], "rule": {"id": "R"}, "message": "m"}
        cases = []
        cases.append((dict(base, replacements="x"), "replacements must be a list"))
        cases.append((dict(base, rule="x"), "rule information is malformed"))
        cases.append((dict(base, rule={"id": 5}), "rule ID is invalid"))
        for hit, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    self._run({"matches": [hit]})

    def test_separator_span_and_duplicate_and_nonstring_message(self):
        sections = {"First": "A", "Second": "B"}
        hit = {"offset": 1, "length": 1, "replacements": [], "rule": {"id": "R"}, "message": 5}
        self.assertEqual(self._run({"matches": [hit]}, text="A\n\nB", sections=sections), [])
        duplicate = {"offset": 0, "length": 4, "replacements": [], "rule": {"id": "R"}, "message": 5}
        result = self._run({"matches": [duplicate, dict(duplicate)]})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["message"], "Local grammar suggestion")


class _ProvenanceAndStyleCoverageTests(unittest.TestCase):
    def test_source_revision_reads_git_when_available(self):
        with patch("sra.provenance.subprocess.run", side_effect=[
            Mock(stdout="abc123\n"), Mock(stdout=" M file\n"),
        ]):
            self.assertEqual(_source_revision(), ("abc123", True))

    def test_style_and_writing_validation_errors(self):
        document = _document("A sentence.")
        with self.assertRaisesRegex(ValueError, "long_sentence_words"):
            style_review(document, long_sentence_words=9)
        with self.assertRaisesRegex(ValueError, "Unsupported discipline"):
            audit_academic_writing(ROOT / "examples" / "academic_writing_sample.md", discipline="bogus")
        with self.assertRaisesRegex(ValueError, "grammar_engine"):
            audit_academic_writing(ROOT / "examples" / "academic_writing_sample.md", grammar_engine="bogus")


class _StatsAndValidationCoverageTests(unittest.TestCase):
    def test_extended_statistics_validation_errors(self):
        base = {"test": "one_sample_t", "sample": {"mean": 1, "sd": 1, "n": 10}}
        with self.assertRaisesRegex(ValueError, "tolerances"):
            verify_extended_stats(dict(base, tolerances=[]))
        with self.assertRaisesRegex(ValueError, "reported"):
            verify_extended_stats(dict(base, reported=[]))
        with self.assertRaisesRegex(ValueError, "p_two_sided"):
            verify_extended_stats(dict(base, reported={"p_two_sided": 0}))
        with self.assertRaisesRegex(ValueError, "must be an object"):
            verify_extended_stats([])
        with self.assertRaisesRegex(ValueError, "exact float integer precision"):
            verify_extended_stats({"test": "chi_square_2x2", "table": [[2**53, 1], [1, 1]]})
        with self.assertRaisesRegex(ValueError, "0, 1"):
            _valid_probability(0)
        with self.assertRaisesRegex(ValueError, "Standard error underflowed"):
            verify_extended_stats({
                "test": "one_sample_t", "sample": {"mean": 1, "sd": 5e-324, "n": 1000},
            })
        with self.assertRaisesRegex(ValueError, "t statistic underflowed"):
            verify_extended_stats({
                "test": "one_sample_t", "sample": {"mean": 5e-324, "sd": 1e308, "n": 4},
            })

    def test_scipy_import_error_is_reported(self):
        with patch.dict(sys.modules, {"scipy": None}):
            with self.assertRaisesRegex(RuntimeError, "requires SciPy"):
                verify_extended_stats({"test": "one_sample_t", "sample": {"mean": 1, "sd": 1, "n": 4}})

    def _fixtures(self, root: Path):
        benchmark = {
            "kind": "unlabeled_real_paper_smoke_test",
            "paper_results": [{
                "pmcid": "PMC1234567", "status": "PROCESSED",
                "response_sha256": "a" * 64, "writing_finding_codes": ["code"],
            }],
        }
        labels = {
            "finding_codes": ["code"],
            "cases": [{
                "pmcid": "PMC1234567", "code": "code", "source_sha256": "a" * 64,
                "expert_label": True, "reviewer_ids": ["a", "b"], "adjudicated": True,
            }],
        }
        benchmark_path = root / "benchmark.json"
        labels_path = root / "labels.json"
        benchmark_path.write_text(json.dumps(benchmark), encoding="utf-8")
        labels_path.write_text(json.dumps(labels), encoding="utf-8")
        return benchmark_path, labels_path, benchmark, labels

    def test_blinded_label_validation_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            benchmark_path, labels_path, benchmark, labels = self._fixtures(root)
            mutations = [
                ({**benchmark, "kind": "wrong"}, labels, "smoke-test report"),
                ({**benchmark, "paper_results": "x"}, labels, "list of objects"),
                (benchmark, {**labels, "finding_codes": []}, "finding_codes"),
                (benchmark, {**labels, "cases": {}}, "cases must be a list"),
                (benchmark, {**labels, "cases": [5]}, "Every case must be an object"),
            ]
            for index, (bad_benchmark, bad_labels, message) in enumerate(mutations):
                with self.subTest(message=message):
                    benchmark_path.write_text(json.dumps(bad_benchmark), encoding="utf-8")
                    labels_path.write_text(json.dumps(bad_labels), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, message):
                        evaluate_blinded_labels(benchmark_path, labels_path)
            missing_codes = json.loads(json.dumps(benchmark))
            del missing_codes["paper_results"][0]["writing_finding_codes"]
            benchmark_path.write_text(json.dumps(missing_codes), encoding="utf-8")
            labels_path.write_text(json.dumps(labels), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "writing_finding_codes"):
                evaluate_blinded_labels(benchmark_path, labels_path)


class _CliHandlerCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def call(self, *args, expected=0):
        captured = io.StringIO()
        with patch.object(sys, "argv", ["sra", *map(str, args)]):
            with contextlib.redirect_stdout(captured):
                self.assertEqual(cli.main(), expected)
        return captured.getvalue()

    def call_error(self, *args, message):
        with patch.object(sys, "argv", ["sra", *map(str, args)]):
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(io.StringIO()) as errors:
                    with self.assertRaises(SystemExit) as exit_code:
                        cli.main()
        self.assertEqual(exit_code.exception.code, 2)
        self.assertIn(message, errors.getvalue())

    def test_cli_error_paths(self):
        missing = self.root / "missing.json"
        patches = (
            ("benchmark-language", "sra.cli.evaluate_arxiv_edit_pairs", (
                "benchmark-language", missing, "--expected-sha256", "a" * 64,
                "--out", self.root / "language.json",
            )),
            ("domain-aggregate", "sra.cli.aggregate_domain_reports", (
                "domain-aggregate", missing, "--out", self.root / "cohort.json",
            )),
            ("domain-review", "sra.cli.audit_domain_file", (
                "domain-review", missing, "--discipline", "clinical",
                "--out", self.root / "domain.json",
            )),
            ("writing-audit", "sra.cli.audit_academic_writing", (
                "writing-audit", missing, "--out", self.root / "writing",
            )),
            ("doi-check", "sra.cli.verify_dois", (
                "doi-check", missing, "--out", self.root / "doi.json",
            )),
            ("benchmark-pmc", "sra.cli.run_pmc_benchmark", (
                "benchmark-pmc", missing, "--out", self.root / "pmc.json",
            )),
            ("evaluate-labels", "sra.cli.evaluate_blinded_labels", (
                "evaluate-labels", missing, missing, "--out", self.root / "labels.json",
            )),
        )
        for name, target, arguments in patches:
            with self.subTest(command=name):
                with patch(target, side_effect=ValueError("synthetic failure")):
                    self.call_error(*arguments, message="synthetic failure")

    def test_cli_overwrite_guards(self):
        source = self.root / "manuscript.md"
        source.write_text(TEXT, encoding="utf-8")
        language = {"rows_evaluated": 2, "unique_papers": 1,
                    "conditional_detection": {"positive_recall": 0.5}}
        with patch("sra.cli.evaluate_arxiv_edit_pairs", return_value=language):
            self.call_error(
                "benchmark-language", source, "--expected-sha256", "a" * 64,
                "--out", source, message="must not overwrite",
            )
        with patch("sra.cli.aggregate_domain_reports", return_value={"manuscripts": 2}):
            self.call_error(
                "domain-aggregate", source, "--out", source, message="must not overwrite",
            )
        with patch("sra.cli.audit_academic_writing", return_value={
            "findings": [], "style_suggestions": [], "grammar_suggestions": [],
        }):
            self.call_error(
                "writing-audit", source, "--out", source.with_suffix(""),
                message="must not overwrite",
            )
        with patch("sra.cli.audit_domain_file", return_value={}):
            self.call_error(
                "domain-review", source, "--discipline", "clinical",
                "--out", source, message="must not overwrite",
            )
        with patch("sra.cli.verify_dois", return_value={"found_count": 0, "checked_count": 0}):
            self.call_error(
                "doi-check", source, "--out", source, message="must not overwrite",
            )
        with patch("sra.cli.run_pmc_benchmark", return_value={
            "processed": 0, "failed": 0, "total_requested": 0,
        }):
            self.call_error(
                "benchmark-pmc", source, "--out", source, message="must not overwrite",
            )
        with patch("sra.cli.evaluate_blinded_labels", return_value={"labelled_units": 0}):
            self.call_error(
                "evaluate-labels", source, source, "--out", source,
                message="must not overwrite",
            )

    def test_writing_audit_prints_discipline_summary(self):
        source = self.root / "manuscript.md"
        source.write_text(TEXT, encoding="utf-8")
        result = {
            "findings": [], "style_suggestions": [], "grammar_suggestions": [],
            "discipline_review": {"items": [{"status": "x"}]},
        }
        with patch("sra.cli.audit_academic_writing", return_value=result):
            with patch("sra.cli.writing_report_markdown", return_value="# report"):
                output = self.call(
                    "writing-audit", source, "--out", self.root / "writing",
                )
        self.assertIn("Domain evidence items: 1", output)

    def test_writing_and_doi_handlers(self):
        self.call(
            "writing-audit", ROOT / "examples" / "academic_writing_sample.md",
            "--genre", "original-research", "--out", self.root / "writing",
        )
        self.assertTrue((self.root / "writing.json").is_file())
        self.call(
            "doi-check", ROOT / "examples" / "doi_metadata_demo.md",
            "--out", self.root / "doi.json",
        )
        self.assertTrue((self.root / "doi.json").is_file())

    def test_benchmark_language_handler(self):
        path = self.root / "corpus.csv"
        rows = []
        for index, intention in enumerate(("Lang-grammar", "Content-add"), 1):
            rows.append({
                "id": str(index), "sentence-1": "This are a test sentence.",
                "sentence-2": "This is a test sentence.", "arxiv-id": "2401.00001",
                "edits-combination-0": repr({"e": {"intention": intention}}),
                "edits-combination-1": "{}", "edits-combination-2": "{}",
            })
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        out = self.root / "language.json"
        self.call(
            "benchmark-language", path, "--expected-sha256", sha,
            "--max-rows", "10", "--out", out,
        )
        self.assertEqual(json.loads(out.read_text())["rows_evaluated"], 2)

    def test_pmc_and_labels_handlers(self):
        manifest = self.root / "manifest.json"
        manifest.write_text(json.dumps({"pmcids": ["PMC1234567"]}), encoding="utf-8")
        with patch("sra.cli.run_pmc_benchmark", return_value={"processed": 1, "failed": 0, "total_requested": 1}):
            self.call("benchmark-pmc", manifest, "--online", "--out", self.root / "pmc.json")
        self.assertTrue((self.root / "pmc.json").is_file())
        benchmark = self.root / "benchmark.json"
        labels = self.root / "labels.json"
        benchmark.write_text(json.dumps({
            "kind": "unlabeled_real_paper_smoke_test",
            "paper_results": [{
                "pmcid": "PMC1234567", "status": "PROCESSED",
                "response_sha256": "a" * 64, "writing_finding_codes": ["code"],
            }],
        }), encoding="utf-8")
        labels.write_text(json.dumps({
            "finding_codes": ["code"],
            "cases": [{
                "pmcid": "PMC1234567", "code": "code", "source_sha256": "a" * 64,
                "expert_label": True, "reviewer_ids": ["a", "b"], "adjudicated": True,
            }],
        }), encoding="utf-8")
        self.call(
            "evaluate-labels", benchmark, labels, "--out", self.root / "labels-report.json",
        )
        self.assertEqual(
            json.loads((self.root / "labels-report.json").read_text())["labelled_units"], 1
        )


if __name__ == "__main__":
    unittest.main()
