"""Negative controls and transport-wrapper coverage."""
import asyncio
import importlib
import os
import runpy
import warnings
import unittest
from unittest.mock import patch

from mcp_server import auth, bridge, server

DOC = "# Methods\nAn observational method.\n# Results\nNo evidence of effects.\n# Conclusion\nNo causal proof."


class BridgeNegativeTests(unittest.TestCase):
    def test_utf8_expansion_and_invalid_binary_text(self):
        with patch.object(bridge, "MAX_DOCUMENT_BYTES", 4):
            with self.assertRaisesRegex(ValueError, "20 MiB"):
                bridge._document_bytes("ééé", "md", "text")
        with self.assertRaisesRegex(ValueError, "UTF-8"):
            bridge._document_bytes("/w==", "txt", "base64")

    def test_busy_and_processing_failure(self):
        self.assertTrue(bridge._LIMITER.acquire(blocking=False))
        self.assertTrue(bridge._LIMITER.acquire(blocking=False))
        try:
            busy = bridge._invoke(lambda: {"x": True})
            self.assertEqual(busy["error"], "BUSY")
        finally:
            bridge._LIMITER.release()
            bridge._LIMITER.release()
        error = bridge._invoke(lambda: (_ for _ in ()).throw(RuntimeError("secret payload")))
        self.assertEqual(error["error"], "PROCESSING_FAILED")
        self.assertNotIn("secret", str(error))

    def test_invalid_editorial_parameters(self):
        self.assertFalse(bridge.audit_academic_writing(DOC, genre="invalid")["ok"])
        self.assertFalse(bridge.audit_academic_writing(DOC, style_language="bad")["ok"])

    def test_invalid_citation_online_type(self):
        result = bridge.check_citations(DOC, online="yes")
        self.assertEqual(result["error"], "INVALID_INPUT")

    def test_missing_model_config(self):
        with patch.dict(os.environ, {
            "SRA_MCP_ENABLE_MODEL_REVIEW": "1",
            "SRA_MCP_MODEL": "",
            "OPENAI_API_KEY": "test-not-live"
        }):
            result = bridge.review_scientific_paper(DOC, send_to_model=True)
        self.assertFalse(result["ok"])
        self.assertIn("identifier", result["message"])

    def test_scrub_recursive_structures(self):
        from pathlib import Path
        value = {"a": ["/tmp/x/secret", {"b": "/tmp/x/doc.pdf"}]}
        safe = bridge._scrub(value, Path("/tmp/x"))
        self.assertNotIn("/tmp/x", str(safe))
        self.assertEqual(bridge._scrub(1, Path("/tmp/x")), 1)


class MCPEntryPointTests(unittest.TestCase):
    def test_six_wrapper_functions_and_stdio_main(self):
        with patch.object(server.bridge, "audit_manuscript", return_value={"ok": True}):
            self.assertTrue(server.audit_manuscript(DOC)["ok"])
        with patch.object(server.bridge, "audit_academic_writing", return_value={"ok": True}):
            self.assertTrue(server.audit_academic_writing(DOC)["ok"])
        with patch.object(server.bridge, "check_citations", return_value={"ok": True}):
            self.assertTrue(server.check_citations(DOC)["ok"])
        with patch.object(server.bridge, "verify_statistics", return_value={"ok": True}):
            self.assertTrue(server.verify_statistics("{}")["ok"])
        with patch.object(server.bridge, "verify_scientific_claims", return_value={"ok": True}):
            self.assertTrue(server.verify_scientific_claims("{}")["ok"])
        with patch.object(server.bridge, "review_scientific_paper", return_value={"ok": True}):
            self.assertTrue(server.review_scientific_paper(DOC)["ok"])
        with patch.object(server.mcp, "run") as runner:
            server.main()
        runner.assert_called_once_with(transport="stdio")

    def test_module_as_script_no_network(self):
        from mcp.server.fastmcp import FastMCP
        with patch.object(FastMCP, "run") as runner:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                runpy.run_module("mcp_server.server", run_name="__main__")
        runner.assert_called_once_with(transport="stdio")

    def test_http_entrypoint_with_token(self):
        with patch.dict(os.environ, {"SRA_MCP_BEARER_TOKEN": "t" * 40}):
            loaded = importlib.import_module("mcp_server.http")
            self.assertIsInstance(loaded.app, auth.BearerGuard)


class AuthEdgeTests(unittest.TestCase):
    def test_non_http_scope_passes_through(self):
        seen = []
        async def downstream(scope, receive, send):
            seen.append(scope["type"])
        guard = auth.BearerGuard(downstream, "a" * 40)
        async def noop():
            return {"type": "lifespan.shutdown"}
        async def send(_):
            return None
        asyncio.run(guard({"type": "lifespan"}, noop, send))
        self.assertEqual(seen, ["lifespan"])


if __name__ == "__main__":
    unittest.main()
