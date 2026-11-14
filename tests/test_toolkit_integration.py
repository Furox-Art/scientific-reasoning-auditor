"""Toolkit transport, source binding and separate output guarantees."""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sra.cli import main
from sra.document import load_document, SourceIdentityError
from sra.review import review_manuscript
from sra.review_report import review_markdown
from sra.toolkit import verify_toolkit_spec
from test_toolkit import problem, polynomial, passage


class ToolkitIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.paper=self.root/'paper.md'
        self.paper.write_text('# Proof\nA polynomial identity is proposed.\n',encoding='utf-8')
        self.doc=load_document(self.paper)
        self.spec=problem(polynomial())
        self.spec.update(source_sha256=self.doc.sha256,extracted_text_sha256=hashlib.sha256(self.doc.text.encode()).hexdigest())
        self.input=self.root/'spec.json'
        self.input.write_text(json.dumps(self.spec))

    def call(self,*args):
        with patch('sys.argv',['sra',*map(str,args)]), contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return main()

    def test_cli_and_unified_api_report_findings_separately(self):
        original=self.paper.read_bytes(),self.input.read_bytes()
        self.assertEqual(self.call('verify-toolkit',self.input,'--manuscript',self.paper,'--out',self.root/'report'),0)
        report=json.loads((self.root/'report.json').read_text())
        self.assertEqual(report['source_binding']['status'],'source_matched')
        self.assertIn('Findings for the user',(self.root/'report.md').read_text(encoding='utf-8'))
        unified=review_manuscript(self.paper,toolkit_spec=self.spec)
        self.assertEqual(unified['modules']['toolkit']['result']['checks'][0]['status'],'VERIFIED')
        self.assertIn('Deterministic inspection toolkit',review_markdown(unified))
        self.assertEqual(self.call('review',self.paper,'--toolkit-spec',self.input,'--out',self.root/'combined'),0)
        self.assertEqual((self.paper.read_bytes(),self.input.read_bytes()),original)

    def test_partial_results_errors_and_output_aliases(self):
        with patch('sra.toolkit._backend',side_effect=ImportError('private')):
            self.assertEqual(self.call('verify-toolkit',self.input,'--out',self.root/'partial'),1)
            self.assertEqual(review_manuscript(self.paper,toolkit_spec=self.spec)['execution_status'],'partial')
        for output in (self.paper,self.input):
            with self.assertRaises(SystemExit):
                self.call('verify-toolkit',self.input,'--manuscript',self.paper,'--out',output)
        (self.root/'alias.json').write_text('existing')
        os.link(self.root/'alias.json',self.root/'alias.md')
        with self.assertRaises(SystemExit):
            self.call('verify-toolkit',self.input,'--out',self.root/'alias')
        self.input.write_text('[]')
        with self.assertRaises(SystemExit):
            self.call('verify-toolkit',self.input,'--out',self.root/'bad')
        self.assertFalse((self.root/'bad.json').exists())

    def test_source_binding_and_preflight_before_external_requests(self):
        with self.assertRaises(SourceIdentityError):
            verify_toolkit_spec(problem(polynomial()),self.doc)
        with patch('sra.doi._lookup_registry') as network,patch('sra.paper_review.request_single_model_review') as model:
            with self.assertRaises(ValueError):
                review_manuscript(self.paper,toolkit_spec={**self.spec,'checks':[]},online=True,send_to_model=True,model='fake')
        network.assert_not_called()
        model.assert_not_called()
        self.spec['checks']=[{'id':'sentences','kind':'claim_candidates'}]
        result=verify_toolkit_spec(self.spec,self.doc)
        self.assertEqual(result['checks'][0]['status'],'CANDIDATES')
        with self.assertRaises(ValueError):
            verify_toolkit_spec({**self.spec,'checks':[{'id':'s','kind':'claim_candidates','text':'Alternate source.'}]},self.doc)
        self.spec['checks']=[{'id':'citations','kind':'citation_match','claim':'Absent query','passages':[passage('Absent query')]}]
        with self.assertRaises(SourceIdentityError):
            verify_toolkit_spec(self.spec,self.doc)
