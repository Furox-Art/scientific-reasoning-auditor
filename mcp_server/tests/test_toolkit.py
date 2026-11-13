"""Local toolkit transport returns findings without editing uploaded content."""
import asyncio
import hashlib
import json
import unittest
from mcp_server import bridge,server


class MCPToolkitTests(unittest.TestCase):
    def test_standalone_and_source_bound_unified_toolkit(self):
        spec={'schema_version':'1.0','checks':[{'id':'math','kind':'polynomial_identity','variables':['x'],'left':'x+x','right':'2*x'}]}
        self.assertEqual(bridge.verify_toolkit(json.dumps(spec))['result']['checks'][0]['status'],'VERIFIED')
        content='# Proof\nAn exact identity is proposed.\n'
        spec.update(source_sha256=hashlib.sha256(content.encode()).hexdigest(),extracted_text_sha256=hashlib.sha256(content.encode()).hexdigest())
        self.assertTrue(bridge.verify_toolkit(json.dumps(spec),content)['ok'])
        self.assertTrue(bridge.review_manuscript(content,toolkit_spec_json=json.dumps(spec))['ok'])
        self.assertFalse(bridge.verify_toolkit('[]')['ok'])
        self.assertTrue(server.verify_toolkit(json.dumps(spec),content)['ok'])
        self.assertTrue(server.review_manuscript(content,toolkit_spec_json=json.dumps(spec))['ok'])
        tools={tool.name:tool for tool in asyncio.run(server.mcp.list_tools())}
        self.assertTrue(tools['verify_toolkit'].annotations.readOnlyHint)
        self.assertFalse(tools['verify_toolkit'].annotations.openWorldHint)
        prepared=bridge.prepare_inspection('# Proof\n$x=x$')
        self.assertTrue(prepared['ok'],prepared)
        self.assertFalse(prepared['result']['checks_executed'])
        self.assertTrue(server.prepare_inspection('# Proof\n$x=x$')['ok'])
        unified=server.review_manuscript('# Proof\n$x=x$',prepare_inputs=True)
        self.assertIn('preparation',unified['result']['modules'])
        research={'schema_version':'1.0','checks':[{'id':'p','kind':'power_analysis','design':'paired_t','mode':'calculate','nobs':34,'effect_size':'.5','alpha':'.05'}]}
        response=server.verify_toolkit(json.dumps(research))
        self.assertTrue(response['ok'],response)
        self.assertEqual(response['result']['checks'][0]['status'],'CALCULATED')
