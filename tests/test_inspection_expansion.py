"""Contracts for requested inspection areas 1–6; no manuscript mutation."""
import hashlib
import json
import unittest
import contextlib
import io
import tempfile
import subprocess
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from sra.document import parse_document_text
from sra.inspection import prepare_inspection
from sra.toolkit import verify_toolkit_spec
from sra.toolkit_spec import prepare_toolkit_spec


def spec(check):
    return {'schema_version':'1.0','checks':[check]}


def symbolic(left,right,kind='symbolic_identity',assumptions=None):
    item={'id':'math','kind':kind,'variables':{'x':assumptions or 'real'},'left':left,'right':right}
    if kind != 'symbolic_identity':
        item['variable']='x'
    return item


class ExpansionTests(unittest.TestCase):
    def check(self,item):
        return verify_toolkit_spec(spec(item))['checks'][0]

    def test_preparation_preserves_exact_offsets_and_never_silently_runs_candidates(self):
        text='# Methods\nAssume x is positive.\n$x**2 + 2*x + 1 = (x+1)**2$\nt(12) = 2.4, p = .03\n\nTable 1\n| Group | Count |\n|---|---|\n| A | 4 |\n\nFigure 1: Changes over time.\n'
        doc=parse_document_text(text,source='paper.md',sha256=hashlib.sha256(text.encode()).hexdigest())
        report=prepare_inspection(doc)
        self.assertEqual(report['extracted_text_sha256'],hashlib.sha256(text.encode()).hexdigest())
        self.assertEqual({r['kind'] for r in report['candidates']},{'assumption','equation','statistic','table','figure'})
        for item in report['candidates']:
            self.assertEqual(text[item['start']:item['end']],item['source_quote'])
            self.assertTrue(item['requires_confirmation'])
        eq=next(r for r in report['candidates'] if r['kind']=='equation')
        self.assertEqual(eq['suggested_check']['kind'],'symbolic_identity')
        self.assertFalse(report['checks_executed'])

    def test_symbolic_domains_and_exact_rewrites(self):
        for check in (symbolic('sin(x)**2+cos(x)**2','1'),symbolic('log(x**2)','2*log(x)',assumptions='positive'),
                      symbolic('x/x','1',assumptions='nonzero'),symbolic('log(x)','1/x','symbolic_derivative','positive'),
                      symbolic('cos(x)','sin(x)','symbolic_antiderivative')):
            self.assertEqual(self.check(check)['status'],'VERIFIED',check)
        self.assertEqual(self.check(symbolic('x/x','1'))['status'],'UNDETERMINED')
        self.assertEqual(self.check(symbolic('sqrt(x**2)','x'))['status'],'REFUTED')
        self.assertEqual(self.check(symbolic('log(x)','log(x)'))['status'],'UNDETERMINED')

    def test_nested_powers_and_hostile_symbolic_inputs_are_rejected_before_backend(self):
        for expression in ('(x**4)**4','sin(log(x))','x.__class__','__import__(x)','x**100','x+',
                           'sin(x)+cos(x)+exp(x)+sqrt(x)+log(x)','-'*12+'x','x+'*25+'x','(x+x+x+x+x)**4','1e99999'):
            with self.subTest(expression=expression),self.assertRaises(ValueError):
                prepare_toolkit_spec(spec(symbolic(expression,'x')))

    def test_regression_multiple_testing_missingness_and_assumptions(self):
        item={'id':'reg','kind':'statistical_analysis','operation':'linear_regression','x':[1,2,3,4],'y':[2,4,5,8]}
        result=self.check(item)
        self.assertEqual(result['status'],'CALCULATED')
        self.assertAlmostEqual(result['details']['computed']['slope'],1.9)
        self.assertEqual(self.check({**item,'y':[2,None,5,8]})['status'],'UNDETERMINED')
        self.assertEqual(self.check({**item,'y':[2,None,5,8],'missing_policy':'complete_case'})['status'],'CALCULATED')
        result=self.check({'id':'adjust','kind':'statistical_analysis','operation':'multiple_testing','p_values':['0.01','0.04','0.03'],'method':'holm'})
        self.assertEqual(result['details']['adjusted_p_values'],['0.03','0.06','0.06'])
        result=self.check({'id':'assumptions','kind':'statistical_analysis','operation':'assumption_diagnostics','groups':[[1,2,4,6],[2,4,5,7]]})
        self.assertEqual(result['status'],'CALCULATED')
        self.assertFalse(result['details']['assumptions_proven'])

    def test_reported_statistics_account_for_both_statistic_and_p_rounding(self):
        base={'id':'reported','kind':'statistic_consistency','test':'t','statistic':'2.400','df':[12],'reported_p':'0.03','relation':'='}
        self.assertEqual(self.check(base)['status'],'VERIFIED')
        self.assertEqual(self.check({**base,'reported_p':'0.5'})['status'],'REFUTED')
        self.assertEqual(self.check({**base,'statistic':'2.4'})['status'],'UNDETERMINED')
        self.assertEqual(self.check({**base,'reported_p':'0.05','relation':'<'})['status'],'VERIFIED')

    def test_context_retains_offsets_and_never_labels_semantic_support(self):
        text='Background.\nTreatment did not increase survival.\nThe sample was small.'
        item={'id':'context','kind':'citation_context','claim':'Treatment increased survival.','sources':[{'id':'study','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]}
        result=self.check(item)
        self.assertEqual(result['status'],'CANDIDATES')
        self.assertEqual(result['details']['support_status'],'NOT_ASSESSED')
        for row in result['details']['matches']:
            self.assertEqual(text[row['start']:row['end']],row['passage'])
        self.assertTrue(any(r['negation_cues'] for r in result['details']['matches']))

    def test_keyed_table_supplement_comparison_and_svg_review(self):
        item={'id':'data','kind':'table_compare','table_csv':'group,value\nA,1\nB,2\n','supplement_csv':'group,value\nB,2\nA,1\n','keys':['group']}
        self.assertEqual(self.check(item)['status'],'VERIFIED')
        self.assertEqual(self.check({**item,'supplement_csv':'group,value\nA,3\nB,2\n'})['status'],'REFUTED')
        svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><title>Measurements</title><text x="1" y="9">Time (s)</text><polyline points="1,2 3,4"/></svg>'
        result=self.check({'id':'figure','kind':'figure_svg','svg':svg})
        self.assertEqual(result['status'],'CANDIDATES')
        self.assertIn('Time (s)',result['details']['text_labels'])
        self.assertFalse(result['details']['scientific_visual_interpretation_verified'])

    def test_preparation_cli_and_unified_review_keep_manuscript_read_only(self):
        from sra.cli import main
        from sra.review import review_manuscript
        from sra.review_report import review_markdown
        with tempfile.TemporaryDirectory() as root:
            paper=Path(root)/'paper.md'
            paper.write_text('# Proof\n$x*x = x**2$\n',encoding='utf-8')
            before=paper.read_bytes()
            with patch('sys.argv',['sra','prepare-inspection',str(paper),'--out',str(Path(root)/'prepared')]),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(),0)
            result=review_manuscript(paper,prepare_inputs=True)
            self.assertIn('preparation',result['modules'])
            self.assertIn('Inspection input preparation',review_markdown(result))
            self.assertEqual(paper.read_bytes(),before)

    def test_malformed_svg_and_csv_are_structured_failures(self):
        with self.assertRaises(ValueError):
            prepare_toolkit_spec(spec({'id':'table','kind':'table_compare','keys':['id'],'table_csv':'id,x\n"A,1','supplement_csv':'id,x\nA,1'}))
        self.assertEqual(self.check({'id':'svg','kind':'figure_svg','svg':'<svg>'})['status'],'FAILED')

    def test_exact_symbolic_core_worker_and_budget_paths(self):
        from sra.symbolic import prepare_symbolic,compute_symbolic,worker,verify_symbolic
        for item,status in ((symbolic('sin(x)**2+cos(x)**2','1'),'VERIFIED'),
                            (symbolic('-x + +x','0'),'VERIFIED'),
                            (symbolic('x**-1*x','1',assumptions='nonzero'),'VERIFIED'),
                            (symbolic('exp(x)','exp(x)','symbolic_derivative'),'VERIFIED'),
                            (symbolic('sqrt(x)','1/(2*sqrt(x))','symbolic_derivative','positive'),'VERIFIED'),
                            (symbolic('x/2','x*0.5'),'VERIFIED'),
                            (symbolic('log(x**2)','2*log(x)',assumptions='positive'),'VERIFIED'),
                            (symbolic('log(x)','log(x)'),'UNDETERMINED'),
                            (symbolic('x/x','1'),'UNDETERMINED'),
                            (symbolic('sqrt(x**2)','x'),'REFUTED'),
                            (symbolic('sin(x)','0',assumptions='positive'),'REFUTED'),
                            (symbolic('x*(x-1)*(x+1)*(x-2)*(x+2)','0'),'UNDETERMINED'),
                            (symbolic('cos(x)','sin(x)','symbolic_antiderivative'),'VERIFIED')):
            with self.subTest(item=item):
                self.assertEqual(compute_symbolic(prepare_symbolic(item))[0],status)
        prepared=prepare_symbolic(symbolic('x','x'))
        output=io.StringIO()
        with patch('sys.stdin',io.StringIO(json.dumps(prepared))),patch('sys.stdout',output):
            worker()
        self.assertEqual(json.loads(output.getvalue())[0],'VERIFIED')
        with patch('sra.symbolic.subprocess.run',side_effect=subprocess.TimeoutExpired('worker',5)):
            self.assertEqual(verify_symbolic(prepared,None)[0],'UNDETERMINED')
        with patch('sra.symbolic.subprocess.run',return_value=SimpleNamespace(returncode=1,stdout='private')):
            self.assertEqual(self.check(symbolic('x','x'))['status'],'FAILED')

    def test_strict_new_input_contracts(self):
        sym=symbolic('x','x')
        reg={'id':'reg','kind':'statistical_analysis','operation':'linear_regression','x':[1,2,3],'y':[2,4,7]}
        adjust={'id':'p','kind':'statistical_analysis','operation':'multiple_testing','p_values':[0.1],'method':'holm'}
        diag={'id':'d','kind':'statistical_analysis','operation':'assumption_diagnostics','groups':[[1,2,3],[2,4,6]]}
        context={'id':'c','kind':'citation_context','claim':'Claim','sources':[{'id':'s','text':'Source.','sha256':hashlib.sha256(b'Source.').hexdigest()}]}
        table={'id':'t','kind':'table_compare','table_csv':'id,x\nA,1\n','supplement_csv':'id,x\nA,1\n','keys':['id']}
        statistic={'id':'s','kind':'statistic_consistency','test':'t','df':[10],'statistic':'2','reported_p':'.1'}
        invalid=[{**sym,'id':'bad-id'},{**sym,'variables':{}},{**symbolic('x','x','symbolic_derivative'),'variable':'y'},
                 {**reg,'x':[1]},{**reg,'missing_policy':'impute'}, {**adjust,'method':'unknown'},{**adjust,'p_values':[2]},
                 {**diag,'groups':[[1],[2]]},{**reg,'operation':'unknown'},
                 {**context,'sources':[]},{**context,'sources':[context['sources'][0]]*2},
                 {**context,'sources':[{'id':'s','text':'Wrong','sha256':'0'*64}]},
                 {**table,'table_csv':'id,id\nA,A'},{**table,'keys':['absent']},
                 {**table,'table_csv':'id,x\nA'},{**table,'table_csv':'id,x\nA,1\nA,2'},
                 {**table,'atol':-1},{'id':'s','kind':'figure_svg','svg':'<!DOCTYPE svg><svg/>'},
                 {**statistic,'df':[True]},{**statistic,'reported_p':'2'}]
        for item in invalid:
            with self.subTest(item=item),self.assertRaises(ValueError):
                prepare_toolkit_spec(spec(item))
        with self.assertRaises(ValueError):
            prepare_toolkit_spec({'schema_version':'1.0','checks':[{**sym,'id':f's{i}'} for i in range(9)]})

    def test_preparation_limits_code_fences_unsupported_notation_and_source_links(self):
        def doc(text):
            return parse_document_text(text,source='paper.md',sha256=hashlib.sha256(text.encode()).hexdigest())
        text='```\n$x=x$\n```\n$x^2=x*x$\n$?=?$\nt = 2, p = .03\n| id | x |\n| A | 1 |'
        report=prepare_inspection(doc(text))
        self.assertEqual(len([r for r in report['candidates'] if r['kind']=='equation']),2)
        self.assertIsNone(report['proposed_toolkit_spec'])
        self.assertEqual(report['candidates'][-1]['kind'],'table')
        for text in ('a'*200001,'Assume x.\n'*501):
            with self.assertRaises(ValueError):
                prepare_inspection(doc(text))
        from sra.extended_inspection import prepare_extra
        from sra.document import SourceIdentityError
        with self.assertRaises(SourceIdentityError):
            prepare_extra({'id':'c','kind':'citation_context','claim':'Absent','sources':[]},doc('Other text.'))
        from sra.review import review_document
        with self.assertRaises(ValueError):
            review_document(doc('Text'),prepare_inputs=1)

    def test_prepared_specs_are_batched_without_losing_candidates(self):
        text='$x=x$\n'*9
        doc=parse_document_text(text,source='paper.md',sha256=hashlib.sha256(text.encode()).hexdigest())
        report=prepare_inspection(doc)
        self.assertIsNone(report['proposed_toolkit_spec'])
        batches=report['proposed_toolkit_specs']
        self.assertEqual(len(batches),2)
        self.assertEqual(sum(len(batch['checks']) for batch in batches),9)
        for batch in batches:
            prepare_toolkit_spec(batch,doc)
        text='t(12) = 2.400, p = .03\n'*33
        doc=parse_document_text(text,source='paper.md',sha256=hashlib.sha256(text.encode()).hexdigest())
        batches=prepare_inspection(doc)['proposed_toolkit_specs']
        self.assertEqual([len(batch['checks']) for batch in batches],[32,1])

    def test_svg_event_and_css_indicators_are_not_reported_absent(self):
        for svg in ('<svg onload="alert(1)"/>','<svg><style>@import url(https://example.com/x.css);</style></svg>',
                    '<svg><rect style="fill:url(https://example.com/image)"/></svg>'):
            self.assertTrue(self.check({'id':'svg','kind':'figure_svg','svg':svg})['details']['external_or_active_content_present'])

    def test_analysis_diagnostics_context_limits_and_artifact_mismatches(self):
        for method,expected in (('bonferroni',['0.03','0.12','0.09']),('benjamini_hochberg',['0.03','0.04','0.04'])):
            row=self.check({'id':'p','kind':'statistical_analysis','operation':'multiple_testing','p_values':['.01','.04','.03'],'method':method})
            self.assertEqual(row['details']['adjusted_p_values'],expected)
        self.assertEqual(self.check({'id':'a','kind':'statistical_analysis','operation':'assumption_diagnostics','groups':[[1,1,1],[1,1,1]]})['status'],'UNDETERMINED')
        base={'id':'s','kind':'statistic_consistency','test':'z','df':[],'statistic':'1000','reported_p':'.001'}
        self.assertEqual(self.check(base)['status'],'UNDETERMINED')
        for test,df,value,relation,p,status in (('z',[],'2.400','>','.5','REFUTED'),('z',[],'0.100','>','.5','VERIFIED'),
                                             ('F',[2,20],'10.000','<','.05','VERIFIED'),('chi2',[2],'10.000','<','.0001','REFUTED')):
            self.assertEqual(self.check({**base,'test':test,'df':df,'statistic':value,'relation':relation,'reported_p':p})['status'],status)
        for text in ('word '*500,'X. '*2002):
            row=self.check({'id':'c','kind':'citation_context','claim':'word','sources':[{'id':'s','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}]})
            self.assertEqual(row['status'],'FAILED' if text.startswith('X.') else 'CANDIDATES')
        table={'id':'t','kind':'table_compare','table_csv':'id,text,x\nA,hello,1\nB,world,2',
               'supplement_csv':'id,text,other\nA,bye,1\nC,world,2','keys':['id']}
        self.assertGreaterEqual(self.check(table)['details']['mismatch_count'],3)
        for svg in ('<x/>','<svg>'+'<rect/>'*2001+'</svg>'):
            self.assertEqual(self.check({'id':'s','kind':'figure_svg','svg':svg})['status'],'FAILED')
        row=self.check({'id':'s','kind':'figure_svg','svg':'<svg><image href="https://invalid.example"/><script>alert(1)</script></svg>'})
        self.assertTrue(row['details']['external_or_active_content_present'])
