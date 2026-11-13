"""Unified MCP consent boundaries and real-engine source binding."""
import asyncio
import hashlib
import json
import os
import unittest
from unittest.mock import patch

from mcp_server import bridge, server

DOC = "# Proof\nWe derive an identity under explicit assumptions.\n"


class UnifiedMCPTests(unittest.TestCase):
    def api(self):
        self.assertTrue(hasattr(bridge, "review_manuscript"), "Unified MCP bridge is missing")
        return bridge.review_manuscript

    def test_offline_real_engine_no_persistent_paths_and_default_model_off(self):
        run = self.api()
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            response = run(DOC, study_type="theoretical", disciplines=["physics", "computing"])
        self.assertTrue(response["ok"], response)
        report = response["result"]
        self.assertEqual(report["source_sha256"], hashlib.sha256(DOC.encode()).hexdigest())
        self.assertEqual(report["modules"]["model"]["status"], "not_requested")
        self.assertEqual(report['criteria_matrix']['source_sha256'],report['source_sha256'])
        criteria={row['id']:row for row in report['criteria_matrix']['criteria']}
        self.assertEqual(criteria['proof_completeness']['execution_status'],'human_review_required')
        self.assertEqual(criteria['code_reexecution']['scientific_verdict'],'NOT_ASSESSED')
        self.assertEqual(report["source"], "uploaded.md")
        self.assertNotIn("sra-mcp-", json.dumps(report))

    def test_both_per_call_and_host_consent_are_needed(self):
        run = self.api()
        with patch.dict(os.environ, {"SRA_MCP_ENABLE_NETWORK": "0", "SRA_MCP_ENABLE_MODEL_REVIEW": "0"}):
            for kwargs in (dict(online=True), dict(send_to_model=True), dict(online=1), dict(send_to_model=1)):
                with self.subTest(kwargs=kwargs):
                    self.assertEqual(run(DOC, **kwargs)["error"], "INVALID_INPUT")
        with patch.dict(os.environ, {"SRA_MCP_ENABLE_MODEL_REVIEW": "1", "SRA_MCP_MODEL": "", "OPENAI_API_KEY": "test"}):
            self.assertEqual(run(DOC, send_to_model=True)["error"], "INVALID_INPUT")

    def test_enabled_host_without_caller_consent_never_sends(self):
        run = self.api()
        with patch.dict(os.environ, {"SRA_MCP_ENABLE_NETWORK": "1", "SRA_MCP_ENABLE_MODEL_REVIEW": "1"}), \
             patch("sra.review.review_parsed_paper", side_effect=AssertionError("unexpected model")), \
             patch("sra.doi._lookup_registry", side_effect=AssertionError("unexpected DOI")):
            self.assertTrue(run(DOC)["ok"])

    def test_enabled_requested_model_failure_is_visible_partial_not_transport_success(self):
        run = self.api()
        with patch.dict(os.environ, {"SRA_MCP_ENABLE_MODEL_REVIEW": "1", "SRA_MCP_MODEL": "fake", "OPENAI_API_KEY": "fake-not-live"}), \
             patch("sra.review.review_parsed_paper", side_effect=RuntimeError("private")):
            response = run(DOC, send_to_model=True)
        self.assertTrue(response["ok"])
        self.assertEqual(response["result"]["execution_status"], "partial")
        self.assertEqual(response["result"]["modules"]["model"]["status"], "failed")

    def test_invalid_spec_or_profile_blocks_external_work(self):
        run = self.api()
        with patch.dict(os.environ, {"SRA_MCP_ENABLE_NETWORK": "1"}), \
             patch("sra.doi._lookup_registry", side_effect=AssertionError("network")):
            for kwargs in (dict(scientific_spec_json="[]"), dict(statistics_spec_json="{}"),
                           dict(disciplines=["unknown"]), dict(disciplines="physics"),
                           dict(statistics_spec_json="a" * (bridge.MAX_JSON_BYTES + 1))):
                with self.subTest(keys=list(kwargs)):
                    self.assertEqual(run(DOC, online=True, **kwargs)["error"], "INVALID_INPUT")

    def test_structured_values_and_catalog_and_response_bounds(self):
        run = self.api()
        science = '{"schema_version":"1.0","checks":[{"id":"x","kind":"dimension_equation","lhs":"x","rhs":"x","variables":{"x":{"dimensions":{"L":1}}}}]}'
        # Reuse the supported reference fixture rather than inventing an input schema.
        from pathlib import Path
        science = (Path(__file__).parents[2] / "examples/advanced_scientific_checks.json").read_text()
        result = run(DOC, scientific_spec_json=science)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["modules"]["scientific"]["status"], "completed")
        catalog = bridge.get_review_capabilities()
        self.assertTrue(catalog["ok"])
        self.assertFalse(catalog["result"]["interfaces"]["mcp"]["ocr"])
        with patch.object(bridge, "MAX_RESPONSE_BYTES", 10):
            self.assertEqual(run(DOC)["error"], "INVALID_INPUT")

    def test_mcp_wrappers_and_discovery_include_additive_tools(self):
        self.api()
        result = server.review_manuscript(DOC, study_type="theoretical", disciplines=["physics"])
        self.assertTrue(result["ok"])
        self.assertTrue(server.get_review_capabilities()["ok"])
        tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
        self.assertTrue(tools["review_manuscript"].annotations.openWorldHint)
        self.assertFalse(tools["get_review_capabilities"].annotations.openWorldHint)
        self.assertNotIn("path", tools["review_manuscript"].inputSchema["properties"])


if __name__ == "__main__":
    unittest.main()
