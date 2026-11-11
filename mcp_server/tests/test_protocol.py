"""Test actual MCP tool registration and local stdio round-trip."""
import asyncio
import os
import sys
import unittest
from pathlib import Path

from mcp_server.server import mcp

REPO_ROOT = Path(__file__).resolve().parents[2]


class ProtocolTests(unittest.TestCase):
    def test_discovery_metadata(self):
        async def discover():
            tools = await mcp.list_tools()
            return tools
        tools = asyncio.run(discover())
        found = {tool.name: tool for tool in tools}
        self.assertEqual(set(found), {
            "audit_manuscript", "audit_academic_writing", "check_citations",
            "verify_statistics", "verify_scientific_claims", "review_scientific_paper",
        })
        for tool in tools:
            self.assertTrue(tool.annotations.readOnlyHint)
            self.assertFalse(tool.annotations.destructiveHint)
            self.assertIn("properties", tool.inputSchema)

    def test_stdio_client_round_trip(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def run():
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "mcp_server.server"],
                cwd=str(REPO_ROOT),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    tools = await client.list_tools()
                    self.assertTrue(any(t.name == "audit_manuscript" for t in tools.tools))
                    response = await client.call_tool("audit_manuscript", {
                        "content": "# Methods\nObservational.\n# Results\nA test.\n# Conclusion\nA conclusion.",
                    })
                    self.assertFalse(response.isError, response)
                    self.assertIn("result", str(response))
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
