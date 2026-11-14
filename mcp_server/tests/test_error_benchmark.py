"""Real MCP wrappers, synthetic labels only."""
import json
import unittest
from pathlib import Path
from mcp_server import server


class ErrorBenchmarkTransportTests(unittest.TestCase):
    def test_run_template_evaluation_and_invalid_inputs(self):
        root=Path(__file__).parents[2]/'examples/error_benchmark'
        manifest=(root/'synthetic.json').read_text()
        labels=(root/'synthetic-labels.json').read_text()
        run=server.benchmark_errors(manifest)
        self.assertTrue(run['ok'],run)
        template=server.error_label_template(manifest)
        self.assertTrue(template['ok'],template)
        self.assertIsNone(template['result']['cases'][0]['reviewers'][0]['label'])
        result=server.evaluate_errors(manifest,json.dumps(run['result']),labels)
        self.assertTrue(result['ok'],result)
        self.assertEqual(result['result']['summary']['metrics']['end_to_end_recall']['value'],1/3)
        exact=server.benchmark_errors((root/'numeric-boundary.json').read_text())
        self.assertTrue(exact['ok'],exact)
        self.assertEqual(exact['result']['cases'][0]['prediction'],'error')
        for response in [server.benchmark_errors('[]'),server.error_label_template('{}'),
                         server.benchmark_errors('{"v":1e9999999999999999999999999999}'),
                         server.evaluate_errors(manifest,'{}',labels),
                         server.evaluate_errors(manifest,json.dumps(run['result']),json.dumps(template['result']))]:
            self.assertFalse(response['ok'],response)
