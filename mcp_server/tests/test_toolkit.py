"""Local toolkit transport returns findings without editing uploaded content."""
import asyncio
import hashlib
import json
import unittest
from pathlib import Path
from mcp_server import bridge,server


class MCPToolkitTests(unittest.TestCase):
    def test_dependent_calculations_survive_real_transport(self):
        path=Path(__file__).parents[2]/'examples/dependent-data.json'
        response=server.verify_toolkit(path.read_text(encoding='utf-8'))
        self.assertTrue(response['ok'],response)
        rows=response['result']['checks']
        self.assertEqual([row['status'] for row in rows],['CALCULATED']*3)
        self.assertEqual(rows[0]['details']['inference_df'],3)
        self.assertAlmostEqual(rows[1]['details']['estimate'],2)
        self.assertEqual(rows[2]['details']['risk_difference_bounds']['lower_exact'],'-1/8')

    def test_evidence_operations_retain_differences_and_missing_records(self):
        path=Path(__file__).parents[2]/'examples/evidence-checks.json'
        response=server.verify_toolkit(path.read_text(encoding='utf-8'))
        self.assertTrue(response['ok'],response)
        rows=response['result']['checks']
        self.assertEqual([row['status'] for row in rows],['CANDIDATES','REFUTED','UNDETERMINED'])
        self.assertEqual(rows[0]['details']['sources'][0]['matched_tokens'],5)
        self.assertEqual(rows[1]['details']['differences'],1)
        self.assertEqual(rows[2]['details']['unassessed_checks'],['recruitment'])

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

    def test_modified_hksj_and_incomplete_manifest_survive_source_bound_transport(self):
        content='# Methods\nTwo independent study estimates and a partial ML manifest.\n'
        digest=hashlib.sha256(content.encode()).hexdigest()
        spec={'schema_version':'1.0','source_sha256':digest,'extracted_text_sha256':digest,'checks':[
            {'id':'meta','kind':'meta_analysis','model':'random','ci_method':'modified_hksj',
             'effect_scale':'mean_difference','studies':[{'id':'a','effect':0,'variance':1},{'id':'b','effect':0,'variance':1}]},
            {'id':'ml','kind':'ml_validation','samples':[{'id':'a'},{'id':'b'}],
             'splits':{'train':['a'],'test':['b']},'temporal':True}]}
        response=server.verify_toolkit(json.dumps(spec),content)
        self.assertTrue(response['ok'],response)
        result=response['result']
        self.assertEqual(result['source_binding']['status'],'source_matched')
        self.assertEqual(result['checks'][0]['details']['ci_method'],'modified_hksj')
        self.assertGreater(result['checks'][0]['details']['confidence_interval'][1],8.98)
        self.assertEqual(result['checks'][1]['details']['protocol_status'],'incomplete')
        self.assertEqual(result['manuscript_access'],'read_only')
