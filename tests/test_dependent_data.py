"""Synthetic numerical cross-checks, not empirical scientific validation."""
import copy
import itertools
import unittest
import tempfile
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch

from sra.toolkit import verify_toolkit_spec
from sra.toolkit_spec import prepare_toolkit_spec
from sra.toolkit_spec import digest
from sra.document import load_document, SourceIdentityError
from sra.review import review_manuscript


def clustered():
    return dict(id='cluster',kind='cluster_robust_regression',
                x=[[0],[1],[2],[0],[2],[4],[1],[3],[5],[0],[4],[6]],
                y=[1,2,4,2,4,5,2,5,8,0,6,7],
                clusters=['a']*3+['b']*3+['c']*3+['d']*3,terms=['exposure'],
                leave_one_cluster_out=True)


def correlated():
    return dict(id='correlated',kind='correlated_meta_analysis',effect_scale='mean_difference',
                studies=[dict(id='a',effect=1),dict(id='b',effect=3)],
                covariance=[[1,'.5'],['.5',1]])


def missing():
    return dict(id='missing',kind='missing_binary_sensitivity',
                treatment=dict(events=3,observed=5,missing=3),
                control=dict(events=1,observed=5,missing=3),threshold='0')


def run(item):
    return verify_toolkit_spec(dict(schema_version='1.0',checks=[item]))['checks'][0]


