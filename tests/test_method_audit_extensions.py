"""Known evidence gaps and sampling uncertainty must not become false passes."""
import copy
from decimal import localcontext
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import warnings

from sra.measurement_uncertainty import normal_agreement_confidence, confidence_decision
from sra.toolkit import verify_toolkit_spec
from sra.toolkit_spec import prepare_toolkit_spec

ROOT = Path(__file__).parents[1]


def items():
    return json.loads((ROOT / 'examples/method-audits.json').read_text())['checks']


def problem(item):
    return dict(schema_version='1.0',checks=[item])


def check(item):
    return verify_toolkit_spec(problem(item))['checks'][0]


class EvidenceExtensionTests(unittest.TestCase):
    def test_question_and_method_quote_offsets_select_distinct_occurrences(self):
        item = items()[3]
        result = check(item)
        self.assertEqual(result['status'],'VERIFIED')
        for row in result['details']['fields']:
            self.assertNotEqual(row['left']['start'],row['right']['start'])
            for evidence in (row['left'],row['right']):
                self.assertEqual(evidence['selection'],'explicit_offset')
                self.assertEqual(item['text'][evidence['start']:evidence['end']],evidence['quote'])
        for row in item['method'].values():
            row.pop('start')
        result = check(item)
        self.assertEqual(result['status'],'UNDETERMINED')
        self.assertTrue(all(row['comparison']=='equal' for row in result['details']['fields']))
        self.assertIn('outcome:ambiguous_quote',result['details']['unassessed_checks'])

    def test_overlapping_occurrences_and_selected_unicode_offsets(self):
        item = items()[0]
        item['text']='🙂aaa'
        item['contribution']['sensor']=dict(value='aa',quote='aa')
        self.assertEqual(check(item)['status'],'UNDETERMINED')
        item['contribution']['sensor']['start']=2
        row=check(item)
        self.assertEqual(row['status'],'CANDIDATES')
        self.assertEqual(row['details']['comparisons'][0]['fields'][0]['left']['end'],4)
        for invalid in (True,-1,0,1000,2.5,None):
            bad=copy.deepcopy(item);bad['contribution']['sensor']['start']=invalid
            with self.subTest(offset=invalid),self.assertRaises(ValueError):
                prepare_toolkit_spec(problem(bad))

    def test_required_comparators_and_reference_subset_coverage(self):
        item=items()[0]
        item['required_comparator_ids']=['prior','missing']
        row=check(item)
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertEqual(row['details']['missing_required_comparators'],['missing'])
        self.assertEqual(row['details']['comparisons'][0]['comparison'],'different_declared_features')
        item['required_comparator_ids']=['prior']
        self.assertEqual(check(item)['status'],'CANDIDATES')
        search=items()[1]
        search['reference_coverage']=dict(required=['A','B'],retrieved=['A','extra'])
        row=check(search)
        self.assertEqual(row['status'],'REFUTED')
        self.assertEqual(row['details']['reference_coverage']['missing_required'],['B'])
        self.assertEqual(row['details']['reference_coverage']['matched_count'],1)
        search['reference_coverage']['retrieved'].append('B')
        self.assertEqual(check(search)['status'],'VERIFIED')
        search['reference_coverage']['retrieved']=[]
        self.assertEqual(check(search)['details']['reference_coverage']['matched_count'],0)
        self.assertEqual(check(search)['details']['literature_adequacy'],'NOT_ASSESSED')

    def test_invalid_record_sets_and_confidence_levels_rejected(self):
        bad=[]
        for value in ([],['a','a'],['bad id'],['a\x00b'],[3], 'a', ['a']*1001):
            item=items()[0];item['required_comparator_ids']=value;bad.append(item)
        item=items()[0];item['required_comparator_ids']=['bad:identifier'];bad.append(item)
        for coverage in (dict(required=[],retrieved=[]),dict(required=['A'],retrieved=['A','A']),dict(required=['A'],retrieved=['bad id']),dict(required=['A'],retrieved=['a\x7fb'])):
            item=items()[1];item['reference_coverage']=coverage;bad.append(item)
        for level in (0,.4999,1,True,'NaN','.9991'):
            item=items()[2];item['confidence_level']=level;bad.append(item)
        for item in bad:
            with self.subTest(kind=item['kind']),self.assertRaises(ValueError):
                prepare_toolkit_spec(problem(item))


