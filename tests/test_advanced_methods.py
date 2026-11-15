"""Analytic and independently constructed synthetic method controls."""
import copy
import itertools
import math
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from test_dependent_data import clustered, run
from sra.toolkit_spec import prepare_toolkit_spec


def multilevel():
    effects = [-.5, .5, 1.5, 2.5, 3.5, 4.5]
    return dict(id='multi', kind='multilevel_meta_analysis', effect_scale='mean_difference',
                studies=[dict(id=f'e{i}',group=f'g{i//2}',effect=y) for i,y in enumerate(effects)],
                covariance=[[int(i==j) for j in range(6)] for i in range(6)],tau2_max=20)


def bootstrap():
    item=clustered()
    return {k:v for k,v in item.items() if k not in ('leave_one_cluster_out',)} | dict(
        id='wild',kind='wild_cluster_bootstrap',term='exposure',null_value=0)


def power():
    return dict(id='plan',kind='cluster_power_analysis',mode='calculate',cluster_size=20,
                clusters_per_arm=12,icc='.05',effect_size='.4',alpha='.05')


class AdvancedMethodTests(unittest.TestCase):
    def test_balanced_group_reml_has_known_variance_and_blup(self):
        row=run(multilevel());self.assertEqual(row['status'],'CALCULATED');d=row['details']
        self.assertAlmostEqual(d['tau_squared'],3.5,places=5)
        self.assertAlmostEqual(d['estimate'],2)
        self.assertAlmostEqual(d['standard_error'],math.sqrt(4/3),places=6)
        self.assertEqual(d['group_count'],3)
        self.assertFalse(d['variance_component_uncertainty_propagated'])
        for value,mean in zip(d['group_effects'],[0,2,4]):
            self.assertAlmostEqual(value['conditional_blup'],3.5/4*(mean-2),places=5)

    def test_reml_matches_independent_dense_scalar_optimization(self):
        import numpy as np
        from scipy.optimize import minimize_scalar
        item=multilevel();item['covariance'][0][0]=2;item['studies'][0]['effect']='-.8'
        y=np.array([float(s['effect']) for s in item['studies']]);ones=np.ones(6)
        v=np.array(item['covariance'],dtype=float)
        b=np.array([[int(a['group']==c['group']) for c in item['studies']] for a in item['studies']])
        def objective(tau):
            matrix=v+tau*b;inv=np.linalg.inv(matrix);mu=ones@inv@y/(ones@inv@ones)
            return np.linalg.slogdet(matrix)[1]+np.log(ones@inv@ones)+(y-mu)@inv@(y-mu)
        ref=minimize_scalar(objective,bounds=(0,20),method='bounded',options={'xatol':1e-10})
        d=run(item)['details'];self.assertAlmostEqual(d['tau_squared'],ref.x,places=5)
        self.assertAlmostEqual(d['restricted_objective'],ref.fun,places=8)

    def test_reml_scale_order_and_location_and_zero_boundary(self):
        item=multilevel();base=run(item)['details']
        scaled=copy.deepcopy(item)
        for s in scaled['studies']:s['effect']=10*s['effect']+100
        scaled['covariance']=[[100*v for v in row] for row in item['covariance']];scaled['tau2_max']=2000
        d=run(scaled)['details'];self.assertAlmostEqual(d['tau_squared']/100,base['tau_squared'],places=5)
        self.assertAlmostEqual(d['estimate'],120)
        rev=copy.deepcopy(item);rev['studies'].reverse();rev['covariance']=[list(reversed(r)) for r in reversed(rev['covariance'])]
        self.assertAlmostEqual(run(rev)['details']['tau_squared'],base['tau_squared'],places=5)
        for s in item['studies']:s['effect']=1
        d=run(item)['details'];self.assertEqual(d['tau_squared'],0)
        self.assertTrue(d['variance_on_boundary'])

    def test_reml_upper_bound_and_bad_covariance_abstain(self):
        item=multilevel();item['tau2_max']='.1'
        row=run(item);self.assertEqual(row['status'],'UNDETERMINED')
        self.assertIn('variance_upper_bound_active',row['details']['unassessed_checks'])
        item=multilevel();item['covariance']=[[1]*6 for _ in range(6)]
        self.assertEqual(run(item)['status'],'UNDETERMINED')

    def test_reml_minimum_between_zero_and_first_search_grid_point(self):
        item=multilevel();a=math.sqrt(.5001)
        for i,s in enumerate(item['studies']):s['effect']=[-a,0,a][i//2]+(-.1 if i%2==0 else .1)
        row=run(item);self.assertEqual(row['status'],'CALCULATED')
        self.assertAlmostEqual(row['details']['tau_squared'],.0001,places=6)

    def test_reml_upper_constraint_numerically_tied_to_an_interior_point(self):
        for factor in (1,.001):
            item=multilevel();item['tau2_max']=3.49999999965*factor**2
            for s in item['studies']:s['effect']*=factor
            item['covariance']=[[v*factor**2 for v in row] for row in item['covariance']]
            row=run(item);self.assertEqual(row['status'],'UNDETERMINED')
            self.assertTrue(row['details']['upper_boundary_unresolved'])
            self.assertTrue(row['details']['variance_on_boundary'])
            self.assertIn('variance_upper_bound_active',row['details']['unassessed_checks'])

    def test_exhaustive_bootstrap_matches_direct_statsmodels_refits(self):
        import numpy as np
        from statsmodels.regression.linear_model import OLS
        from statsmodels.stats.sandwich_covariance import cov_cluster
        item=bootstrap();x=np.column_stack([np.ones(12),item['x']]);y=np.array(item['y'],dtype=float)
        groups=np.array(item['clusters']);fit=OLS(y,x).fit()
        observed=fit.params[1]/math.sqrt(cov_cluster(fit,groups)[1,1])
        restricted=np.full(12,float(y.mean()));residual=y-restricted
        values=[]
        for signs in itertools.product((-1,1),repeat=4):
            weights=np.array([signs[sorted(set(groups)).index(g)] for g in groups])
            f=OLS(restricted+residual*weights,x).fit()
            values.append(abs(f.params[1]/math.sqrt(cov_cluster(f,groups)[1,1])))
        row=run(item);self.assertEqual(row['status'],'CALCULATED');d=row['details']
        expected=sum(t>=abs(observed)-d['numerical_tie_band'] for t in values)
        self.assertEqual(d['p_denominator'],16);self.assertEqual(d['p_numerator'],expected)
        self.assertEqual(d['p_value'],expected/16)
        self.assertFalse(d['finite_sample_exact_test'])

    def test_bootstrap_repeatability_nonzero_null_and_order(self):
        item=bootstrap();item['null_value']='.5';before=copy.deepcopy(item)
        first=run(item);self.assertEqual(first,run(item));self.assertEqual(item,before)
        self.assertTrue(first['details']['null_imposed'])
        reverse={**item,**{key:list(reversed(item[key])) for key in ('x','y','clusters')}}
        self.assertEqual(run(reverse)['details']['p_value'],first['details']['p_value'])
        self.assertGreaterEqual(first['details']['p_numerator'],2)

    def test_bootstrap_unresolved_inputs_or_draws_never_drop_denominators(self):
        item=bootstrap();item['y']=[1+2*r[0] for r in item['x']]
        self.assertEqual(run(item)['status'],'UNDETERMINED')
        item=bootstrap();item['x']=[[1]]*12
        self.assertEqual(run(item)['status'],'UNDETERMINED')

    def test_cluster_power_matches_independent_cluster_mean_t_model(self):
        from statsmodels.stats.power import TTestIndPower
        item=power();d=run(item)['details']
        effective=.4/math.sqrt(.05+.95/20)
        expected=float(TTestIndPower().power(effect_size=effective,nobs1=12,alpha=.05,ratio=1))
        self.assertAlmostEqual(d['power'],expected,places=12)
        self.assertEqual(d['inference_df'],22)
        self.assertAlmostEqual(d['design_effect'],1.95)
        item.update(cluster_size=1,icc='1');a=run(item)['details']['power']
        item.update(cluster_size=200,icc='1');self.assertAlmostEqual(run(item)['details']['power'],a)

    def test_cluster_count_search_reaches_target_and_previous_count_does_not(self):
        item=power();item.pop('clusters_per_arm');item.update(mode='sample_size',target_power='.8')
        row=run(item);self.assertEqual(row['status'],'CALCULATED');d=row['details']
        self.assertGreaterEqual(d['power'],.8)
        self.assertTrue(d['minimal_within_supported_range'])
        self.assertLess(d['previous_cluster_count_power'],.8)
        item['max_clusters_per_arm']=2
        self.assertEqual(run(item)['status'],'UNDETERMINED')

    def test_power_null_effect_and_icc_monotonicity(self):
        item=power();item['effect_size']=0
        self.assertAlmostEqual(run(item)['details']['power'],.05,places=12)
        item=power();a=run(item)['details']['power'];item['icc']='.2'
        self.assertLess(run(item)['details']['power'],a)

    def test_planning_thresholds_below_numeric_resolution_abstain(self):
        item=power();item.pop('clusters_per_arm');item.update(mode='sample_size',target_power='.0500000000000000000001',effect_size=0)
        self.assertIn('planning_target_collapses_in_float64',run(item)['details']['unassessed_checks'])
        item.update(target_power='.8',effect_size='.4')
        with patch('scipy.stats.nct.sf',return_value=.8),patch('scipy.stats.nct.cdf',return_value=0.):
            row=run(item)
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertFalse(row['details']['minimal_within_supported_range'])
        self.assertIn('planning_target_at_numerical_resolution',row['details']['unassessed_checks'])

    def test_all_three_methods_validate_before_backend_import(self):
        bad=[]
        for key,value in [('tau2_max',0),('effect_scale','raw'),('studies',[])]:
            item=multilevel();item[key]=value;bad.append(item)
        item=multilevel()
        for s in item['studies']:s['group']='same'
        bad.append(item)
        item=multilevel();item['studies'][0]['group']=' g0';bad.append(item)
        for key,value in [('term','intercept'),('term','absent'),('x',[[0]]*501),('null_value','1e9')]:
            item=bootstrap();item[key]=value;bad.append(item)
        for key,value in [('mode','unknown'),('cluster_size',True),('clusters_per_arm',1),('icc','1.1'),('effect_size',-1)]:
            item=power();item[key]=value;bad.append(item)
        item=power();item.pop('clusters_per_arm');item.update(mode='sample_size',target_power='.05');bad.append(item)
        item=bootstrap();item.update(x=[[0]]*501,y=[0]*501,clusters=[str(i%4) for i in range(501)]);bad.append(item)
        with patch('sra.toolkit._backend',side_effect=AssertionError('No backend')):
            for item in bad:
                with self.subTest(item=item),self.assertRaises(ValueError):
                    prepare_toolkit_spec(dict(schema_version='1.0',checks=[item]))

    def test_reml_precision_conditioning_and_solver_failures_abstain(self):
        item=multilevel();item['studies'][0]['effect']='1.00000000000000000000001';item['studies'][1]['effect']='1'
        self.assertEqual(run(item)['status'],'UNDETERMINED')
        with patch('numpy.linalg.cond',return_value=1e11):
            self.assertIn('ill_conditioned_sampling_covariance',run(multilevel())['details']['unassessed_checks'])
        with patch('numpy.linalg.cond',side_effect=[1,1e11]):
            self.assertIn('unresolved_reml_search',run(multilevel())['details']['unassessed_checks'])
        with patch('scipy.optimize.minimize_scalar',return_value=SimpleNamespace(success=False,x=0)):
            self.assertIn('reml_search_did_not_converge',run(multilevel())['details']['unassessed_checks'])
        def unfinished(function,bounds,**kwargs):return SimpleNamespace(success=True,x=sum(bounds)/2)
        with patch('scipy.optimize.minimize_scalar',side_effect=unfinished),patch('scipy.optimize.brentq',side_effect=lambda f,left,right,**kw:(left+right)/2):
            self.assertIn('reml_stationarity_unresolved',run(multilevel())['details']['unassessed_checks'])

    def test_reml_unrepresentable_mean_interval_retains_estimate(self):
        item=multilevel();item['studies']=item['studies'][:3]
        for i,s in enumerate(item['studies']):s.update(group=f'g{i}',effect=999999)
        item['covariance']=[['1e-12' if i==j else '-4.999999995e-13' for j in range(3)] for i in range(3)]
        item['tau2_max']='1e-12'
        row=run(item);self.assertEqual(row['status'],'UNDETERMINED')
        self.assertIsNone(row['details']['confidence_interval'])
        self.assertAlmostEqual(row['details']['estimate'],999999)

    def test_bootstrap_collapsed_and_cancelled_score_inputs_abstain(self):
        item=bootstrap();item['y']=['1.0000000000000000000001','1']+item['y'][2:]
        self.assertEqual(run(item)['status'],'UNDETERMINED')
        item=bootstrap();item['x']=[[x] for x in [0,1,2]*4]
        item['y']=[3+2*x+r for x,r in zip([0,1,2]*4,[1,-2,1]*4)]
        self.assertIn('observed_bootstrap_studentization_unresolved',run(item)['details']['unassessed_checks'])

    def test_undefined_bootstrap_replicates_do_not_become_dropped_successes(self):
        import numpy as np
        from sra.advanced_checks import _wild_projection
        calls=[0]
        def fit(original,values,np):
            calls[0]+=1;current,change=_wild_projection(original,values,np)
            if calls[0]==1:current.update(residual_norm=0.)
            return current,change
        with patch('sra.advanced_checks._wild_projection',side_effect=fit):
            row=run(bootstrap())
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertEqual(row['details']['p_denominator'],16)
        self.assertEqual(row['details']['unresolved_replicates'],1)
        self.assertIsNone(row['details']['p_value'])

    def test_contrast_reml_resolves_near_singular_mean_direction(self):
        item=multilevel();eps=2e-10;tau=1e-7;a=math.sqrt(.5+tau)
        for i,s in enumerate(item['studies']):s['effect']=[-a,0,a][i//2]+(-.1 if i%2==0 else .1)
        item['covariance']=[[int(i==j)-(1-eps)/6 for j in range(6)] for i in range(6)]
        item['tau2_max']=1
        row=run(item);self.assertEqual(row['status'],'CALCULATED')
        self.assertAlmostEqual(row['details']['tau_squared']/tau,1,places=6)
        self.assertAlmostEqual(row['details']['standard_error']/math.sqrt((tau+eps/2)/3),1,places=6)

    def test_bootstrap_collinearity_cannot_lose_global_sign_ties(self):
        import numpy as np
        rng=np.random.default_rng(45);item=None
        for eps in (1e-4,1e-5,1e-6):
            for case in range(30):
                u=rng.normal(size=20);x=np.column_stack([u,u+eps*rng.normal(size=20)])
                y=rng.normal(size=20)+rng.normal(size=5)[np.repeat(np.arange(5),4)]
                if eps==1e-6 and case==10:
                    item=dict(id='collinear',kind='wild_cluster_bootstrap',x=x.tolist(),y=y.tolist(),
                              clusters=[str(i//4) for i in range(20)],term='x1',null_value=1)
        row=run(item)
        if row['status']=='CALCULATED':
            self.assertGreaterEqual(row['details']['p_numerator'],2)
            self.assertLessEqual(row['details']['original_replication_error'],row['details']['numerical_tie_band'])
        else:
            self.assertEqual(row['status'],'UNDETERMINED')
            self.assertIsNone(row['details'].get('p_value'))

    def test_bootstrap_detects_broken_sign_symmetry_or_endpoint_replication(self):
        from sra.advanced_checks import _wild_projection
        count=[0]
        def altered(original,values,np):
            current,change=_wild_projection(original,values,np);count[0]+=1
            if count[0]==1:change[1]+=1e-4
            return current,change
        with patch('sra.advanced_checks._wild_projection',side_effect=altered):
            row=run(bootstrap())
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertIn('bootstrap_sign_invariance_unresolved',row['details']['unassessed_checks'])
        self.assertIsNone(row['details']['p_value'])

    def test_cluster_power_left_tail_fallback_is_an_equivalent_identity(self):
        with patch('scipy.stats.nct.cdf',return_value=float('nan')):
            row=run(power())
        self.assertEqual(row['status'],'CALCULATED')
        self.assertAlmostEqual(row['details']['power'],run(power())['details']['power'],places=12)

    def test_individual_noncentral_t_tails_cannot_be_invalid_but_sum_valid(self):
        expected=run(power())['details']['power']
        with patch('scipy.stats.nct.cdf',return_value=-.1):
            self.assertAlmostEqual(run(power())['details']['power'],expected)
        for left,right in [(.5,-.1),(.8,.8)]:
            with patch('scipy.stats.nct.cdf',return_value=left),patch('scipy.stats.nct.sf',return_value=right):
                row=run(power())
            self.assertEqual(row['status'],'UNDETERMINED')
            self.assertIn('noncentral_t_power_unresolved',row['details']['unassessed_checks'])

    def test_restricted_bootstrap_fit_failure_abstains_before_enumeration(self):
        from sra.dependent_checks import _linear_fit
        item=bootstrap();item['x']=[row+[i%2] for i,row in enumerate(item['x'])]
        item['terms']=['exposure','nuisance'];count=[0]
        def fit(x,y,np):
            count[0]+=1
            return None if count[0]==2 else _linear_fit(x,y,np)
        with patch('sra.dependent_checks._linear_fit',side_effect=fit):
            row=run(item)
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertIn('restricted_bootstrap_design_unresolved',row['details']['unassessed_checks'])

    def test_power_saturation_failures_and_minimum_design(self):
        item=power()
        with patch('scipy.stats.nct.sf',return_value=float('nan')):
            self.assertIn('noncentral_t_power_unresolved',run(item)['details']['unassessed_checks'])
        with patch('scipy.stats.nct.sf',return_value=1.),patch('scipy.stats.nct.cdf',return_value=0.):
            row=run(item);self.assertEqual(row['status'],'UNDETERMINED')
            self.assertIsNone(row['details']['power'])
        item.pop('clusters_per_arm');item.update(mode='sample_size',target_power='.06',effect_size='1')
        row=run(item);self.assertEqual(row['details']['clusters_per_arm'],2)
        # Deliberately inconsistent numerical tail function must not certify an
        # integer minimum just because a bisection path happens to return one.
        calls={}
        def inconsistent(critical,df,noncentrality):
            k=(df+2)//2;calls[k]=calls.get(k,0)+1
            return .1 if k<=4 or (k==6 and calls[k]==1) else .9
        with patch('scipy.stats.nct.sf',side_effect=inconsistent),patch('scipy.stats.nct.cdf',return_value=0.):
            report=run({**item,'target_power':'.8'})
        self.assertEqual(report['status'],'UNDETERMINED')
        self.assertIn('integer_search_minimality_unresolved',report['details']['unassessed_checks'])

    def test_source_binding_criteria_and_benchmark_abstention(self):
        import tempfile
        from pathlib import Path
        from sra.document import load_document
        from sra.review import review_manuscript
        from sra.toolkit_spec import digest
        from sra.error_benchmark import run_error_benchmark
        from sra.json_utils import canonical_json
        text='# Synthetic methods\nDeclared grouped estimates and cluster design only.\n'
        checks=[multilevel(),bootstrap(),power()]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);paper=root/'paper.md';paper.write_text(text,encoding='utf-8')
            doc=load_document(paper);spec=root/'spec.json'
            spec.write_text(canonical_json(dict(schema_version='1.0',source_sha256=doc.sha256,
                extracted_text_sha256=digest(doc.text),checks=checks)),encoding='utf-8')
            report=review_manuscript(str(paper),study_type='quantitative',toolkit_spec=spec.read_text(encoding='utf-8'),style_language='none')
            rows={r['id']:r for r in report['criteria_matrix']['criteria']}
            for criterion in ('statistical_inference','sample_size_power','meta_analysis'):
                self.assertEqual(rows[criterion]['execution_status'],'checks_completed')
                self.assertEqual(rows[criterion]['scientific_verdict'],'NOT_ASSESSED')
            self.assertEqual(paper.read_text(),text)
        manifest=dict(schema_version='error-benchmark/1.0',dataset_id='synthetic_methods',dataset_kind='synthetic',
            papers=[dict(id='paper',group_id='group',split='development',discipline='synthetic',source_uri='synthetic:paper',
                         license_note='Synthetic software control.',text=text,sha256=digest(text))],
            targets=[dict(id=c['id'],kind=c['kind'],definition='Conditional calculation, no reported discrepancy.') for c in checks],
            cases=[dict(id=c['id'],paper_id='paper',target_id=c['id'],source_quote='Declared grouped estimates and cluster design only.',check=c) for c in checks])
        result=run_error_benchmark(manifest)
        self.assertTrue(all(c['prediction']=='abstain' for c in result['cases']))


if __name__=='__main__':
    unittest.main()
