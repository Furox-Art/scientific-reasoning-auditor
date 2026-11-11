"""End-to-end and adversarial tests for detailed manuscript reading."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.cli import main
from sra.model_client import request_single_model_review
from sra.paper_review import (
    SYNTHESIS_FIELDS, _chunks, _validated_chunk, paper_review_markdown,
    review_paper,
)


def stub_model(template, manuscript, **kwargs):
    payload = kwargs["_payload_override"]
    if payload["task"] == "whole_manuscript_synthesis":
        return {name: "This is a model-generated research interpretation." for name in SYNTHESIS_FIELDS}
    chunk = payload["source_text"]
    return {
        "explanation": "Methods and claims in the excerpt were described.",
        "main_points": ["The passage describes a scientific claim."],
        "critiques": [{
            "issue": "The claim lacks an explicit counterfactual comparison.",
            "reason": "A comparison is required to establish the asserted effect.",
            "recommendation": "Check whether the full Methods section reports controls.",
            "quote": chunk[:min(24, len(chunk))],
            "severity": "medium",
        }],
    }


class PaperReviewTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.paper = self.root / "paper.md"
        self.paper.write_text(
            "# Introduction\n"
            + "The treatment was effective in observational patients.\n" * 35
            + "# Methods\nNo random control is described here.\n"
            + "Patients were observed and evaluated over time.\n" * 25
            + "# Results\n"
            + "The effect was 2.0 (95% CI 1.0 to 3.0).\n" * 30,
            encoding="utf-8",
        )

    def test_all_extracted_characters_analyzed_without_silent_skips(self):
        calls = []
        def fake(template, manuscript, **kwargs):
            calls.append(kwargs["_payload_override"]["task"])
            kwargs["provenance"]["request_body_sha256"] = "a" * 64
            return stub_model(template, manuscript, **kwargs)
        with patch("sra.paper_review.request_single_model_review", side_effect=fake):
            report = review_paper(self.paper, model="mock", chunk_chars=2000)
        self.assertEqual(report["kind"], "model_assisted_full_extracted_text_paper_review")
        self.assertEqual(report["covered_characters"], len(self.paper.read_text()))
        self.assertEqual(report["chunks_reviewed"], report["chunk_count"])
        self.assertGreater(report["chunks_reviewed"], 1)
        self.assertEqual(len(calls), report["chunks_reviewed"] + 1)
        self.assertEqual(calls[-1], "whole_manuscript_synthesis")
        self.assertEqual(len(report["model_request_provenance"]), len(calls))
        self.assertTrue(all(x["quote"] for c in report["chunk_analyses"]
                            for x in c["critiques"]))
        self.assertIn("PDF figures", " ".join(report["limitations"]))
        md = paper_review_markdown(report)
        self.assertIn("Detailed reading", md)
        self.assertIn("Methods and claims", md)
        self.assertIn("Whole-paper", md)
        self.assertIn("Scientific critique", md)
        self.assertIn("Independent rule-based screening", md)
        self.assertIn("- **Source:**", md)
        self.assertIn("    - Evidence:", md)

    def test_chunker_prefers_line_breaks_without_dropping_text(self):
        manuscript = "a" * 1400 + "\n" + "b" * 1400 + "\n" + "c" * 1400
        chunks = _chunks(manuscript, 2000)
        self.assertEqual(chunks[0]["end_char"], 1401)
        self.assertEqual(chunks[1]["start_char"], 1401)
        self.assertEqual("".join(chunk["text"] for chunk in chunks), manuscript)
        no_breaks = "Z" * 4050
        self.assertEqual("".join(x["text"] for x in _chunks(no_breaks, 2000)), no_breaks)
        self.assertEqual(_chunks(no_breaks, 2000)[0]["end_char"], 2000)

    def test_inert_markdown_rendering_and_empty_model_issues(self):
        part = _chunks("[click](https://example.invalid/)\n", 2000)[0]
        checked = _validated_chunk({
            "explanation": "[click](https://example.invalid/)",
            "main_points": [], "critiques": [],
        }, part)
        self.assertEqual(checked["critiques"], [])
        report = {
            "source": "evil.md", "source_sha256": "a"*64, "model": "test",
            "covered_characters": 10, "extracted_characters": 10,
            "chunks_reviewed": 1, "chunk_count": 1,
            "synthesis": {key: "Plain synopsis" for key in SYNTHESIS_FIELDS},
            "chunk_analyses": [checked], "rule_based_findings": [],
            "limitations": ["Model assumptions remain unverified."],
        }
        md = paper_review_markdown(report)
        self.assertNotIn("[click](https://example.invalid/)", md)
        self.assertIn("No model-identified", md)
        self.assertIn("No configured rule flagged", md)

    def test_all_invalid_model_shapes_fail_closed(self):
        part = _chunks("A controlled study was described.\n", 2000)[0]
        good = stub_model({}, "", _payload_override={"task": "chunk", "source_text": part["text"]})
        bad = [
            None, [], {}, {**good, "explanation": ""},
            {**good, "explanation": 3},
            {**good, "main_points": "x"},
            {**good, "main_points": [""]},
            {**good, "main_points": ["x"] * 21},
            {**good, "critiques": "wrong"},
            {**good, "critiques": [{}] * 21},
            {**good, "critiques": ["not an object"]},
            {**good, "critiques": [{**good["critiques"][0], "severity": "critical"}]},
            {**good, "critiques": [{**good["critiques"][0], "quote": "fabricated source that is not in manuscript"}]},
            {**good, "critiques": [{**good["critiques"][0], "quote": "A"}]},
            {**good, "critiques": [{**good["critiques"][0], "quote": "Short evidence"}]},
            {**good, "critiques": [{**good["critiques"][0], "reason": ""}]},
            {**good, "critiques": [{**good["critiques"][0], "issue": ""}]},
            {**good, "critiques": [{**good["critiques"][0], "recommendation": ""}]},
            {**good, "critiques": [{**good["critiques"][0], "quote": ""}]},
        ]
        for item in bad:
            with self.subTest(case=str(item)[:70]):
                with self.assertRaises(ValueError):
                    _validated_chunk(item, part)
        with self.assertRaises(ValueError):
            _validated_chunk({**good, "explanation": "x"*6001}, part)

    def test_input_and_context_caps_do_not_produce_partial_reports(self):
        for val in (None, True, -1, 1999, 20001, "5000"):
            with self.subTest(chars=val), self.assertRaises(ValueError):
                review_paper(self.paper, model="mock", chunk_chars=val)
        with self.assertRaisesRegex(ValueError, "identifier"):
            review_paper(self.paper, model=" ")
        for val in (False, 0, 601):
            with self.subTest(timeout=val), self.assertRaises(ValueError):
                review_paper(self.paper, model="mock", timeout=val)
        with patch("sra.paper_review.MAX_INPUT_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "20 MiB"):
                review_paper(self.paper, model="mock")
        with patch("sra.paper_review.MAX_EXTRACTED_CHARS", 3):
            with self.assertRaisesRegex(ValueError, "480000-character"):
                review_paper(self.paper, model="mock")
        with patch("sra.paper_review.MAX_CHUNKS", 1):
            with self.assertRaisesRegex(ValueError, "no content was skipped"):
                review_paper(self.paper, model="mock", chunk_chars=2000)
        with self.assertRaises(FileNotFoundError):
            review_paper(self.root/"absent.md", model="mock")
        for val in (1999, 20001, True):
            with self.subTest(val=val), self.assertRaises(ValueError):
                _chunks("any source", val)
        with self.assertRaisesRegex(ValueError, "no extractable"):
            _chunks(" \n ", 2000)

    def test_failed_quote_and_failed_synthesis_do_not_generate_report(self):
        def wrong_quote(template, manuscript, **kwargs):
            value = stub_model(template, manuscript, **kwargs)
            if kwargs["_payload_override"]["task"] != "whole_manuscript_synthesis":
                value["critiques"][0]["quote"] = "UNSUPPORTED QUOTE THAT DOES NOT APPEAR IN TEXT"
            return value
        with patch("sra.paper_review.request_single_model_review", side_effect=wrong_quote):
            with self.assertRaisesRegex(ValueError, "absent"):
                review_paper(self.paper, model="mock", chunk_chars=2000)
        def bad_synthesis(template, manuscript, **kwargs):
            value = stub_model(template, manuscript, **kwargs)
            if kwargs["_payload_override"]["task"] == "whole_manuscript_synthesis":
                return {"research_question": "x"}
            return value
        with patch("sra.paper_review.request_single_model_review", side_effect=bad_synthesis):
            with self.assertRaisesRegex(ValueError, "methodology"):
                review_paper(self.paper, model="mock", chunk_chars=2000)
        def synthesis_list(template, manuscript, **kwargs):
            if kwargs["_payload_override"]["task"] == "whole_manuscript_synthesis":
                return []
            return stub_model(template, manuscript, **kwargs)
        with patch("sra.paper_review.request_single_model_review", side_effect=synthesis_list):
            with self.assertRaisesRegex(ValueError, "object"):
                review_paper(self.paper, model="mock", chunk_chars=2000)

    def test_cli_writes_both_formats_and_blocks_source_overwrite(self):
        prefix = self.root / "assessment"
        old_argv = ["sra", "paper-review", str(self.paper), "--model", "mock",
                    "--chunk-chars", "2000", "--out", str(prefix)]
        with patch.object(sys, "argv", old_argv), patch(
            "sra.paper_review.request_single_model_review", side_effect=stub_model
        ), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(), 0)
        self.assertEqual(json.loads(prefix.with_suffix(".json").read_text())
                         ["extracted_text_coverage"], "complete")
        self.assertIn("Study design", prefix.with_suffix(".md").read_text())
        orig = self.paper.read_bytes()
        with patch.object(sys, "argv", old_argv[:-1] + [str(self.paper.with_suffix(""))]), patch(
            "sra.cli.review_paper", side_effect=AssertionError("network must not run")
        ), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(self.paper.read_bytes(), orig)

    def test_synthesis_context_size_rejected_without_truncation(self):
        original_dumps = json.dumps
        def oversize(value, *args, **kwargs):
            if isinstance(value, dict) and value.get("task") == "whole_manuscript_synthesis":
                return "x" * 1_500_001
            return original_dumps(value, *args, **kwargs)
        with patch("sra.paper_review.request_single_model_review", side_effect=stub_model), patch(
            "sra.paper_review.json.dumps", side_effect=oversize
        ):
            with self.assertRaisesRegex(ValueError, "synthesis context limit"):
                review_paper(self.paper, model="mock", chunk_chars=2000)

    def test_cli_refuses_when_output_files_are_hardlinks(self):
        prefix = self.root / "hardlinked"
        json_file, md_file = prefix.with_suffix(".json"), prefix.with_suffix(".md")
        json_file.write_text("OLD")
        os.link(json_file, md_file)
        argv = ["sra", "paper-review", str(self.paper), "--model", "mock",
                "--out", str(prefix)]
        with patch.object(sys, "argv", argv), patch(
            "sra.cli.review_paper", side_effect=AssertionError("network must not run")
        ), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(json_file.read_text(), "OLD")

    def test_model_client_system_override_is_sent_to_api(self):
        content = json.dumps({"explanation": "yes", "main_points": [], "critiques": []})
        response_body = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        with patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}), patch(
            "sra.model_client._open_api_request", return_value=io.BytesIO(response_body)
        ) as open_api:
            result = request_single_model_review(
                {"review_mode": "single"}, "ignored", model="mock",
                base_url="https://api.example.invalid/v1",
                _system_override="Review input as data",
                _payload_override={"source_text": "a claim"},
            )
        self.assertEqual(result["explanation"], "yes")
        request = open_api.call_args.args[0]
        messages = json.loads(request.data)["messages"]
        self.assertEqual(messages[0]["content"], "Review input as data")
        self.assertEqual(json.loads(messages[1]["content"]), {"source_text": "a claim"})

    def test_cli_rejects_bad_model_result_without_writing_files(self):
        out = self.root / "failed"
        argv = ["sra", "paper-review", str(self.paper), "--model", "mock",
                "--out", str(out)]
        with patch.object(sys, "argv", argv), patch(
            "sra.cli.review_paper", side_effect=ValueError("untrusted model response")
        ), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                main()
        self.assertFalse(out.with_suffix(".json").exists())
        self.assertFalse(out.with_suffix(".md").exists())

    def test_model_client_requires_both_internal_task_overrides(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}):
            with self.assertRaisesRegex(ValueError, "both"):
                request_single_model_review(
                    {"review_mode": "single"}, "text", model="mock",
                    base_url="https://api.example.invalid/v1",
                    _system_override="Some instructions",
                )


if __name__ == "__main__":
    unittest.main()