class MeasurementConfidenceTests(unittest.TestCase):
    def measurement(self):
        item=items()[2]
        item.update(reference=[10,20,30],measured=[9,20,31],confidence_level='.95',acceptable_difference=dict(lower=-30,upper=30))
        return item

    def test_df_two_closed_form_quantiles_and_conservative_bounds(self):
        row=check(self.measurement())
        self.assertEqual(row['status'],'VERIFIED')
        region=row['details']['confidence_region']
        self.assertEqual(region['method'],'bonferroni_mean_sd_rectangle')
        # For df=2, chi-square CDF is 1-exp(-x/2), and Student t has
        # inverse sqrt(2)*u/sqrt(1-u^2), u=2p-1. Independent analytic controls.
        tail=(1-.95)/4
        u=1-2*tail
        t=math.sqrt(2)*u/math.sqrt(1-u*u)
        q_low=-2*math.log1p(-tail)
        q_high=-2*math.log(tail)
        self.assertAlmostEqual(region['quantiles']['t'],t,places=9)
        self.assertAlmostEqual(region['sd_interval'][0],math.sqrt(2/q_high),places=11)
        self.assertAlmostEqual(region['sd_interval'][1],math.sqrt(2/q_low),places=11)
        expected_low=-t/math.sqrt(3)-1.96*math.sqrt(2/q_low)
        self.assertAlmostEqual(region['lower_limit_interval'][0],expected_low,places=9)
        self.assertEqual(row['details']['decision_basis'],'simultaneous_confidence_bounds')
        self.assertEqual(row['details']['measurement_validity'],'NOT_ASSESSED')
        higher=normal_agreement_confidence(0,1,3,'.99')
        self.assertLess(higher['lower_limit_interval'][0],region['lower_limit_interval'][0])
        self.assertGreater(higher['upper_limit_interval'][1],region['upper_limit_interval'][1])

    def test_point_estimate_pass_is_not_confidence_pass(self):
        item=self.measurement();item['acceptable_difference']=dict(lower=-2,upper=2)
        row=check(item)
        self.assertTrue(row['details']['estimated_limits_within_bounds'])
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertIn('confidence_region_crosses_or_touches_acceptance_boundary',row['details']['unassessed_checks'])
        item['acceptable_difference']=dict(lower=30,upper=40)
        self.assertEqual(check(item)['status'],'REFUTED')
        item['acceptable_difference']=dict(lower=-40,upper=-30)
        self.assertEqual(check(item)['status'],'REFUTED')
        region=check(self.measurement())['details']['confidence_region']
        self.assertEqual(confidence_decision(region,[region['lower_limit_interval'][0],30]),'UNDETERMINED')

    def test_large_offset_cancellation_cannot_earn_confidence_verification(self):
        item=self.measurement()
        item.update(reference=[0,0,0],
                    measured=[2005844685.2440958,2105844685.2440958,2205844685.244096],
                    acceptable_difference=dict(lower='0.00000018',upper='10000000000'))
        row=check(item)
        self.assertEqual(row['status'],'UNDETERMINED')
        region=row['details']['confidence_region']
        self.assertGreater(region['numerical_guard']['absolute'],1e-7)
        self.assertFalse(region['numerical_guard']['certified_error_bound'])
        self.assertTrue(row['details']['estimated_limits_within_bounds'])

    def test_missing_backend_bad_quantiles_and_warnings_keep_estimates(self):
        item=self.measurement()
        with patch('sra.measurement_uncertainty._stats',side_effect=ImportError):
            row=check(item)
        self.assertEqual(row['status'],'UNDETERMINED')
        self.assertEqual(row['details']['mean_difference'],0)
        self.assertEqual(row['details']['confidence_region']['reason'],'optional_backend_unavailable')
        for value in (float('nan'),float('inf'),-1):
            backend=SimpleNamespace(t=SimpleNamespace(ppf=lambda *args:value),chi2=SimpleNamespace(ppf=lambda *args:1))
            with patch('sra.measurement_uncertainty._stats',return_value=backend):
                self.assertEqual(check(item)['details']['confidence_region']['reason'],'invalid_or_warned_quantiles')
        def warned(*args):
            warnings.warn('numerical',RuntimeWarning)
            return 1
        backend=SimpleNamespace(t=SimpleNamespace(ppf=warned),chi2=SimpleNamespace(ppf=lambda *args:1))
        with patch('sra.measurement_uncertainty._stats',return_value=backend):
            self.assertEqual(check(item)['details']['confidence_region']['reason'],'invalid_or_warned_quantiles')
        with patch('sra.measurement_uncertainty._stats',side_effect=ValueError):
            self.assertEqual(check(item)['details']['confidence_region']['reason'],'confidence_backend_did_not_complete')
        # Direct controls exercise guardrails for invalid numeric intervals.
        self.assertEqual(normal_agreement_confidence(0,float('inf'),3,'.95')['reason'],'invalid_confidence_bounds')

    def test_unaffirmed_assumptions_missing_band_and_ambient_decimal(self):
        item=self.measurement()
        item['normal_differences']=False
        self.assertEqual(check(item)['details']['confidence_region']['reason'],'assumptions_or_dispersion_unresolved')
        item=self.measurement();item['measured']=item['reference']
        self.assertEqual(check(item)['status'],'UNDETERMINED')
        item=self.measurement();item['acceptable_difference']=None
        self.assertEqual(check(item)['details']['confidence_region']['status'],'CALCULATED')
        self.assertEqual(check(item)['status'],'UNDETERMINED')
        item=self.measurement();expected=check(item)
        with localcontext() as context:
            context.prec=2;context.Emax=5;context.Emin=-5
            self.assertEqual(check(item),expected)

    def test_advanced_fixture_has_deliberate_gaps_and_sampling_uncertainty(self):
        path=ROOT/'examples/method-audits-advanced.json'
        report=verify_toolkit_spec(path.read_text())
        self.assertEqual([row['status'] for row in report['checks']],['UNDETERMINED','REFUTED','UNDETERMINED','VERIFIED'])
        self.assertEqual(report['execution_status'],'partial')
