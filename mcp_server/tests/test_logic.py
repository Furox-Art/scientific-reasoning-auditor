"""MCP formal verification has no external calls or manuscript edits."""
import asyncio
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from mcp_server import bridge, server


class MCPLogicTests(unittest.TestCase):
    def problem(self):
        return json.loads((Path(__file__).parents[2] / "examples/logic_boolean.json").read_text())

    def test_standalone_and_bound_verification_use_real_solver(self):
        problem = self.problem()
        response = bridge.verify_logic(json.dumps(problem))
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["result"]["claims"][0]["status"], "VERIFIED")
        content = "# Assumptions\nThe hypothesis is assumed true for this example.\n"
        problem.update(source_sha256=hashlib.sha256(content.encode()).hexdigest(),
                       extracted_text_sha256=hashlib.sha256(content.encode()).hexdigest())
        raw = json.dumps(problem)
        with patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("network")):
            bound = bridge.verify_logic(raw, content)
            unified = bridge.review_manuscript(content, logic_spec_json=raw)
        self.assertTrue(bound["ok"], bound)
        self.assertTrue(unified["ok"], unified)
        self.assertEqual(bound["result"]["source_binding"]["status"], "source_matched")
        self.assertIn("logic", unified["result"]["modules"])

    def test_bad_spec_and_wrong_source_are_explicit_errors(self):
        self.assertFalse(bridge.verify_logic("[]")["ok"])
        self.assertFalse(bridge.verify_logic("x" * (bridge.MAX_JSON_BYTES + 1))["ok"])
        problem = self.problem()
        problem.update(source_sha256="a"*64, extracted_text_sha256="b"*64)
        self.assertEqual(bridge.verify_logic(json.dumps(problem), "A different manuscript.")["error"], "INVALID_INPUT")

    def test_tool_is_registered_as_read_only_local_and_wrapper_returns_report(self):
        tools = {t.name:t for t in asyncio.run(server.mcp.list_tools())}
        self.assertTrue(tools["verify_logic"].annotations.readOnlyHint)
        self.assertFalse(tools["verify_logic"].annotations.openWorldHint)
        self.assertTrue(server.verify_logic(json.dumps(self.problem()))["ok"])

    def test_native_backend_error_returns_structured_processing_failure(self):
        import z3
        with patch("sra.logic._check",side_effect=z3.Z3Exception("private backend data")):
            response=bridge.verify_logic(json.dumps(self.problem()))
        self.assertEqual(response["error"],"PROCESSING_FAILED")
        self.assertNotIn("private backend data",json.dumps(response))


if __name__ == "__main__":
    unittest.main()
