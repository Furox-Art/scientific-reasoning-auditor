"""Regression tests for paragraph-grounded specialties and local grammar review."""
import contextlib
import copy
import hashlib
import json
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError
from urllib.parse import parse_qs

from sra.document import load_document
from sra.domain_evidence import PROFILES, review_domain
from sra.domain_adjudication import make_domain_template, validate_domain_adjudication
from sra.grammar_engine import check_local_languagetool
from sra.writing import audit_academic_writing, writing_report_markdown


def create_document(text):
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "article.md"
        path.write_text(text, encoding="utf-8")
        return load_document(path)


def physics_document():
    return create_document(
        "# Methods\n"
        "The instrument was calibrated against a NIST reference standard.\n"
        "\n"
        "Measurements were repeated n = 12 times.\n"
        "# Results\n"
        "The measured signal was 3.4 ± 0.2 mT.\n"
    )


def fill_review(template, document, *,
                source_quote="The instrument was calibrated against a NIST reference standard."):
    filled = copy.deepcopy(template)
    for entry in filled["assessments"]:
        entry["reviewer_assessments"] = [
            {
                "reviewer_id": reviewer,
                "verdict": "partially_reported",
                "rationale": "The source text contains a plausible candidate requiring interpretation.",
                "source_quote": source_quote,
            }
            for reviewer in ("IndependentExpertA", "IndependentExpertB")
        ]
        entry["adjudicated_verdict"] = "partially_reported"
        entry["adjudication_rationale"] = (
            "Both reviewers identified only preliminary reporting evidence."
        )
    return filled


@contextlib.contextmanager
def local_grammar_response(response_factory=None):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/v2/check", self.path
            size = int(self.headers.get("Content-Length", "0"))
            payload = parse_qs(self.rfile.read(size).decode("utf-8"))
            received.append(payload)
            text = payload["text"][0]
            start = text.index("wrong") if "wrong" in text else 0
            start_utf16 = len(text[:start].encode("utf-16-le")) // 2
            result = response_factory(text) if response_factory else {
                "matches": [
                    {
                        "offset": start_utf16,
                        "length": 5,
                        "message": "Consider another word.",
                        "replacements": [{"value": "incorrect"}],
                        "rule": {"id": "FAKE_LOCAL_RULE"},
                    }
                ]
            }
            blob = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(blob)))
            self.end_headers()
            self.wfile.write(blob)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_address[1], received
    finally:
        server.shutdown()
        worker.join(timeout=2)
        server.server_close()


