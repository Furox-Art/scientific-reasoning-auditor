"""Gold-label retrieval evaluation must not fabricate semantic accuracy."""
import json
import tempfile
import unittest
import contextlib
import io
from unittest.mock import patch
from pathlib import Path
from sra.evidence_benchmark import evaluate_scifact


class EvidenceBenchmarkTests(unittest.TestCase):
    def test_gold_document_is_never_injected_into_cited_candidates(self):
        with tempfile.TemporaryDirectory() as root:
            corpus=Path(root)/'corpus.jsonl'
            claims=Path(root)/'claims.jsonl'
            corpus.write_text('\n'.join(json.dumps(row) for row in [
                {'doc_id':1,'abstract':['Completely unrelated.']},{'doc_id':2,'abstract':['Treatment improved survival.']}]))
            claims.write_text(json.dumps({'id':1,'claim':'Treatment improved survival.','cited_doc_ids':[1],
                'evidence':{'2':[{'label':'SUPPORT','sentences':[0]}]}}))
            result=evaluate_scifact(corpus,claims)
            self.assertEqual(result['retrieval']['1']['gold_sentence_overlap_recall'],0)
            self.assertEqual(result['retrieval']['1']['gold_total'],1)
            self.assertEqual(result['gold_sentences_outside_cited_documents'],1)

    def test_gold_rationales_retrieval_and_semantic_abstention_are_separate(self):
        with tempfile.TemporaryDirectory() as root:
            corpus=Path(root)/'corpus.jsonl'
            claims=Path(root)/'claims.jsonl'
            corpus.write_text(json.dumps({'doc_id':1,'title':'Study','abstract':['Treatment improved survival.','The sample was small.'],'structured':False})+'\n')
            claims.write_text('\n'.join(json.dumps(r) for r in [
                {'id':1,'claim':'Treatment improved survival.','evidence':{'1':[{'label':'SUPPORT','sentences':[0]}]},'cited_doc_ids':[1]},
                {'id':2,'claim':'Unknown claim.','evidence':{},'cited_doc_ids':[1]}]))
            result=evaluate_scifact(corpus,claims)
            self.assertEqual(result['claims_in_file'],2)
            self.assertEqual(result['claims_with_gold_evidence'],1)
            self.assertEqual(result['retrieval']['1']['gold_sentence_overlap_recall'],1)
            self.assertEqual(result['semantic_verification']['predictions'],0)
            self.assertIsNone(result['semantic_verification']['accuracy'])
            self.assertEqual(result,evaluate_scifact(corpus,claims))
            from sra.cli import main
            with patch('sys.argv',['sra','benchmark-evidence',str(corpus),'--claims',str(claims),'--out',str(Path(root)/'result')]),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(),0)
            self.assertIn('Semantic prediction coverage: 0',(Path(root)/'result.md').read_text())

    def test_invalid_gold_provenance_and_coverage_are_not_silently_skipped(self):
        from sra.evidence_benchmark import _read_rows
        with tempfile.TemporaryDirectory() as root:
            corpus=Path(root)/'corpus.jsonl'
            claims=Path(root)/'claims.jsonl'
            record={'doc_id':1,'abstract':['A result.']}
            claim={'id':1,'claim':'Claim.','cited_doc_ids':[1],'evidence':{'1':[{'label':'SUPPORT','sentences':[0]}]}}
            def write(rows,path):
                path.write_text('\n'.join(json.dumps(r) for r in rows))
            write([record],corpus)
            write([claim],claims)
            for bad in ([],[[]],[{**record,'abstract':[]}],[record,record],[{**record,'abstract':['x'*10001]}],
                        [{**record,'abstract':['x'*10000]*11}]):
                write(bad,corpus)
                with self.subTest(bad=str(bad)[:40]),self.assertRaises(ValueError):
                    evaluate_scifact(corpus,claims)
            write([record],corpus)
            bad_claims=[{**claim,'claim':None},{**claim,'evidence':{'99':[{'label':'SUPPORT','sentences':[0]}]}},
                        {**claim,'evidence':{'1':[{'label':'UNKNOWN','sentences':[0]}]}},
                        {**claim,'evidence':{'1':[{'label':'SUPPORT','sentences':[2]}]}},
                        {**claim,'cited_doc_ids':[99]},{**claim,'evidence':{}}]
            for bad in bad_claims:
                write([bad],claims)
                with self.subTest(bad=bad),self.assertRaises(ValueError):
                    evaluate_scifact(corpus,claims)
            write([claim,claim],claims)
            with self.assertRaises(ValueError):
                evaluate_scifact(corpus,claims)
            with self.assertRaises(ValueError):
                _read_rows(corpus,1)
            write([{**record,'abstract':['.']}],corpus)
            write([claim],claims)
            result=evaluate_scifact(corpus,claims)
            self.assertEqual(result['retrieval']['1']['gold_sentence_overlap_recall'],0)
            self.assertIsNone(result['retrieval']['1']['window_overlap_precision'])
            from sra.cli import main
            with patch.dict('sys.modules',{'rapidfuzz':None}),patch('sys.argv',['sra','benchmark-evidence',str(corpus),'--claims',str(claims)]),contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code,2)
