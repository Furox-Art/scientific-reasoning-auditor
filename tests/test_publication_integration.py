"""Crossref updates are directional and remain opt-in registry observations."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sra.doi import _lookup_crossref
from sra.review import review_manuscript
from sra.review_report import review_markdown


class Response(io.BytesIO):
    status=200


class PublicationIntegrationTests(unittest.TestCase):
    def test_one_registry_request_exposes_update_and_human_report(self):
        message={'DOI':'10.1000/paper','title':['Paper title'],
                 'updated-by':[{'DOI':'10.1000/notice','type':'retraction'}]}
        class Opener:
            calls=0
            def open(self,*args,**kwargs):
                self.calls+=1
                return Response(json.dumps({'message':message}).encode())
        opener=Opener()
        with patch('sra.doi.build_opener',return_value=opener):
            result=_lookup_crossref('10.1000/paper')
        self.assertEqual(opener.calls,1)
        self.assertEqual(result['publication_status']['publication_status'],'RETRACTION_REPORTED')
        with tempfile.TemporaryDirectory() as root:
            paper=Path(root)/'paper.md'
            paper.write_text('# References\nPaper title doi:10.1000/paper\n')
            before=paper.read_bytes()
            with patch('sra.doi.build_opener',return_value=opener):
                report=review_manuscript(paper,online=True)
            self.assertIn(r'RETRACTION\_REPORTED',review_markdown(report))
            self.assertEqual(paper.read_bytes(),before)
            with patch('sra.doi.build_opener') as network:
                review_manuscript(paper)
            network.assert_not_called()

    def test_malformed_update_metadata_cannot_look_clear(self):
        class Opener:
            def open(self,*args,**kwargs):
                return Response(json.dumps({'message':{'DOI':'10.1000/paper','title':['Paper title'],'updated-by':[{}]}}).encode())
        with patch('sra.doi.build_opener',return_value=Opener()):
            self.assertEqual(_lookup_crossref('10.1000/paper')['status'],'UNVERIFIED')
