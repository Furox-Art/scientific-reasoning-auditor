"""Integration tests using the REAL SRA engine, never synthetic verdicts."""
import base64
import hashlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from mcp_server import bridge

MANUSCRIPT = (
    "# Introduction\nThe goal is to assess a treatment.\n"
    "# Methods\nObservational cohort with no randomization.\n"
    "# Results\nThe treatment was associated with increased recovery.\n"
    "# Conclusion\nThe treatment proves improved recovery.\n"
    "# References\nExample paper, DOI: 10.1000/182\n"
)


class DocumentBoundaryTests(unittest.TestCase):
    def test_accepted_text_and_binary(self):
        self.assertEqual(bridge._document_bytes("a\nb", "md", "text"), b"a\nb")
        self.assertEqual(bridge._document_bytes("ö", "txt", "text"), "ö".encode())
        self.assertEqual(bridge._document_bytes(base64.b64encode(b"%PDF-1.7\n").decode(), "pdf", "base64"), b"%PDF-1.7\n")

    def test_rejected_paths_formats_and_payloads(self):
        for fmt, enc, content in (
            ("../../etc/passwd", "text", "data"), ("exe", "text", "data"),
            ("pdf", "text", "not a pdf"), ("md", "zip", "hello"),
            ("md", "base64", "***"), ("pdf", "base64", base64.b64encode(b"notpdf").decode()),
            ("md", "text", ""), ("txt", "base64", "ö"),
        ):
            with self.subTest(fmt=fmt, enc=enc, content=content[:12]):
                with self.assertRaises(ValueError):
                    bridge._document_bytes(content, fmt, enc)

    def test_oversized_inputs_rejected_pre_decode(self):
        with self.assertRaises(ValueError):
            bridge._document_bytes("a" * (bridge.MAX_DOCUMENT_BYTES + 1), "md", "text")
        with self.assertRaises(ValueError):
            bridge._document_bytes("A" * (bridge.MAX_B64_CHARS + 1), "pdf", "base64")
        with self.assertRaises(ValueError):
            bridge._json_bytes("é" * (bridge.MAX_JSON_BYTES // 2 + 1))

    def test_temp_file_deleted_even_on_error(self):
        with bridge._uploaded(b"secret", ".txt") as (file, root):
            self.assertEqual(file.read_bytes(), b"secret")
            self.assertEqual(file.parent, root)
            filename = file
        self.assertFalse(filename.exists())

    def test_json_guard(self):
        self.assertEqual(bridge._json_bytes('{"a":1}'), b'{"a":1}')
        for data in ("", None, "a" * (bridge.MAX_JSON_BYTES + 1)):
            with self.assertRaises(ValueError):
                bridge._json_bytes(data)

    def test_bounded_output_rejects_no_truncation(self):
        with self.assertRaisesRegex(ValueError, "no partial report"):
            bridge._bounded({"text": "X" * (bridge.MAX_RESPONSE_BYTES + 1)})


class RealEngineTests(unittest.TestCase):
    def test_audit_real_engine_and_provenance(self):
        result = bridge.audit_manuscript(MANUSCRIPT)
        self.assertTrue(result["ok"], result)
        report = result["result"]
        self.assertEqual(report["sha256"], hashlib.sha256(MANUSCRIPT.encode()).hexdigest())
        self.assertEqual(report["source"], "uploaded.md")
        self.assertIn("reasoning_graph", report)
        self.assertNotIn("sra-mcp-", json.dumps(report))

    def test_two_calls_isolated_and_distinct(self):
        def check(text):
            result = bridge.audit_manuscript(text)
            self.assertTrue(result["ok"], result)
            return result["result"]["sha256"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(check, [MANUSCRIPT, MANUSCRIPT + "More data.\n"]))
        self.assertNotEqual(a, b)

    def test_writing_and_dois(self):
        writing = bridge.audit_academic_writing(MANUSCRIPT, genre="original-research")
        self.assertTrue(writing["ok"], writing)
        self.assertIn("findings", writing["result"])
        doi = bridge.check_citations(MANUSCRIPT)
        self.assertTrue(doi["ok"], doi)
        self.assertIn("10.1000/182", json.dumps(doi["result"]))

    def test_statistics_and_science_from_real_examples(self):
        root = Path(__file__).resolve().parents[2]
        stats = (root / "examples" / "welch_t_example.json").read_text()
        result = bridge.verify_statistics(stats)
        self.assertTrue(result["ok"], result)
        science = (root / "examples" / "advanced_scientific_checks.json").read_text()
        result = bridge.verify_scientific_claims(science)
        self.assertTrue(result["ok"], result)
        self.assertIn("checks", result["result"])

    def test_malformed_json_fails_closed(self):
        bad = bridge.verify_statistics('{"test":"welch_t","test":"welch_t"}')
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["error"], "INVALID_INPUT")
        self.assertFalse(bridge.verify_scientific_claims('{"schema_version":NaN}')["ok"])

    def test_offline_network_policy(self):
        with patch.dict(os.environ, {"SRA_MCP_ENABLE_NETWORK": "0"}):
            with patch("sra.doi._lookup_registry", side_effect=AssertionError("No network expected")):
                result = bridge.check_citations(MANUSCRIPT, online=True)
        self.assertFalse(result["ok"])
        self.assertIn("disabled", result["message"])

    def test_model_privacy_guard(self):
        with patch.dict(os.environ, {"SRA_MCP_ENABLE_MODEL_REVIEW": "0", "OPENAI_API_KEY": "dummy"}):
            with patch("sra.paper_review.review_paper", side_effect=AssertionError("Should not be called")):
                self.assertFalse(bridge.review_scientific_paper(MANUSCRIPT, send_to_model=False)["ok"])
                denied = bridge.review_scientific_paper(MANUSCRIPT, send_to_model=True)
                self.assertFalse(denied["ok"])
                self.assertIn("disabled", denied["message"])

    def test_model_opt_in_mock_provider_never_live(self):
        with patch.dict(os.environ, {
            "SRA_MCP_ENABLE_MODEL_REVIEW": "1", "OPENAI_API_KEY": "synthetic-not-real",
            "SRA_MCP_MODEL": "synthetic-model"
        }):
            with patch("sra.paper_review.review_paper", return_value={"covered_characters": 3}) as call:
                result = bridge.review_scientific_paper(MANUSCRIPT, send_to_model=True)
        self.assertTrue(result["ok"], result)
        self.assertEqual(call.call_args.kwargs["model"], "synthetic-model")
        self.assertFalse(call.call_args.kwargs["visual_pages"])


if __name__ == "__main__":
    unittest.main()
