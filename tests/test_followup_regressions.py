"""Edge-case regression tests."""
import json, os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from jsonschema import Draft202012Validator, FormatChecker
from sra.audit import audit_file
from sra.report import to_markdown
from sra.semantic_review import build_semantic_review_template, validate_semantic_review
from sra.model_client import request_single_model_review

class FollowupSecurityTests(unittest.TestCase):
    def test_untrusted_conclusion_section_escaped(self):
        source="# Methods\nAn observational study.\n# Results\nPain decreased.\n# Conclusion\nPain increased."
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"paper.md";path.write_text(source)
            report=audit_file(str(path))
        report.reasoning_map.append({"relation":"possible_directional_contradiction",
            "status":"heuristic_review_required","results_sentence":"Pain decreased.",
            "conclusion_section":"Discussion <img src=x onerror=alert(1)>",
            "conclusion_sentence":"Pain increased."})
        out=to_markdown(report)
        self.assertNotIn("<img",out)
        self.assertIn("&lt;img",out)

    def test_non_rfc3339_separator_rejected(self):
        source=("# Methods\nA controlled protocol was used.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score.")
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"paper.md";path.write_text(source)
            report=audit_file(str(path)).to_dict()
        review=build_semantic_review_template(report,source_text=source)
        self.assertEqual(len(review["assessments"]),1)
        review["reviewer"]={"name":"Fixture","model_or_agent":"test",
            "reviewed_at_utc":"2026-11-04X12:00:00Z"}
        review["assessments"][0].update({"relation":"entailed","confidence":0.8,
            "rationale":"Lexical evidence.","source_quotes":[
            "The intervention increased the measured score."]})
        schema=json.loads((Path(__file__).resolve().parents[1]/
            "schemas/semantic-review-completed.schema.json").read_text())
        self.assertTrue(list(Draft202012Validator(schema,format_checker=FormatChecker()).iter_errors(review)))
        self.assertEqual(validate_semantic_review(review,report,source)["status"],"REJECTED")

    def test_control_char_urls_never_reach_network(self):
        for control in ("\x01","\x7f","\n"):
            with self.subTest(control=repr(control)):
                with patch.dict(os.environ,{"SRA_TEST_KEY":"dummy-secret"}):
                    with patch("sra.model_client._open_api_request") as transport:
                        with self.assertRaises(ValueError) as err:
                            request_single_model_review(
                                {"review_mode":"single"},"manuscript",
                                model="model",base_url="https://example.test/v1/PRIVATE_PATH"+control+"token",
                                api_key_env="SRA_TEST_KEY")
                transport.assert_not_called()
                self.assertNotIn("PRIVATE_PATH",str(err.exception))