class DependentDataTests(unittest.TestCase):
    def test_cluster_cr1_matches_independent_statsmodels_and_original_units(self):
        import numpy as np
        from statsmodels.regression.linear_model import OLS
        from statsmodels.stats.sandwich_covariance import cov_cluster
        from scipy.stats import t
        item=clustered();row=run(item);details=row['details']
        self.assertEqual(row['status'],'CALCULATED')
        x=np.column_stack([np.ones(12),np.array(item['x'])])
        fit=OLS(item['y'],x).fit()
        reference=cov_cluster(fit,item['clusters'],use_correction=True)
        actual=details['coefficients']
        np.testing.assert_allclose([c['estimate'] for c in actual],fit.params,rtol=1e-11,atol=1e-12)
        np.testing.assert_allclose(details['covariance'],reference,rtol=1e-10,atol=1e-12)
        np.testing.assert_allclose([c['standard_error'] for c in actual],np.sqrt(np.diag(reference)),rtol=1e-10)
        self.assertEqual(details['inference_df'],3)
        self.assertAlmostEqual(details['correction_factor'],4/3*11/10)
        self.assertAlmostEqual(actual[1]['p_value'],2*t.sf(abs(fit.params[1]/np.sqrt(reference[1,1])),3))
        self.assertEqual(len(details['leave_one_cluster_out']),4)
        altered=copy.deepcopy(item);altered['x']=[[100+10*x[0]] for x in item['x']]
        transformed=run(altered)['details']['coefficients']
        self.assertAlmostEqual(transformed[1]['estimate'],actual[1]['estimate']/10)
        self.assertAlmostEqual(transformed[0]['estimate'],actual[0]['estimate']-10*actual[1]['estimate'])

    def test_cluster_rank_collapse_zero_uncertainty_and_omission_partial(self):
        item=clustered();item['x']=[[1]]*12
        self.assertEqual(run(item)['status'],'UNDETERMINED')
        item=clustered();item['x']=[['1000000000000.00000000001' if i%2 else '1000000000000'] for i in range(12)]
        # Keep values within the explicit magnitude bound.
        item['x']=[['999999999999.00000000001' if i%2 else '999999999999'] for i in range(12)]
        self.assertIn('input_values_collapse_in_float64',run(item)['details']['unassessed_checks'])
        item=clustered();item['y']=[0]*12
        row=run(item)
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertIsNone(row['details']['coefficients'][0]['p_value'])
        item=clustered();item['x']=[[1]]*3+[[0]]*9
        row=run(item)
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertTrue(any(r['status']=='UNDETERMINED' for r in row['details']['leave_one_cluster_out']))
        self.assertEqual(len(row['details']['coefficients']),2)

    def test_exact_affine_response_does_not_turn_roundoff_into_inference(self):
        for scale,offset in [(1.,3.),(1e-12,0.),(100.,10000.)]:
            item=clustered();item['y']=[offset+scale*row[0] for row in item['x']]
            row=run(item)
            self.assertEqual(row['status'],'UNDETERMINED')
            self.assertIn('residuals_below_numeric_resolution',row['details']['unassessed_checks'])
            self.assertIsNone(row['details']['covariance'])
            self.assertTrue(all(c['p_value'] is None and c['standard_error'] is None for c in row['details']['coefficients']))
            self.assertAlmostEqual(row['details']['coefficients'][1]['estimate']/scale,1.)

    def test_cancelled_cluster_scores_do_not_create_roundoff_significance(self):
        for slope,offset in itertools.product((2,1000,1e6),(3,1e8)):
            item=clustered();item['x']=[[x] for x in [0,1,2]*4]
            item['y']=[offset+slope*x+r for x,r in zip([0,1,2]*4,[1,-2,1]*4)]
            row=run(item)
            self.assertEqual(row['status'],'UNDETERMINED')
            self.assertIsNone(row['details']['covariance'])
            self.assertTrue(all(c['p_value'] is None and c['standard_error'] is None for c in row['details']['coefficients']))

    def test_correlated_gls_analytic_and_diagonal_pooling(self):
        import math
        row=run(correlated());self.assertEqual(row['status'],'CALCULATED');d=row['details']
        self.assertAlmostEqual(d['estimate'],2)
        self.assertAlmostEqual(d['standard_error'],math.sqrt(.75))
        self.assertAlmostEqual(d['q'],4)
        self.assertEqual(d['q_df'],1)
        self.assertEqual([r['estimate'] for r in d['leave_one_out']],[3,1])
        item=correlated();item['covariance']=[[1,0],[0,4]]
        d=run(item)['details']
        self.assertAlmostEqual(d['estimate'],1.4)
        self.assertAlmostEqual(d['standard_error'],math.sqrt(.8))
        item['studies'].reverse();item['covariance']=[[4,0],[0,1]]
        self.assertAlmostEqual(run(item)['details']['estimate'],d['estimate'])

    def test_covariance_scenarios_retain_baseline_and_negative_weights(self):
        item=correlated()
        item['covariance_scenarios']=[dict(id='singular',covariance=[[1,1],[1,1]]),dict(id='independent',covariance=[[1,0],[0,1]])]
        row=run(item);self.assertEqual(row['status'],'UNDETERMINED')
        self.assertAlmostEqual(row['details']['estimate'],2)
        self.assertEqual([r['status'] for r in row['details']['covariance_scenarios']],['UNDETERMINED','CALCULATED'])
        item=correlated();item['covariance']=[[1,'1.5'],['1.5',4]]
        d=run(item)['details']
        self.assertTrue(any(w<0 for w in d['weights']))
        self.assertEqual(run({**item,'covariance':[[1,1],[1,1]]})['status'],'UNDETERMINED')

    def test_correlated_effect_resolution_and_tail_underflow_abstain(self):
        item=correlated();item['studies'][0]['effect']='999999.000000000000001';item['studies'][1]['effect']='999999'
        self.assertEqual(run(item)['status'],'UNDETERMINED')
        with patch('scipy.stats.chi2.sf',return_value=0):
            row=run(correlated())
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertEqual(row['details']['estimate'],2)
        self.assertIsNone(row['details']['q_p_value'])

    def test_gls_q_is_stable_under_large_common_effect_translation(self):
        from decimal import Decimal
        item=correlated();delta=Decimal('0.00000095367431640625')
        item['studies']=[dict(id=f's{i}',effect=str(i*delta)) for i in range(3)]
        item['covariance']=[['1e-12' if i==j else 0 for j in range(3)] for i in range(3)]
        original=run(item)['details']
        for i,study in enumerate(item['studies']):study['effect']=str(Decimal(999999)+i*delta)
        shifted=run(item)['details']
        self.assertAlmostEqual(shifted['q'],original['q'],places=10)
        self.assertAlmostEqual(shifted['standard_error'],original['standard_error'])

    def test_sub_ulp_confidence_intervals_are_unassessed_without_losing_estimates(self):
        item=correlated();item['studies']=[dict(id='a',effect='999999'),dict(id='b',effect='999999')]
        item['covariance']=[['1e-12','-0.0000000000009999999997'],['-0.0000000000009999999997','1e-12']]
        row=run(item)
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertAlmostEqual(row['details']['estimate'],999999)
        self.assertIsNone(row['details']['confidence_interval'])
        self.assertIn('confidence_interval_resolution_lost',row['details']['unassessed_checks'])
        item=clustered();item['x']=[[0],[1]]*100;item['clusters']=[f'g{i}' for i in range(100) for _ in range(2)]
        item['leave_one_cluster_out']=False
        item['y']=[999999999990+x[0]+(.0001 if i//2%2 else -.0001) for i,x in enumerate(item['x'])]
        row=run(item)
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertIsNone(row['details']['coefficients'][0]['confidence_interval'])
        self.assertIn('confidence_interval_resolution_lost:intercept',row['details']['unassessed_checks'])

    def test_numeric_failures_preserve_only_usable_results(self):
        import numpy as np
        import scipy.linalg
        import warnings
        with patch('scipy.stats.t.sf',return_value=0):
            row=run(clustered())
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertTrue(all(c['p_value'] is None for c in row['details']['coefficients']))
        with patch('numpy.linalg.cond',return_value=1e11):
            row=run(correlated())
        self.assertIn('ill_conditioned_covariance',row['details']['unassessed_checks'])
        original=scipy.linalg.cho_factor
        def factor(matrix,*args,**kwargs):
            if len(matrix)==1:raise np.linalg.LinAlgError('simulated omission failure')
            return original(matrix,*args,**kwargs)
        with patch('scipy.linalg.cho_factor',side_effect=factor):
            row=run(correlated())
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertAlmostEqual(row['details']['estimate'],2)
        self.assertTrue(all(r['status']=='UNDETERMINED' for r in row['details']['leave_one_out']))
        def zero_solve(matrix,vector,*args,**kwargs):return np.zeros_like(vector)
        with patch('scipy.linalg.solve_triangular',side_effect=zero_solve):
            row=run(correlated())
        self.assertIn('nonpositive_pooling_information',row['details']['unassessed_checks'])
        def warning_tail(*args):
            warnings.warn('simulated numerical warning',RuntimeWarning)
            return .5
        with patch('scipy.stats.chi2.sf',side_effect=warning_tail):
            row=run(correlated())
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertNotIn('estimate',row['details'])

    def test_preflight_boundary_shapes_names_counts_and_limits(self):
        invalid=[]
        for key,value in [('clusters',[' a']*3+['b']*3+['c']*3+['d']*3),('terms',[]),('terms',['bad-name']),
                          ('x',[[0,0]]*12),('y',[None]*12)]:
            item=clustered();item[key]=value;invalid.append(item)
        item=clustered();item['x']=[[0]]*51;item['y']=[1]*51;item['clusters']=[str(i) for i in range(51)];invalid.append(item)
        item=correlated();item['covariance']=[[1,0]];invalid.append(item)
        item=correlated();item['studies'][1]['id']='a';invalid.append(item)
        item=correlated();item['covariance']=[[0,0],[0,1]];invalid.append(item)
        item=correlated();item['covariance_scenarios']=[dict(id='s',covariance=[[1,0],[0,1]])]*6;invalid.append(item)
        item=missing();item['treatment']['missing']=1000000;invalid.append(item)
        item=missing();item['threshold']='1.1';invalid.append(item)
        for item in invalid:
            with self.subTest(item=item),self.assertRaises(ValueError):prepare_toolkit_spec(dict(schema_version='1.0',checks=[item]))
        item=clustered();item.pop('terms');item['leave_one_cluster_out']=False
        self.assertEqual(run(item)['details']['coefficients'][1]['term'],'x1')

    def test_exact_missing_bounds_and_frontier_against_exhaustive_counts(self):
        item=missing();row=run(item);self.assertEqual(row['status'],'CALCULATED');d=row['details']
        values=[Fraction(3+a,8)-Fraction(1+b,8) for a,b in itertools.product(range(4),repeat=2)]
        self.assertEqual(d['risk_difference_bounds']['lower_exact'],str(min(values)))
        self.assertEqual(d['risk_difference_bounds']['upper_exact'],str(max(values)))
        self.assertEqual(d['threshold_status'],'depends_on_missing_outcomes')
        for frontier in d['tipping_frontier']:
            b=frontier['control_missing_events']
            possible=[a for a in range(4) if Fraction(3+a,8)-Fraction(1+b,8)>0]
            self.assertEqual(frontier['minimum_treatment_missing_events'],min(possible) if possible else None)
        item['threshold']='.25';item['control_missing_events_grid']=[0,1,2,3]
        d=run(item)['details']
        self.assertEqual(d['tipping_frontier'][0]['minimum_treatment_missing_events'],1)
        self.assertIsNone(d['tipping_frontier'][-1]['minimum_treatment_missing_events'])

    def test_missing_no_missingness_extreme_thresholds_and_large_counts(self):
        item=missing()
        for arm in ('treatment','control'):item[arm]['missing']=0
        d=run(item)['details']
        self.assertEqual(d['risk_difference_bounds']['lower_exact'],d['risk_difference_bounds']['upper_exact'])
        self.assertEqual(d['threshold_status'],'all_above_threshold')
        item['threshold']='1'
        self.assertEqual(run(item)['details']['threshold_status'],'none_above_threshold')
        item=missing();item['treatment']=dict(events=1,observed=2,missing=999998)
        self.assertLessEqual(len(run(item)['details']['tipping_frontier']),3)

    def test_strict_preflight_before_imports(self):
        invalid=[]
        for key,value in [('clusters',['a']*12),('clusters',['a']*3),('y',[1]*2),('x',[[1,2],[2]]),
                          ('terms',['intercept']),('leave_one_cluster_out',1),('alpha',0)]:
            item=clustered();item[key]=value;invalid.append(item)
        item=correlated();item['covariance']=[[1,'.5'],['.4',1]];invalid.append(item)
        item=correlated();item['covariance']=[[1,2],[2,1]];invalid.append(item)
        item=correlated();item['covariance_scenarios']=[dict(id='changed_diagonal',covariance=[[2,0],[0,1]])];invalid.append(item)
        item=missing();item['treatment']['events']=True;invalid.append(item)
        item=missing();item['control_missing_events_grid']=[0,0];invalid.append(item)
        item=missing();item['treatment']['events']=6;invalid.append(item)
        with patch('sra.toolkit._backend',side_effect=AssertionError('backend must not load')):
            for item in invalid:
                with self.subTest(item=item),self.assertRaises(ValueError):prepare_toolkit_spec(dict(schema_version='1.0',checks=[item]))

    def test_source_bound_criteria_and_error_evaluation_abstention(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'paper.md';text='# Methods\nRepeated observations and a declared covariance matrix.\n';path.write_text(text)
            doc=load_document(path)
            spec=dict(schema_version='1.0',source_sha256=doc.sha256,extracted_text_sha256=digest(doc.text),checks=[clustered(),correlated(),missing()])
            report=review_manuscript(path,toolkit_spec=spec,study_type='quantitative')
            rows={row['id']:row for row in report['criteria_matrix']['criteria']}
            for ident in ('statistical_inference','meta_analysis','robustness','missing_data'):
                self.assertEqual(rows[ident]['execution_status'],'checks_completed')
                self.assertEqual(rows[ident]['scientific_verdict'],'NOT_ASSESSED')
            spec['checks']=[dict(clustered(),leave_one_cluster_out=False)]
            report=review_manuscript(path,toolkit_spec=spec,study_type='quantitative')
            row=next(row for row in report['criteria_matrix']['criteria'] if row['id']=='robustness')
            self.assertNotEqual(row['execution_status'],'checks_completed')
            spec['source_sha256']='0'*64
            with self.assertRaises(SourceIdentityError):prepare_toolkit_spec(spec,doc)
            self.assertEqual(path.read_text(),text)
        from sra.error_benchmark import run_error_benchmark
        manifest=dict(schema_version='error-benchmark/1.0',dataset_id='synthetic',dataset_kind='synthetic',
                      papers=[dict(id='paper',group_id='paper',split='test',discipline='clinical',source_uri='synthetic:paper',license_note='Synthetic control.',text=text,sha256=digest(text))],
                      targets=[dict(id='target',kind='missing_binary_sensitivity',definition='Sensitivity counts are not reported-value agreement.')],
                      cases=[dict(id='missing',paper_id='paper',target_id='target',source_quote=text,check=missing())])
        result=run_error_benchmark(manifest)
        self.assertEqual(result['cases'][0]['prediction'],'abstain')

    def test_three_estimate_gls_and_dependency_preserving_omissions(self):
        import numpy as np
        item=correlated();item['studies'].append(dict(id='c',effect=-1));item['covariance']=[[2,'.3','.4'],['.3',1,'.2'],['.4','.2',3]]
        d=run(item)['details'];v=np.array(item['covariance'],dtype=float);e=np.array([1,3,-1.])
        w=np.linalg.solve(v,np.ones(3));expected=w@e/w.sum()
        self.assertAlmostEqual(d['estimate'],expected)
        self.assertAlmostEqual(d['standard_error'],(1/w.sum())**.5)
        self.assertAlmostEqual(d['q'],(e-expected)@np.linalg.solve(v,e-expected))
        for i,omission in enumerate(d['leave_one_out']):
            mask=np.arange(3)!=i;weights=np.linalg.solve(v[np.ix_(mask,mask)],np.ones(2))
            self.assertAlmostEqual(omission['estimate'],weights@e[mask]/weights.sum())
        item['covariance']=[[1,'.9','.9'],['.9',1,'-.9'],['.9','-.9',1]]
        self.assertEqual(run(item)['status'],'UNDETERMINED')
        item=correlated();item['studies']=[]
        with self.assertRaises(ValueError):prepare_toolkit_spec(dict(schema_version='1.0',checks=[item]))
        item=clustered();item.pop('terms');item['x']=[[row[0],2*row[0]] for row in item['x']]
        self.assertEqual(run(item)['status'],'UNDETERMINED')

    def test_exhaustive_small_binary_tables_preserve_strict_threshold(self):
        from sra.dependent_spec import prepare_dependent
        from sra.dependent_checks import missing_binary_sensitivity
        for ot,oc,mt,mc in itertools.product((1,2),(1,2),range(3),range(3)):
            for et,ec,threshold in itertools.product(range(ot+1),range(oc+1),('-.5','0','.5')):
                item=dict(id='s',kind='missing_binary_sensitivity',treatment=dict(events=et,observed=ot,missing=mt),
                          control=dict(events=ec,observed=oc,missing=mc),threshold=threshold,
                          control_missing_events_grid=list(range(mc+1)))
                _,d=missing_binary_sensitivity(prepare_dependent(item),None)
                values=[Fraction(et+a,ot+mt)-Fraction(ec+b,oc+mc) for a,b in itertools.product(range(mt+1),range(mc+1))]
                self.assertEqual(d['risk_difference_bounds']['lower_exact'],str(min(values)))
                self.assertEqual(d['risk_difference_bounds']['upper_exact'],str(max(values)))
                for frontier in d['tipping_frontier']:
                    b=frontier['control_missing_events'];possible=[a for a in range(mt+1) if Fraction(et+a,ot+mt)-Fraction(ec+b,oc+mc)>Fraction(threshold)]
                    self.assertEqual(frontier['minimum_treatment_missing_events'],min(possible) if possible else None)
