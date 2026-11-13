"""New scientific methods remain conditional, bounded and read-only."""
import copy
import hashlib
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from sra.toolkit import verify_toolkit_spec
from sra.toolkit_spec import prepare_toolkit_spec


def spec(item):
    return {'schema_version':'1.0','checks':[item]}


class ResearchMethodTests(unittest.TestCase):
    def check(self,item):
        return verify_toolkit_spec(spec(item))['checks'][0]

    def test_causal_backdoor_and_graph_sensitivity_are_conditional(self):
        item={'id':'causal','kind':'causal_graph','nodes':['U','T','Y'],'edges':[['U','T'],['U','Y'],['T','Y']],
              'treatment':'T','outcome':'Y','observed':['U','T','Y'],'adjustment':['U']}
        result=self.check(item)
        self.assertEqual(result['status'],'VERIFIED')
        self.assertFalse(result['details']['model_assumptions_confirmed'])
        self.assertEqual(self.check({**item,'adjustment':[]})['status'],'REFUTED')
        hidden={**item,'observed':['T','Y'],'adjustment':[]}
        self.assertFalse(self.check(hidden)['details']['backdoor_adjustment_available'])
        sensitive={**hidden,'edges':[['T','Y']],'sensitivity_edges':[['U','T'],['U','Y']]}
        self.assertFalse(self.check(sensitive)['details']['sensitivity']['adjustment_valid'])

    def test_bias_evidence_never_certifies_low_risk(self):
        domains={k:{'judgment':'unknown','source_quote':None} for k in
                 ('randomization','allocation_concealment','blinding','missing_outcomes','selective_reporting')}
        domains['blinding']={'judgment':'concern','source_quote':'The study was open label.'}
        result=self.check({'id':'bias','kind':'bias_assessment','domains':domains})
        self.assertEqual(result['status'],'CANDIDATES')
        self.assertEqual(result['details']['concerns_reported'],['blinding'])
        self.assertFalse(result['details']['expert_certification'])

    def test_power_and_integer_sample_size(self):
        item={'id':'power','kind':'power_analysis','design':'independent_t','mode':'sample_size','effect_size':'.5','alpha':'.05','target_power':'.8'}
        result=self.check(item)
        self.assertEqual(result['status'],'CALCULATED')
        self.assertEqual(result['details']['n_group1'],64)
        self.assertEqual(result['details']['n_group2'],64)
        self.assertGreaterEqual(result['details']['power'],.8)
        paired={**item,'design':'paired_t'}
        self.assertEqual(self.check(paired)['details']['n_pairs'],34)
        calculated={**item,'mode':'calculate','nobs':64}
        calculated.pop('target_power')
        self.assertEqual(self.check({**calculated,'reported_power':'.99'})['status'],'REFUTED')

    def test_meta_analysis_uses_declared_scale_and_sensitivity(self):
        item={'id':'meta','kind':'meta_analysis','effect_scale':'mean_difference','model':'random',
              'studies':[{'id':'a','effect':'.1','variance':'.02'},{'id':'b','effect':'.5','variance':'.02'},{'id':'c','effect':'1','variance':'.03'}]}
        result=self.check(item)
        self.assertEqual(result['status'],'CALCULATED')
        self.assertGreater(result['details']['tau_squared'],0)
        self.assertEqual(len(result['details']['leave_one_out']),3)
        self.assertFalse(result['details']['publication_bias_proven'])

    def test_mcmc_diagnostics_flag_shifted_chains_and_abstain_on_constants(self):
        import numpy as np
        draws=np.random.default_rng(42).normal(size=(4,500))
        item={'id':'chains','kind':'bayesian_diagnostics','chains':draws.tolist()}
        result=self.check(item)
        self.assertEqual(result['status'],'CALCULATED')
        self.assertFalse(result['details']['posterior_correctness_proven'])
        draws[0]+=5
        self.assertIn('rhat_exceeds_threshold',self.check({**item,'chains':draws.tolist()})['details']['flags'])
        self.assertEqual(self.check({**item,'chains':[[1]*20,[1]*20]})['status'],'UNDETERMINED')

    def test_ml_split_manifest_detects_overlap_fit_group_and_time_leakage(self):
        item={'id':'ml','kind':'ml_validation','samples':[{'id':'a','group':'g1','time':1},{'id':'b','group':'g2','time':2}],
              'splits':{'train':['a'],'test':['b']},'preprocessing_fit_ids':['a'],'group_exclusive':True,'temporal':True}
        result=self.check(item)
        self.assertEqual(result['details']['protocol_status'],'no_violations_detected')
        bad=copy.deepcopy(item)
        bad['splits']['test']=['a','b']
        bad['preprocessing_fit_ids']=['a','b']
        result=self.check(bad)
        self.assertIn('sample_overlap',result['details']['violations'])
        self.assertIn('preprocessing_fit_outside_train',result['details']['violations'])

    def test_publication_snapshot_distinguishes_article_from_notice(self):
        original={'id':'pub','kind':'publication_status','doi':'10.1000/paper',
                  'message':{'DOI':'10.1000/paper','updated-by':[{'DOI':'10.1000/notice','type':'retraction'}]}}
        self.assertEqual(self.check(original)['details']['publication_status'],'RETRACTION_REPORTED')
        notice={**original,'doi':'10.1000/notice','message':{'DOI':'10.1000/notice','update-to':[{'DOI':'10.1000/paper','type':'retraction'}]}}
        self.assertEqual(self.check(notice)['details']['publication_status'],'RETRACTION_NOTICE')
        clean={**original,'message':{'DOI':'10.1000/paper'}}
        self.assertEqual(self.check(clean)['details']['publication_status'],'NO_UPDATES_REPORTED')
        self.assertFalse(self.check(clean)['details']['absence_proves_no_updates'])

    def test_falsey_malformed_update_collections_cannot_look_clear(self):
        for malformed in ({},'',False,0):
            item={'id':'pub','kind':'publication_status','doi':'10.1000/paper','message':{'DOI':'10.1000/paper','updated-by':malformed}}
            with self.subTest(malformed=malformed),self.assertRaises(ValueError):
                prepare_toolkit_spec(spec(item))

    def test_strict_research_preflight(self):
        causal={'id':'c','kind':'causal_graph','nodes':['T','Y'],'edges':[['T','Y']],'observed':['T','Y'],'adjustment':[],'treatment':'T','outcome':'Y'}
        domains={k:{'judgment':'unknown','source_quote':None} for k in ('randomization','allocation_concealment','blinding','missing_outcomes','selective_reporting')}
        bias={'id':'b','kind':'bias_assessment','domains':domains}
        power={'id':'p','kind':'power_analysis','design':'independent_t','mode':'calculate','nobs':50,'effect_size':'.5','alpha':'.05'}
        meta={'id':'m','kind':'meta_analysis','model':'random','effect_scale':'mean_difference','studies':[{'id':'a','effect':'.1','variance':'.01'},{'id':'b','effect':'.2','variance':'.02'}]}
        bayes={'id':'b','kind':'bayesian_diagnostics','chains':[[1]*20,[2]*20]}
        ml={'id':'s','kind':'ml_validation','samples':[{'id':'a'},{'id':'b'}],'splits':{'train':['a'],'test':['b']}}
        invalid=[{**causal,'nodes':['T','T']},{**causal,'edges':[['T','T']]},{**causal,'edges':[['T','Y'],['Y','T']]},
                 {**causal,'treatment':'Y'},{**causal,'adjustment':['Y']},{**causal,'observed':['T','T']},
                 {**bias,'domains':{**domains,'blinding':{'judgment':'low','source_quote':'Evidence'}}},
                 {**bias,'domains':{**domains,'blinding':{'judgment':'concern','source_quote':None}}},
                 {**power,'alpha':1},{**power,'design':'other'},{**power,'nobs':True},
                 {**power,'design':'paired_t','ratio':2},
                 {'id':'p','kind':'power_analysis','design':'paired_t','mode':'sample_size','effect_size':'.5','alpha':'.05','target_power':'.01'},
                 {**meta,'model':'unknown'},{**meta,'studies':[]},{**meta,'studies':[meta['studies'][0]]*2},{**meta,'asymmetry':1},
                 {**bayes,'chains':[[1]*20]}, {**bayes,'chains':[[1]*20,[1]*21]},
                 {**ml,'samples':[]},{**ml,'samples':[{'id':'a'},{'id':'a'}]},
                 {**ml,'splits':{'train':[],'test':['b']}},{**ml,'temporal':1}]
        for item in invalid:
            with self.subTest(item=item),self.assertRaises(ValueError):
                prepare_toolkit_spec(spec(item))
        from sra.document import parse_document_text,SourceIdentityError
        document=parse_document_text('Some other text.',source='paper.md',sha256='0'*64)
        from sra.research_spec import prepare_research
        with self.assertRaises(SourceIdentityError):
            prepare_research({**bias,'domains':{**domains,'blinding':{'judgment':'concern','source_quote':'Absent evidence','note':'Review this.'}}},document)
        row=self.check({**bias,'domains':{**domains,'blinding':{'judgment':'unknown','source_quote':None,'note':'Not reported.'}}})
        self.assertEqual(row['status'],'CANDIDATES')

    def test_numeric_solver_failures_cannot_award_calculated_results(self):
        power={'id':'p','kind':'power_analysis','design':'independent_t','mode':'sample_size','effect_size':'.5','alpha':'.05','target_power':'.8'}
        with patch('statsmodels.stats.power.TTestIndPower.solve_power',return_value=1000001):
            self.assertEqual(self.check(power)['status'],'FAILED')
        with patch('statsmodels.stats.power.TTestIndPower.power',return_value=.4),patch('statsmodels.stats.power.TTestIndPower.solve_power',return_value=64):
            self.assertEqual(self.check(power)['status'],'FAILED')
        large={**power,'mode':'calculate','nobs':1000000,'ratio':100}
        large.pop('target_power')
        self.assertEqual(self.check(large)['status'],'FAILED')
        meta={'id':'m','kind':'meta_analysis','model':'random','effect_scale':'mean_difference','studies':[{'id':'a','effect':'.1','variance':'.01'},{'id':'b','effect':'1','variance':'.02'}]}
        with patch('statsmodels.stats.meta_analysis.combine_effects',return_value=SimpleNamespace(tau2=10000)):
            self.assertEqual(self.check(meta)['status'],'FAILED')

    def test_more_meta_diagnostics_and_both_mcmc_interfaces(self):
        studies=[{'id':f's{i}','effect':str(.2+.03*i+.02*(i%3)),'variance':str(.01+.003*i)} for i in range(10)]
        item={'id':'meta','kind':'meta_analysis','model':'random','effect_scale':'log_risk_ratio','tau_method':'dersimonian_laird','studies':studies,'asymmetry':True}
        result=self.check(item)
        self.assertEqual(result['status'],'CALCULATED')
        self.assertEqual(result['details']['asymmetry']['status'],'calculated')
        small={**item,'model':'fixed','studies':studies[:2]}
        self.assertEqual(self.check(small)['details']['asymmetry']['status'],'undetermined')
        from sra.research_checks import bayesian_diagnostics
        from sra.research_spec import prepare_research
        legacy=SimpleNamespace(__name__='arviz',rhat=lambda *a,**kw:1.0,ess=lambda *a,**kw:800.0)
        prepared=prepare_research({'id':'b','kind':'bayesian_diagnostics','chains':[[1]*20,[2]*20]},None)
        self.assertEqual(bayesian_diagnostics(prepared,legacy)[0],'CALCULATED')
        # Exercise the modern adapter contract even on Python 3.11, where only
        # legacy ArviZ is installable. Real selected-backend diagnostics above
        # independently test numerical behavior on each CI runtime.
        calls=[]
        def statistic(value,**kwargs):
            calls.append(kwargs)
            return 1.0 if kwargs['method']=='rank' else 800.0
        array_api=SimpleNamespace(rhat=statistic,ess=statistic)
        modern=SimpleNamespace(__name__='arviz_stats')
        with patch.dict('sys.modules',{'arviz_stats':modern,
                'arviz_stats.base':SimpleNamespace(array_stats=array_api)}):
            status,details=bayesian_diagnostics(prepared,modern)
        self.assertEqual(status,'CALCULATED')
        self.assertEqual(details['flags'],[])
        self.assertEqual(calls,[{'method':'rank','chain_axis':0,'draw_axis':1},
            {'method':'bulk','chain_axis':0,'draw_axis':1},
            {'method':'tail','prob':(.05,.95),'chain_axis':0,'draw_axis':1}])

    def test_ml_missing_manifest_fields_and_descendant_adjustment_are_visible(self):
        item={'id':'ml','kind':'ml_validation','samples':[{'id':'a'},{'id':'b'}],'splits':{'train':['a'],'test':['b']},'group_exclusive':True,'temporal':True}
        details=self.check(item)['details']
        self.assertIn('missing_group_ids',details['unassessed_checks'])
        self.assertIn('missing_timestamps',details['unassessed_checks'])
        self.assertIn('preprocessing_fit_not_supplied',details['unassessed_checks'])
        same_group={**item,'samples':[{'id':'a','group':'g','time':2},{'id':'b','group':'g','time':1}]}
        self.assertIn('group_overlap',self.check(same_group)['details']['violations'])
        self.assertIn('temporal_order_violation',self.check(same_group)['details']['violations'])
        dag={'id':'c','kind':'causal_graph','nodes':['T','Y','M'],'edges':[['T','M'],['M','Y']],'observed':['T','Y','M'],'adjustment':['M'],'treatment':'T','outcome':'Y'}
        self.assertEqual(self.check(dag)['status'],'REFUTED')

    def test_snapshot_types_directions_and_malformed_identity(self):
        base={'id':'p','kind':'publication_status','doi':'10.1000/paper','message':{'DOI':'10.1000/paper'}}
        for typ,label in (('partial-retraction','PARTIAL_RETRACTION'),('withdrawal','WITHDRAWAL'),('removal','REMOVAL')):
            for field,suffix in (('updated-by','REPORTED'),('update-to','NOTICE')):
                with self.subTest(update_type=typ,direction=field):
                    item={**base,'message':{**base['message'],field:[{'DOI':'10.1000/notice','type':typ}]}}
                    self.assertEqual(self.check(item)['details']['publication_status'],label+'_'+suffix)
        for typ,status in (('correction','CORRECTION_REPORTED'),('expression_of_concern','CONCERN_REPORTED'),('new-version','UPDATES_REPORTED')):
            self.assertEqual(self.check({**base,'message':{**base['message'],'updated-by':[{'DOI':'10.1000/notice','type':typ}]}})['details']['publication_status'],status)
        notice={**base,'message':{**base['message'],'update-to':[{'DOI':'10.1000/other','type':'correction'}]}}
        self.assertEqual(self.check(notice)['details']['publication_status'],'UPDATE_NOTICE')
        for message in ({'DOI':'10.1000/wrong'},{**base['message'],'updated-by':[{}]},
                        {**base['message'],'updated-by':[{'DOI':'bad','type':'correction'}]}):
            with self.assertRaises(ValueError):
                prepare_toolkit_spec(spec({**base,'message':message}))

    def test_numerical_environment_can_record_missing_optional_packages(self):
        import importlib.metadata
        from sra.toolkit import _numerical_environment
        with patch('sra.toolkit.importlib.metadata.version',side_effect=importlib.metadata.PackageNotFoundError('optional')):
            environment=_numerical_environment()
        self.assertTrue(all(v is None for v in environment['packages'].values()))
        self.assertTrue(environment['python'])

    def test_fractional_snapshot_metadata_keeps_numeric_types_and_stable_hashes(self):
        from sra.publication import summarize_publication
        message={'DOI':'10.1000/paper','score':1.25,'extra':{'values':[.125,True,None,1,'1.25']}}
        item={'id':'p','kind':'publication_status','doi':'10.1000/paper','message':message}
        result=self.check(item)
        self.assertEqual(result['status'],'CANDIDATES')
        digest=result['details']['metadata_sha256']
        self.assertEqual(digest,summarize_publication(item['doi'],message)['metadata_sha256'])
        self.assertNotEqual(digest,self.check({**item,'message':{**message,'score':'1.25'}})['details']['metadata_sha256'])
        from sra.publication import _canonical_snapshot
        from decimal import Decimal
        for value in ({1:'value'},Decimal('NaN')):
            with self.assertRaises(ValueError):
                _canonical_snapshot(value)
        deep='leaf'
        for _ in range(66):
            deep=[deep]
        with self.assertRaises(ValueError):
            _canonical_snapshot(deep)

    def test_egger_abstains_on_ill_conditioning_and_probability_underflow(self):
        from decimal import Decimal
        narrow=[{'id':f's{i}','effect':str(Decimal('.2')+Decimal('.03')*i),
                 'variance':str(Decimal(1)+Decimal('1e-14')*(i%2))} for i in range(10)]
        underflow=[{'id':f's{i}','variance':str(.01+.001*i),'effect':str(100+2*(.01+.001*i)**.5)} for i in range(50)]
        for studies in (narrow,underflow):
            with self.subTest(study_count=len(studies)):
                item={'id':'m','kind':'meta_analysis','model':'fixed','effect_scale':'mean_difference','studies':studies,'asymmetry':True}
                result=self.check(item)
                self.assertEqual(result['status'],'UNDETERMINED')
                self.assertEqual(result['details']['asymmetry']['status'],'undetermined')
                self.assertNotIn('p_value',result['details']['asymmetry'])
                self.assertIn('estimate',result['details'])
