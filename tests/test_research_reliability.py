"""Numerical method oracles and partial-manifest regressions."""
import math
import json
import os
import subprocess
import sys
import unittest
from decimal import Context, localcontext
from unittest.mock import patch

from sra.toolkit import verify_toolkit_spec
from sra.toolkit_spec import prepare_toolkit_spec


def report(item):
    return verify_toolkit_spec({'schema_version':'1.0','checks':[item]})


POWER={'id':'p','kind':'power_analysis','design':'independent_t','mode':'calculate',
       'nobs':100,'effect_size':'.5','alpha':'.05'}
META={'id':'m','kind':'meta_analysis','model':'random','effect_scale':'mean_difference',
      'studies':[{'id':'a','effect':'0','variance':'1'},
                 {'id':'b','effect':'0','variance':'1'}]}
ML={'id':'ml','kind':'ml_validation',
    'samples':[{'id':'a','time':3},{'id':'b'},{'id':'c','time':1}],
    'splits':{'train':['a'],'validation':['b'],'test':['c']},
    'preprocessing_fit_ids':[],'temporal':True}


class ResearchReliabilityTests(unittest.TestCase):
    def test_allocation_ceil_uses_exact_declared_ratio(self):
        # Binary 100 * .07 is 7.000000000000001; it must still allocate 7.
        for ratio,n2 in (('.07',7),('.0700000000000000000000000000000001',8)):
            with self.subTest(ratio=ratio),localcontext(Context(prec=6)):
                row=report({**POWER,'ratio':ratio})['checks'][0]
                self.assertEqual(row['status'],'CALCULATED')
                self.assertEqual(row['details']['n_group2'],n2)
                from scipy.stats import nct,t
                df=100+n2-2
                critical=t.isf(.025,df)
                delta=.5/math.sqrt(1/100+1/n2)
                expected=nct.sf(critical,df,delta)+nct.cdf(-critical,df,delta)
                self.assertAlmostEqual(row['details']['power'],expected,places=12)
                self.assertEqual(row['details']['assumptions']['variance_model'],'equal_population_variances')

    def test_sample_size_respects_minimum_feasible_design(self):
        for design in ('independent_t','paired_t'):
            with self.subTest(design=design):
                item={k:v for k,v in POWER.items() if k!='nobs'}
                item.update(design=design,mode='sample_size',effect_size='3',target_power='.06')
                row=report(item)['checks'][0]
                self.assertEqual(row['status'],'CALCULATED')
                self.assertEqual(row['details']['n_group1' if design=='independent_t' else 'n_pairs'],2)
                self.assertGreaterEqual(row['details']['power'],.06)

    def test_invalid_power_cannot_receive_an_agreement_verdict(self):
        # Backend output validation is separate from finite-output validation.
        for value in (0.0,-.1,1.1,float('nan'),float('inf')):
            with self.subTest(value=value),patch('statsmodels.stats.power.TTestIndPower.power',return_value=value):
                result=report({**POWER,'reported_power':0})
            self.assertEqual(result['checks'][0]['status'],'UNDETERMINED')
            self.assertEqual(result['execution_status'],'partial')
            self.assertNotIn('power',result['checks'][0]['details'])

    def test_modified_hksj_two_identical_studies_has_nonzero_t_interval(self):
        row=report({**META,'ci_method':'modified_hksj'})['checks'][0]
        self.assertEqual(row['status'],'CALCULATED')
        details=row['details']
        # Student-t(df=1) .975 quantile = tan(pi*(.975-.5)).
        critical=math.tan(math.pi*.475)
        half=critical/math.sqrt(2)
        self.assertAlmostEqual(details['confidence_interval'][0],-half,places=8)
        self.assertAlmostEqual(details['confidence_interval'][1],half,places=8)
        self.assertEqual(details['interval_degrees_of_freedom'],1)
        self.assertEqual(details['hksj_scale_raw'],0)
        self.assertEqual(details['hksj_scale_used'],1)
        self.assertEqual(details['ci_method'],'modified_hksj')
        self.assertEqual(len(details['leave_one_out']),2)

    def test_modified_hksj_matches_statsmodels_wls_when_scale_exceeds_one(self):
        import numpy as np
        from statsmodels.stats.meta_analysis import combine_effects
        # Unequal precisions make DL residual scale differ from one.
        effects=np.array([0.,1.,4.])
        variances=np.array([.01,.1,1.])
        reference=combine_effects(effects,variances,method_re='chi2',use_t=True)
        self.assertGreater(reference.scale_hksj_re,1)
        item={**META,'ci_method':'modified_hksj','tau_method':'dersimonian_laird',
              'studies':[{'id':f's{i}','effect':str(e),'variance':str(v)}
                         for i,(e,v) in enumerate(zip(effects,variances))]}
        row=report(item)['checks'][0]
        self.assertEqual(row['status'],'CALCULATED')
        for actual,expected in zip(row['details']['confidence_interval'],reference.conf_int(use_t=True)[3]):
            self.assertAlmostEqual(actual,expected,places=10)
        self.assertAlmostEqual(row['details']['interval_standard_error'],math.sqrt(reference.var_hksj_re),places=12)

    def test_normal_interval_remains_default_and_method_validates_before_import(self):
        details=report(META)['checks'][0]['details']
        self.assertEqual(details['ci_method'],'normal')
        self.assertAlmostEqual(details['confidence_interval'][1],1.385903824349678,places=10)
        for update in ({'ci_method':'other'},{'ci_method':'modified_hksj','model':'fixed'}):
            with self.subTest(update=update),patch('sra.toolkit._backend') as backend:
                with self.assertRaises(ValueError):
                    prepare_toolkit_spec({'schema_version':'1.0','checks':[{**META,**update}]})
                backend.assert_not_called()

    def test_missing_validation_times_cannot_hide_known_train_test_violation(self):
        row=report(ML)['checks'][0]
        self.assertEqual(row['status'],'CANDIDATES')
        self.assertIn('temporal_order_violation',row['details']['violations'])
        self.assertIn('missing_timestamps',row['details']['unassessed_checks'])
        self.assertEqual(row['details']['protocol_status'],'violations_found')
        self.assertIn({'partitions':['train','test'],'earlier_known_max':'3','later_known_min':'1'},
                      row['details']['facts'])

    def test_partial_manifest_uses_incomplete_status(self):
        item={**ML,'samples':[{'id':'a','time':1},{'id':'b'},{'id':'c','time':3}]}
        details=report(item)['checks'][0]['details']
        self.assertEqual(details['protocol_status'],'incomplete')
        self.assertEqual(details['violations'],[])

    def test_known_values_in_partial_partition_can_still_prove_violation(self):
        item={**ML,'samples':ML['samples']+[{'id':'d'}],
              'splits':{'train':['a','d'],'test':['c']}}
        details=report(item)['checks'][0]['details']
        self.assertIn('temporal_order_violation',details['violations'])
        self.assertIn('missing_timestamps',details['unassessed_checks'])

    def test_equal_timestamp_evidence_is_stable_across_hash_seeds(self):
        item={**ML,'samples':[{'id':'a','time':'1.0'},{'id':'d','time':'1.00'},{'id':'b','time':0}],
              'splits':{'train':['a','d'],'test':['b']}}
        code=('import json; from sra.toolkit import verify_toolkit_spec; '
              'print(json.dumps(verify_toolkit_spec('+repr({'schema_version':'1.0','checks':[item]})+'),sort_keys=True))')
        outputs=[subprocess.check_output([sys.executable,'-c',code],text=True,
                 env={**os.environ,'PYTHONHASHSEED':str(seed)}) for seed in range(4)]
        self.assertEqual(len(set(outputs)),1)
        self.assertEqual(json.loads(outputs[0])['checks'][0]['details']['facts'][0]['earlier_known_max'],'1.0')
