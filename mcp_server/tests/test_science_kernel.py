"""Standalone finite proof kernel stays offline and bounded over MCP."""
import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from mcp_server import bridge,server

SPEC=(Path(__file__).parents[2]/'examples/scientific-proof.json').read_text()


class KernelMCPTests(unittest.TestCase):
    def test_real_proof_and_independent_certificate_recheck_offline(self):
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('network')):
            result=server.prove_science(SPEC)
            self.assertTrue(result['ok'],result)
            certificate=json.dumps(result['result'])
            verified=server.verify_science_certificate(SPEC,certificate)
        self.assertTrue(verified['ok'],verified)
        self.assertTrue(verified['result']['valid'])
        forged=json.loads(certificate);forged['claims'][0]['status']='CONTRADICTED'
        response=server.verify_science_certificate(SPEC,json.dumps(forged))
        self.assertTrue(response['ok'])
        self.assertFalse(response['result']['valid'])
        self.assertNotIn('sra-mcp-',certificate)

    def test_invalid_inputs_size_guards_and_tool_discovery(self):
        self.assertEqual(bridge.prove_science('{}')['error'],'INVALID_INPUT')
        self.assertEqual(bridge.prove_science('x'*(1024*1024+1))['error'],'INVALID_INPUT')
        self.assertEqual(bridge.verify_science_certificate(SPEC,'x'*(1024*1024+1))['error'],'INVALID_INPUT')
        with patch.object(bridge,'MAX_RESPONSE_BYTES',10):
            self.assertEqual(bridge.prove_science(SPEC)['error'],'INVALID_INPUT')
        tools={t.name:t for t in asyncio.run(server.mcp.list_tools())}
        for name in ('prove_science','verify_science_certificate'):
            self.assertFalse(tools[name].annotations.openWorldHint)
            self.assertNotIn('path',tools[name].inputSchema['properties'])
