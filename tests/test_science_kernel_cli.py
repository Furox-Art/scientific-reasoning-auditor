"""Read-only standalone proof commands and safe English reports."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sra.cli import main
from sra.science_kernel import prove_science
from sra.science_kernel_cli import science_proof_markdown

ROOT=Path(__file__).parents[1]


class ProofCLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.spec=self.root/'problem.json'
        self.spec.write_bytes((ROOT/'examples/scientific-proof.json').read_bytes())

    def call(self,*args):
        with patch('sys.argv',['sra',*map(str,args)]),contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return main()

    def test_prover_and_verifier_create_separate_reports_without_mutation(self):
        original=self.spec.read_bytes()
        self.assertEqual(self.call('prove-science',self.spec,'--out',self.root/'proof'),0)
        certificate=self.root/'proof.json'
        self.assertNotIn(b'\r\n',certificate.read_bytes())
        report=json.loads(certificate.read_text())
        self.assertEqual(report['claims'][1]['status'],'UNRESOLVED')
        self.assertEqual(self.call('verify-science-certificate',self.spec,certificate,'--out',self.root/'checked'),0)
        self.assertTrue(json.loads((self.root/'checked.json').read_text())['valid'])
        report['claims'][0]['status']='CONTRADICTED';certificate.write_text(json.dumps(report))
        self.assertEqual(self.call('verify-science-certificate',self.spec,certificate,'--out',self.root/'invalid'),1)
        self.assertIn('Valid: False',(self.root/'invalid.md').read_text())
        self.assertEqual(self.spec.read_bytes(),original)

    def test_inputs_and_hardlinked_outputs_are_protected_before_analysis(self):
        original=self.spec.read_bytes()
        with self.assertRaises(SystemExit):self.call('prove-science',self.spec,'--out',self.spec)
        output=self.root/'aliased.json';output.write_text('preserve')
        os.link(output,self.root/'aliased.md')
        with self.assertRaises(SystemExit):self.call('prove-science',self.spec,'--out',self.root/'aliased')
        self.assertEqual(output.read_text(),'preserve')
        self.assertEqual(self.spec.read_bytes(),original)

    def test_bad_empty_oversized_missing_and_non_utf8_files_fail_safely(self):
        for data in (b'',b'not JSON',b'x'*(1024*1024+1),b'\xff'):
            self.spec.write_bytes(data)
            with self.subTest(size=len(data)),self.assertRaises(SystemExit) as caught:
                self.call('prove-science',self.spec,'--out',self.root/'failed')
            self.assertEqual(caught.exception.code,2)
        self.assertFalse((self.root/'failed.json').exists())
        with self.assertRaises(SystemExit):self.call('prove-science',self.root/'absent','--out',self.root/'failed')

    def test_evidence_and_untrusted_markdown_are_visible_but_escaped(self):
        spec=json.loads(self.spec.read_text())
        source=spec['sources'][0]
        source['text']='<script>danger</script>\n'
        import hashlib
        source['sha256']=hashlib.sha256(source['text'].encode()).hexdigest()
        for fact in spec['facts']:
            if fact['origin']=='evidence':fact['source_refs']=[dict(source_id=source['id'],quote='<script>danger</script>',start=0)]
        text=science_proof_markdown(prove_science(spec))
        self.assertNotIn('<script>',text)
        self.assertIn('&lt;script&gt;',text)
        for field in ('Statement:','Premises and source evidence','Rule assumptions','Source snapshots','Native exact arithmetic','Counter-world:'):
            self.assertIn(field,text)