class EvidenceBasedDomainReviewTests(unittest.TestCase):
    def test_six_discipline_profiles_have_in_scope_rules(self):
        self.assertEqual(
            set(PROFILES),
            {"clinical", "animal", "physics", "chemistry", "computing", "social-science"},
        )
        for name, profile in PROFILES.items():
            with self.subTest(name=name):
                self.assertGreaterEqual(len(profile["rules"]), 6)
                self.assertEqual(len({rule.key for rule in profile["rules"]}),
                                 len(profile["rules"]))
                for rule in profile["rules"]:
                    self.assertGreaterEqual(len(rule.signals), 2)

    def test_extended_domain_questions_cannot_claim_expert_review(self):
        for discipline in PROFILES:
            with self.subTest(discipline=discipline):
                doc = create_document("# Methods\nA neutral control sentence.\n")
                report = review_domain(doc, discipline)
                self.assertGreaterEqual(len(report["items"]), 6)
                self.assertEqual(report["summary"]["expert_verified_items"], 0)
                self.assertTrue(all(item["expert_assessment"] == "REQUIRED"
                                    for item in report["items"]))

    def test_fenced_code_leading_content_preserves_actual_source_line(self):
        doc = create_document(
            "# Methods\n~~~python\n"
            "wrong hidden code\n~~~\n"
            "The instrument was calibrated against a NIST reference.\n"
            "# Results\nMeasured 1 ± 0.1 V.\n"
        )
        self.assertEqual(doc.section_start_lines["Methods"], 5)
        review = review_domain(doc, "physics")
        calibration = next(x for x in review["items"] if x["rule_id"] == "instrument_calibration")
        self.assertEqual(calibration["evidence"][0]["line"], 5)

    def test_physics_source_quotes_and_lines(self):
        doc = physics_document()
        result = review_domain(doc, "physics")
        self.assertEqual(result["source_sha256"], doc.sha256)
        self.assertEqual(result["summary"]["expert_verified_items"], 0)
        self.assertGreaterEqual(result["summary"]["textual_candidates"], 3)
        uncertainty = next(
            x for x in result["items"] if x["rule_id"] == "quantified_uncertainty"
        )
        self.assertEqual(uncertainty["status"], "TEXTUAL_EVIDENCE_CANDIDATE")
        self.assertEqual(uncertainty["evidence"][0]["line"], 6)
        self.assertEqual(uncertainty["evidence"][0]["section"], "Results")
        self.assertIn("± 0.2", uncertainty["evidence"][0]["excerpt"])
        self.assertEqual(uncertainty["expert_assessment"], "REQUIRED")
        self.assertEqual(len(result["ruleset_sha256"]), 64)

    def test_section_constraint_excludes_later_methods_mention(self):
        doc = create_document(
            "# Results\nCalibration relied on a NIST reference standard.\n"
            "# Conclusion\nThe reference standard was adequate.\n"
        )
        review = review_domain(doc, "physics")
        calibration = next(
            x for x in review["items"] if x["rule_id"] == "instrument_calibration"
        )
        self.assertEqual(calibration["status"], "NOT_DETECTED_REVIEW_MANUALLY")
        self.assertEqual(calibration["evidence"], [])

    def test_separate_paragraphs_do_not_satisfy_joint_condition(self):
        doc = create_document(
            "# Methods\nThe instrument was calibrated.\n\n"
            "A NIST reference was used elsewhere.\n"
        )
        review = review_domain(doc, "physics")
        calibration = next(
            x for x in review["items"] if x["rule_id"] == "instrument_calibration"
        )
        self.assertEqual(calibration["status"], "PARTIAL_CUES_REVIEW_MANUALLY")
        self.assertEqual(calibration["signal_hit_counts"]["calibration"], 1)
        self.assertEqual(calibration["signal_hit_counts"]["reference"], 1)
        self.assertEqual(calibration["evidence"], [])

    def test_reference_list_and_fenced_code_do_not_fake_evidence(self):
        doc = create_document(
            "# Methods\n~~~python\n"
            "calibrated against a NIST reference\n~~~\n"
            "Actual methods described without calibration.\n"
            "# References\nNIST calibration reference standard.\n"
        )
        review = review_domain(doc, "physics")
        calibration = next(
            x for x in review["items"] if x["rule_id"] == "instrument_calibration"
        )
        self.assertNotEqual(calibration["status"], "TEXTUAL_EVIDENCE_CANDIDATE")

    def test_cues_are_conditional_on_matching_context_in_six_disciplines(self):
        fixtures = {
            "clinical": (
                "# Methods\nThe ethics IRB: 2026-024 approval covered our study.\n",
                "ethics_identifier",
            ),
            "animal": (
                "# Methods\nThe experimental unit was the mouse, not the cage.\n",
                "experimental_unit",
            ),
            "physics": (
                "# Methods\nThe sensor was calibrated against a NIST reference.\n",
                "instrument_calibration",
            ),
            "chemistry": (
                "# Results\nHPLC purity was 97.5% for the product.\n",
                "analytical_purity",
            ),
            "computing": (
                "# Methods\nA train-test split prevented patient-level leakage.\n",
                "split_and_leakage",
            ),
            "social-science": (
                "# Methods\nSampling included n=200 participants from the population.\n",
                "sampling_and_n",
            ),
        }
        for name, (text, expected_rule) in fixtures.items():
            with self.subTest(discipline=name):
                doc = create_document(text)
                report = review_domain(doc, name)
                item = next(x for x in report["items"] if x["rule_id"] == expected_rule)
                self.assertEqual(item["status"], "TEXTUAL_EVIDENCE_CANDIDATE")
                self.assertEqual(item["evidence"][0]["line"], 2)

    def test_ruleset_hash_is_stable_across_reloads(self):
        doc = physics_document()
        first = review_domain(doc, "physics")
        second = review_domain(doc, "physics")
        self.assertEqual(first, second)

    def test_invalid_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unknown discipline"):
            review_domain(physics_document(), "astrology")

    def test_writing_audit_includes_domain_evidence_separately(self):
        doc = (
            "# Methods\nWe calibrated an instrument against a NIST reference.\n"
            "# Results\nThe result was 1.5 ± 0.1 V.\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper.md"
            path.write_text(doc)
            report = audit_academic_writing(path, discipline="physics")
        self.assertIn("discipline_review", report)
        self.assertEqual(report["discipline_review"]["summary"]["textual_candidates"], 2)
        markdown = writing_report_markdown(report)
        self.assertIn("Discipline-specific evidence candidates", markdown)
        self.assertIn("NOT expert verification", markdown)

    def test_domain_markdown_escapes_unsafe_source_text(self):
        doc = (
            "# Methods\nThe instrument was calibrated with a NIST reference "
            "<script>alert('bad')</script>.\n"
        )
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "paper.md"
            path.write_text(doc)
            report = audit_academic_writing(path, discipline="physics")
        markdown = writing_report_markdown(report)
        self.assertIn("&lt;script&gt;", markdown)
        self.assertNotIn("<script>", markdown)


class ExpertTemplateAndImportTests(unittest.TestCase):
    def test_template_has_source_bound_fingerprint_and_no_fake_experts(self):
        doc = physics_document()
        template = make_domain_template(doc, "physics")
        self.assertEqual(template["kind"], "manual_domain_expert_assessment_template")
        self.assertEqual(template["source_sha256"], doc.sha256)
        self.assertEqual(len(template["contract_sha256"]), 64)
        self.assertTrue(all(x["reviewer_assessments"] == [] for x in template["assessments"]))
        self.assertTrue(all(x["adjudicated_verdict"] is None for x in template["assessments"]))

    def test_two_reviewer_review_with_exact_quotes_is_structurally_accepted(self):
        doc = physics_document()
        completed = fill_review(make_domain_template(doc, "physics"), doc)
        result = validate_domain_adjudication(doc, "physics", completed)
        self.assertEqual(result["status"], "STRUCTURALLY_ACCEPTED_FOR_EXPERT_OVERSIGHT")
        self.assertEqual(result["declared_reviewer_count"], 2)
        self.assertGreaterEqual(result["rule_count"], 6)
        self.assertIn("not verified", " ".join(result["limitations"]).lower())

    def test_wrong_source_hash_and_rule_fingerprint_are_rejected(self):
        doc = physics_document()
        for field in ("source_sha256", "contract_sha256", "ruleset_sha256", "discipline"):
            with self.subTest(field=field):
                completed = fill_review(make_domain_template(doc, "physics"), doc)
                completed[field] = "tampered"
                with self.assertRaisesRegex(ValueError, "does not match"):
                    validate_domain_adjudication(doc, "physics", completed)

    def test_source_quote_must_exist_verbatim(self):
        doc = physics_document()
        completed = fill_review(make_domain_template(doc, "physics"), doc)
        completed["assessments"][0]["reviewer_assessments"][0]["source_quote"] = (
            "Never observed fictional evidence in this manuscript."
        )
        with self.assertRaisesRegex(ValueError, "absent from the source"):
            validate_domain_adjudication(doc, "physics", completed)

    def test_positive_assessment_requires_source_quote(self):
        doc = physics_document()
        completed = fill_review(make_domain_template(doc, "physics"), doc)
        completed["assessments"][0]["reviewer_assessments"][1]["source_quote"] = ""
        with self.assertRaisesRegex(ValueError, "exact source quote"):
            validate_domain_adjudication(doc, "physics", completed)

    def test_duplicate_or_missing_rule_is_rejected(self):
        doc = physics_document()
        for kind in ("missing", "duplicate"):
            with self.subTest(kind=kind):
                completed = fill_review(make_domain_template(doc, "physics"), doc)
                if kind == "missing":
                    completed["assessments"].pop()
                else:
                    completed["assessments"][-1]["rule_id"] = completed["assessments"][0]["rule_id"]
                with self.assertRaisesRegex(ValueError, "each rule ID once"):
                    validate_domain_adjudication(doc, "physics", completed)

    def test_duplicate_reviewer_identity_rejected(self):
        doc = physics_document()
        completed = fill_review(make_domain_template(doc, "physics"), doc)
        completed["assessments"][0]["reviewer_assessments"][1]["reviewer_id"] = "IndependentExpertA"
        with self.assertRaisesRegex(ValueError, "must differ"):
            validate_domain_adjudication(doc, "physics", completed)

    def test_bad_verdict_and_weak_rationale_rejected(self):
        doc = physics_document()
        for field, value, message in (
            ("verdict", "truth", "Expert verdict"),
            ("rationale", "ok", "20 characters"),
        ):
            with self.subTest(field=field):
                completed = fill_review(make_domain_template(doc, "physics"), doc)
                completed["assessments"][0]["reviewer_assessments"][0][field] = value
                with self.assertRaisesRegex(ValueError, message):
                    validate_domain_adjudication(doc, "physics", completed)

    def test_positive_final_verdict_requires_one_positive_reader(self):
        doc = physics_document()
        completed = fill_review(make_domain_template(doc, "physics"), doc)
        for reviewer in completed["assessments"][0]["reviewer_assessments"]:
            reviewer["verdict"] = "not_reported"
            reviewer["source_quote"] = None
        with self.assertRaisesRegex(ValueError, "supporting source-quoted"):
            validate_domain_adjudication(doc, "physics", completed)

    def test_adjudication_and_two_reader_fields_mandatory(self):
        doc = physics_document()
        completed = fill_review(make_domain_template(doc, "physics"), doc)
        completed["assessments"][0]["reviewer_assessments"].pop()
        with self.assertRaisesRegex(ValueError, "exactly two"):
            validate_domain_adjudication(doc, "physics", completed)
        completed = fill_review(make_domain_template(doc, "physics"), doc)
        completed["assessments"][0]["adjudication_rationale"] = None
        with self.assertRaisesRegex(ValueError, "Adjudication rationale"):
            validate_domain_adjudication(doc, "physics", completed)


class LocalGrammarConnectorTests(unittest.TestCase):
    def test_real_loopback_protocol_and_source_provenance(self):
        doc = create_document("# Methods\nThe analysis was wrong.\n")
        with local_grammar_response() as (port, received):
            results = check_local_languagetool(doc, port=port, language="en")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["line"], 2)
        self.assertEqual(results[0]["excerpt"], "wrong")
        self.assertEqual(results[0]["suggestion"], "incorrect")
        self.assertEqual(results[0]["rule_id"], "FAKE_LOCAL_RULE")
        self.assertEqual(results[0]["engine"], "languagetool_local")
        self.assertEqual(received[0]["language"], ["en-US"])

    def test_references_and_fenced_code_not_sent_to_local_server(self):
        doc = create_document(
            "# Methods\n~~~python\nwrong code\n~~~\n"
            "There is a wrong detail.\n"
            "# References\nA wrong citation title.\n"
        )
        references = {"References"}
        with local_grammar_response() as (port, received):
            findings = check_local_languagetool(
                doc, port=port, excluded_sections=references, language="tr",
            )
        payload = received[0]["text"][0]
        self.assertIn("wrong detail", payload)
        self.assertNotIn("wrong code", payload)
        self.assertNotIn("wrong citation", payload)
        self.assertEqual(received[0]["language"], ["tr"])
        self.assertEqual(findings[0]["line"], 5)

    def test_emoji_utf16_offsets_map_to_correct_character(self):
        doc = create_document("# Methods\n🧪 It was wrong.\n")
        with local_grammar_response() as (port, _):
            results = check_local_languagetool(doc, port=port)
        self.assertEqual(results[0]["excerpt"], "wrong")
        self.assertEqual(results[0]["line"], 2)

    def test_local_grammar_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "article.md"
            path.write_text("# Methods\nThe analysis was wrong.\n")
            with patch("sra.writing.check_local_languagetool") as hook:
                result = audit_academic_writing(path)
            hook.assert_not_called()
        self.assertEqual(result["grammar_engine"], "rules")
        self.assertEqual(result["grammar_suggestions"], [])

    def test_optin_grammar_appended_to_report_without_source_edit(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "article.md"
            original = "# Methods\nThe analysis was wrong.\n"
            path.write_text(original)
            with local_grammar_response() as (port, _):
                result = audit_academic_writing(
                    path, grammar_engine="local-languagetool", grammar_port=port,
                )
            self.assertEqual(path.read_text(), original)
        self.assertEqual(result["grammar_engine"], "local-languagetool")
        self.assertEqual(result["grammar_suggestions"][0]["suggestion"], "incorrect")
        self.assertIn("Local grammar suggestions", writing_report_markdown(result))

    def test_unreachable_local_service_is_explicit_error(self):
        doc = create_document("# Methods\nThe analysis was wrong.\n")
        with patch("sra.grammar_engine.build_opener") as opener:
            opener.return_value.open.side_effect = URLError("unavailable")
            with self.assertRaisesRegex(RuntimeError, "service unavailable"):
                check_local_languagetool(doc, port=8081)

    def test_invalid_options_rejected_before_requests(self):
        doc = create_document("# Methods\nText.\n")
        for params in (
            {"port": 80},
            {"port": True},
            {"timeout": -1},
            {"timeout": float("inf")},
            {"language": "auto"},
        ):
            with self.subTest(params=params):
                with self.assertRaises(ValueError):
                    check_local_languagetool(doc, **params)

    def test_malformed_json_or_offsets_are_rejected(self):
        doc = create_document("# Methods\nThe analysis was wrong.\n")
        def return_bad(_):
            return {"matches": [
                {"offset": 10**6, "length": 4, "replacements": [], "rule": {"id": "x"}},
            ]}
        with local_grammar_response(return_bad) as (port, _):
            with self.assertRaisesRegex(ValueError, "offset is invalid"):
                check_local_languagetool(doc, port=port)

    def test_oversized_manuscript_never_reaches_network(self):
        doc = create_document("# Methods\n" + "many words " * 13000 + "\n")
        with patch("sra.grammar_engine.build_opener") as opener:
            with self.assertRaisesRegex(ValueError, "No content was sent"):
                check_local_languagetool(doc)
            opener.assert_not_called()

    def test_disconnected_engine_and_disabled_language_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "article.md"
            path.write_text("# Methods\nText.\n")
            with self.assertRaisesRegex(ValueError, "language en or tr"):
                audit_academic_writing(
                    path, grammar_engine="local-languagetool", style_language="none",
                )


if __name__ == "__main__":
    unittest.main()
