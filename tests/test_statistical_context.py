"""Declared statistical context and independent analytic reference controls."""
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from sra.document import parse_document_text
from sra.inspection import prepare_inspection
from sra.inspection_calculations import statistic_consistency
from sra.toolkit import verify_toolkit_spec
from sra.toolkit_spec import prepare_toolkit_spec


def item(**values):
    return dict(id='context',kind='statistic_consistency',test='t',df=[1],
                statistic='2.000000000000',reported_p='.147584',**values)


class StatisticalContextTests(unittest.TestCase):
    def check(self, **values):
        base=item()
        base.update(values)
        return verify_toolkit_spec({'schema_version':'1.0','checks':[base]})['checks'][0]

    def test_direction_uses_signed_statistic_and_cauchy_reference(self):
        # t(1) is Cauchy; independent standard-library arctangent oracle.
        p=.5-math.atan(2)/math.pi
        positive=self.check(alternative='greater')
        negative=self.check(alternative='less',statistic='-2.000000000000')
        for result in (positive,negative):
            self.assertEqual(result['status'],'VERIFIED')
            lo,hi=result['details']['computed_p_interval']
            self.assertLessEqual(lo,p);self.assertGreaterEqual(hi,p)
        self.assertEqual(self.check(alternative='less')['status'],'REFUTED')
        two=self.check(reported_p='.295167')
        self.assertEqual(two['status'],'VERIFIED')
        self.assertEqual(two['details']['alternative'],'two-sided')
        self.assertEqual(two['details']['alternative_source'],'default')
        self.assertLess(float(negative['details']['statistic_interval'][0]),0)

    def test_normal_direction_against_erfc_and_inequality_bounds(self):
        for alternative,stat,p in [('less','-2.000000000000','.022750'),
                                   ('greater','-2.000000000000','.977250'),
                                   ('two-sided','-2.000000000000','.045500')]:
            result=self.check(test='z',df=[],alternative=alternative,statistic=stat,reported_p=p)
            self.assertEqual(result['status'],'VERIFIED')
        result=self.check(test='z',df=[],alternative='greater',reported_p='.1',relation='<')
        self.assertEqual(result['status'],'VERIFIED')
        self.assertEqual(self.check(test='z',df=[],alternative='less',reported_p='.1',relation='<')['status'],'REFUTED')
        self.assertAlmostEqual(.5*math.erfc(2/math.sqrt(2)),.0227501319481792)

    def test_unknown_context_abstains_without_backend_calls(self):
        for values in ({'alternative':'unknown'}, {'df':['10.5']},
                       {'df':[10],'df_precision':'unknown'}, {'df':['10.5'],'df_precision':'rounded'}):
            spec=item();spec.update(values)
            prepared=prepare_toolkit_spec({'schema_version':'1.0','checks':[spec]})['checks'][0]
            status,details=statistic_consistency(prepared,SimpleNamespace())
            self.assertEqual(status,'UNDETERMINED')
            self.assertFalse(details['distribution_assumptions_verified'])

    def test_fractional_f_denominator_uses_closed_form_and_preserves_df(self):
        # For F(2,v), SF(x)=(v/(v+2*x))**(v/2), valid for positive real v.
        result=self.check(test='F',df=['2','0.50'],df_precision='exact',reported_p='.577350')
        self.assertEqual(result['status'],'VERIFIED')
        lo,hi=result['details']['computed_p_interval']
        expected=(.5/(.5+4))**.25
        self.assertLessEqual(lo,expected);self.assertGreaterEqual(hi,expected)
        self.assertEqual(result['details']['df'],['2','0.50'])
        self.assertFalse(result['details']['correction_method_verified'])

    def test_chi_square_closed_form_and_nonfinite_backend_guards(self):
        result=self.check(test='chi2',df=[2],reported_p='.367879')
        self.assertEqual(result['status'],'VERIFIED')
        lo,hi=result['details']['computed_p_interval']
        self.assertLessEqual(lo,math.exp(-1));self.assertGreaterEqual(hi,math.exp(-1))
        prepared=prepare_toolkit_spec({'schema_version':'1.0','checks':[item(alternative='greater')]})['checks'][0]
        for value in (0,float('nan'),1.1):
            fake=SimpleNamespace(t=SimpleNamespace(sf=lambda *args:value))
            self.assertEqual(statistic_consistency(prepared,fake)[0],'UNDETERMINED')

    def test_fractional_t_matches_independent_incomplete_beta_reference(self):
        # mpmath 60-digit regularized incomplete beta, not a SciPy-generated target:
        # I_(v/(v+x*x))(v/2,1/2), v=.5, x=2.
        reference=.445514890183131231186597446651213759
        result=self.check(df=['.5'],df_precision='exact',reported_p='.445515')
        self.assertEqual(result['status'],'VERIFIED')
        lo,hi=result['details']['computed_p_interval']
        self.assertLessEqual(lo,reference);self.assertGreaterEqual(hi,reference)

    def test_inexact_df_conversion_never_refutes_a_correct_reported_p(self):
        # Agent counterexample: 80-digit upper regularized gamma reference is
        # .49981193670937693334895010010777..., inside the printed p interval.
        result=self.check(test='chi2',df=['999999.00000000005'],df_precision='exact',
                          statistic='999999.000000000000000000',reported_p='0.49981193670938')
        self.assertEqual(result['status'],'UNDETERMINED')
        self.assertFalse(result['details']['backend_df_conversion_exact'])
        self.assertNotIn('computed_p_interval',result['details'])
        self.assertEqual(self.check(df=['1.3'],df_precision='exact')['status'],'UNDETERMINED')

    def test_backend_statistic_interval_is_rounded_outward(self):
        from decimal import Decimal
        result=self.check(test='chi2',df=[999999],
                          statistic='999999.000000000000000000',reported_p='0.49981193670936')
        details=result['details']
        low,high=map(Decimal,details['statistic_interval'])
        a,b=details['backend_statistic_interval']
        self.assertLessEqual(Decimal.from_float(a),low)
        self.assertGreaterEqual(Decimal.from_float(b),high)

    def test_invalid_directions_and_df_fail_preflight(self):
        invalid=[{'alternative':'one-sided'},{'alternative':[]},{'df_precision':'approximate'},
                 {'df':[True]},{'df':[0]},{'df':['1e-7']},{'df':['1000001']},{'df':['NaN']},
                 {'test':'F','df':[1,10],'alternative':'less'},
                 {'test':'chi2','alternative':'two-sided'},
                 {'test':'z','df':[],'df_precision':'rounded'}]
        for changes in invalid:
            spec=item();spec.update(changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                prepare_toolkit_spec({'schema_version':'1.0','checks':[spec]})

    def test_prepared_candidates_require_direction_and_df_confirmation(self):
        text='t(10.50) = -2.40, p = .03\nF(1, 20) = 4.50, p < .05\nz = 2.00, p = .03\n'
        document=parse_document_text(text,source='paper.md',sha256=hashlib.sha256(text.encode()).hexdigest())
        report=prepare_inspection(document)
        checks=[row['suggested_check'] for row in report['candidates'] if row['kind']=='statistic']
        self.assertEqual(len(checks),3)
        for check in checks:
            self.assertEqual(check['alternative'],'unknown')
            if check['df']:self.assertEqual(check['df_precision'],'unknown')
        self.assertEqual(checks[0]['df'],['10.50'])
        self.assertFalse(report['checks_executed'])
        invalid='t(1e100) = 2.00, p = .05'
        document=parse_document_text(invalid,source='paper.md',sha256=hashlib.sha256(invalid.encode()).hexdigest())
        self.assertIsNone(prepare_inspection(document)['candidates'][0]['suggested_check'])

    def test_frozen_reference_table_cases_all_remain_visible(self):
        path=Path(__file__).resolve().parents[1]/'benchmarks/pilots/statistical-context-20261116/cases.json'
        cases=json.loads(path.read_text())['cases']
        result=verify_toolkit_spec({'schema_version':'1.0','checks':[row['check'] for row in cases]})
        self.assertEqual(len(result['checks']),32)
        for expected,actual in zip(cases,result['checks']):
            self.assertEqual(actual['id'],expected['check']['id'])
            self.assertEqual(actual['status'],expected['expected_status'],actual)
