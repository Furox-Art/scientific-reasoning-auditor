"""Local toolkit transport returns findings without editing uploaded content."""
import asyncio
import hashlib
import json
import unittest
from pathlib import Path
from mcp_server import bridge,server


class MCPToolkitTests(unittest.TestCase):
    def test_scientific_method_audits_survive_transport_with_scoped_verdicts(self):
        path = Path(__file__).parents[2] / 'examples/method-audits.json'
        response = server.verify_toolkit(path.read_text())
        self.assertTrue(response['ok'], response)
        rows = response['result']['checks']
        self.assertEqual([row['status'] for row in rows], ['CANDIDATES', 'VERIFIED', 'VERIFIED', 'VERIFIED'])
        for row, field in zip(rows, ('scientific_novelty', 'literature_adequacy', 'measurement_validity', 'method_appropriateness')):
            self.assertEqual(row['details'][field], 'NOT_ASSESSED')
        spec = json.loads(path.read_text())
        spec['checks'][2]['normal_differences'] = None
        result = server.verify_toolkit(json.dumps(spec))
        self.assertTrue(result['ok'], result)
        self.assertEqual(result['result']['checks'][2]['status'], 'UNDETERMINED')
        self.assertEqual(result['result']['execution_status'], 'partial')

    def test_literal_source_preparation_keeps_unknown_assumptions(self):
        content = 'X^(2) = 7.66, df = 2, P = 0.02; X²(2) = 11.54, P < .01'
        response = server.prepare_inspection(content)
        self.assertTrue(response['ok'], response)
        prepared = response['result']
        rows = [row for row in prepared['candidates'] if row.get('suggested_check')]
        self.assertEqual([row['suggested_check']['statistic'] for row in rows], ['7.66', '11.54'])
        self.assertFalse(prepared['checks_executed'])
        for row in rows:
            self.assertEqual(content[row['start']:row['end']], row['source_quote'])
            self.assertEqual(row['suggested_check']['alternative'], 'unknown')
            self.assertEqual(row['suggested_check']['df_precision'], 'unknown')
        result = server.verify_toolkit(json.dumps(prepared['proposed_toolkit_specs'][0]))
        self.assertTrue(result['ok'], result)
        self.assertEqual([row['status'] for row in result['result']['checks']], ['UNDETERMINED'] * 2)

    def test_declared_statistical_context_survives_real_transport(self):
        base=dict(kind='statistic_consistency',test='t',df=[1],
                  statistic='2.000000000000',reported_p='.147584')
        spec={'schema_version':'1.0','checks':[
            dict(base,id='one_sided',alternative='greater'),
            dict(base,id='unknown',alternative='unknown'),
            dict(base,id='fractional',test='F',df=['2','.5'],df_precision='exact',reported_p='.577350')]}
        response=server.verify_toolkit(json.dumps(spec))
        self.assertTrue(response['ok'],response)
        result=response['result']
        self.assertEqual([r['status'] for r in result['checks']],['VERIFIED','UNDETERMINED','VERIFIED'])
        self.assertEqual(result['execution_status'],'partial')
        self.assertFalse(result['checks'][2]['details']['correction_method_verified'])

    def test_grouped_methods_survive_real_transport(self):
        path=Path(__file__).parents[2]/'examples/grouped-methods.json'
        response=server.verify_toolkit(path.read_text(encoding='utf-8'))
        self.assertTrue(response['ok'],response)
        rows=response['result']['checks']
        self.assertEqual([r['status'] for r in rows],['CALCULATED']*3)
        self.assertAlmostEqual(rows[0]['details']['tau_squared'],3.5,places=5)
        self.assertEqual(rows[1]['details']['p_denominator'],16)
        self.assertEqual(rows[2]['details']['inference_df'],22)

    def test_cr2_cr3_options_survive_real_transport(self):
        path=Path(__file__).parents[2]/'examples/dependent-data.json'
        spec=json.loads(path.read_text(encoding='utf-8'))
        base=spec['checks'][0]
        spec['checks']=[dict(base,id='cr2',covariance_method='CR2'),dict(base,id='cr3',covariance_method='CR3')]
        response=server.verify_toolkit(json.dumps(spec))
        self.assertTrue(response['ok'],response)
        rows=response['result']['checks']
        self.assertEqual([r['status'] for r in rows],['CALCULATED']*2)
        self.assertEqual([r['details']['covariance_method'] for r in rows],['CR2','CR3'])
        self.assertTrue(all(not r['details']['small_cluster_inference_certified'] for r in rows))

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
