"""Regression guards for the fail-closed tail / df-correction abstention.

These lock in the false-alarm reduction measured on the frozen published-reference
cohort (``benchmarks/pilots/published-reference-20261116/first-run.json``). The raw
expressions below are copied verbatim from that cohort; the gold labels are the
historical manual reference, not new human decisions.

The abstention is a deliberate precision/recall trade-off. A REFUTED verdict under
the *default* (undeclared) two-sided tail or uncorrected df is only a verdict about
that assumption. When the printed p is also consistent with a plausible undeclared
analysis choice (a one-tailed t/z test, or a sphericity df correction on F), the
engine abstains instead of declaring a reporting error. Because the false alarms and
some genuine errors share the same numeric signature once the tail/correction is
undeclared, removing those false alarms also moves some true errors to abstention.
That recall cost is asserted explicitly below so it stays a conscious, documented
choice rather than an accidental regression. See the benchmark report and README.
"""
import unittest

from sra.toolkit import verify_toolkit_spec
from tools import evaluate_published_reference as ref

# False alarms (gold=no_error) that the default two-sided/uncorrected engine used to
# REFUTE, now abstained because an undeclared one-tailed test explains the printed p.
FIXED_ONE_TAILED = [
    't(69) = 1.68, p <.05',    # row_262
    't(69) = 1.73, p <.05',    # row_263
    't(29) = 2.06, p <.025',   # row_266
    't(14) = 2.0, p <.03',     # row_703
    't(29) = 1.80, p = .04',   # row_711
    't(31) = 1.86, p = .04',   # row_712
    't(35) = 2.00, p = .03',   # row_713
    't(29) = 2.40, p = .01',   # row_714
]

# False alarms (gold=no_error) now abstained because a sphericity df correction
# (Greenhouse-Geisser/Huynh-Feldt) could raise the upper-tail F p to the printed value.
FIXED_DF_CORRECTION = [
    'F(9, 504) = 2.25, p =.036',   # row_394
    'F(9, 513) = 2.27, p =.032',   # row_395
    'F(9, 504) = 2.30, p =.035',   # row_396
    'F(9, 504) = 2.49, p =.033',   # row_397
    'F(9, 504) = 2.81, p =.011',   # row_398
    'F(9, 513) = 2.98, p =.035',   # row_399
    'F(9, 513) = 3.11, p =.023',   # row_400
    'F(48, 720) = 2.89, p =.005',  # row_409
    'F(2, 30) = 3.46, p =.047',    # row_418
    'F(2, 30) = 6.51, p =.008',    # row_436
    'F(2, 30) = 6.63, p =.01',     # row_437
]

# Genuine reference errors (gold=error) that share the same undeclared-choice numeric
# signature and therefore also move to abstention. This is the documented recall cost.
LOST_TRUE_POSITIVES = [
    't(15) = 2.75, p <.01',    # row_65
    't(18) = 1.99, p <.05',    # row_98
    't(27) = 2.02, p <.05',    # row_526
    'F(4, 15) = 11.01, p =.005',  # row_540
    't(115) = 2.57, p <.01',   # row_656
    't(18) = 3.78, p <.001',   # row_811
    't(18) = 3.85, p <.001',   # row_813
]

# Genuine errors whose discrepancy is NOT explainable by an undeclared one-tailed test
# or an upward df correction, so they must still be REFUTED (recall guards).
STILL_REFUTED = [
    't(35) = 1.97, p <.028',   # row_19: refuted even one-tailed
    't(209) = 3.69, p <.0001', # row_499: refuted even one-tailed
    'F(2, 111) = 2.91, p <.03',# row_138: reported p too LOW (downward)
    'F(3, 14) = 5.45, p <.01', # row_273: downward
    'F(1, 49) = 12.21, p <.001',  # row_15: df1=1, no sphericity correction
    'F(1, 53) = 2.91, p <.05', # row_548: remaining false alarm, df1=1 downward
]


def check(raw):
    parsed, reason = ref.parse_expression(raw, 'regression')
    if parsed is None:
        raise AssertionError(f'benchmark expression no longer parses: {raw!r} ({reason})')
    return verify_toolkit_spec({'schema_version': '1.0', 'checks': [parsed]})['checks'][0]


class StatisticAbstentionRegressions(unittest.TestCase):
    def test_fixed_one_tailed_false_alarms_now_abstain(self):
        for raw in FIXED_ONE_TAILED:
            with self.subTest(raw=raw):
                result = check(raw)
                self.assertEqual(result['status'], 'UNDETERMINED')
                self.assertTrue(result['details']['possible_undeclared_one_tailed'])
                self.assertEqual(result['details']['alternative_source'], 'default')
                self.assertIn('one_tailed_p_interval', result['details'])

    def test_fixed_df_correction_false_alarms_now_abstain(self):
        for raw in FIXED_DF_CORRECTION:
            with self.subTest(raw=raw):
                result = check(raw)
                self.assertEqual(result['status'], 'UNDETERMINED')
                self.assertTrue(result['details']['possible_undeclared_df_correction'])
                self.assertEqual(result['details']['alternative_source'], 'default')
                self.assertIn('df_correction_p_max', result['details'])

    def test_unexplainable_true_errors_still_refuted(self):
        for raw in STILL_REFUTED:
            with self.subTest(raw=raw):
                self.assertEqual(check(raw)['status'], 'REFUTED')

    def test_documented_recall_cost_abstains_transparently(self):
        # These gold=error rows share the undeclared-choice signature; abstention is
        # the intentional, measured recall trade-off, not a silent false negative.
        for raw in LOST_TRUE_POSITIVES:
            with self.subTest(raw=raw):
                result = check(raw)
                self.assertEqual(result['status'], 'UNDETERMINED')
                details = result['details']
                self.assertTrue(details.get('possible_undeclared_one_tailed')
                                or details.get('possible_undeclared_df_correction'))

    def test_declaring_the_tail_resolves_the_abstention(self):
        raw = 't(29) = 1.80, p = .04'
        base, reason = ref.parse_expression(raw, 'regression')
        self.assertIsNone(reason)
        greater = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(base, alternative='greater')]})['checks'][0]
        self.assertEqual(greater['status'], 'VERIFIED')
        self.assertEqual(greater['details']['alternative_source'], 'caller')
        two_sided = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(base, alternative='two-sided')]})['checks'][0]
        self.assertEqual(two_sided['status'], 'REFUTED')
        self.assertEqual(two_sided['details']['alternative_source'], 'caller')

    def test_supplying_corrected_df_resolves_the_abstention(self):
        # Exactly representable corrected df (epsilon=0.75 of df 2,30) with a printed p
        # that matches the corrected calculation yields a real verdict, not abstention.
        result = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(id='corr', kind='statistic_consistency', test='F', df=['1.5', '22.5'],
                 df_precision='exact', statistic='3.46', reported_p='.06', relation='=')]})['checks'][0]
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertNotIn('possible_undeclared_df_correction', result['details'])

    def test_caller_declared_context_never_uses_the_abstention(self):
        # A caller who explicitly declares two-sided owns that assumption; the engine
        # must not silently abstain on their behalf.
        result = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(id='decl', kind='statistic_consistency', test='t', df=[29],
                 statistic='1.80', reported_p='.04', relation='=', alternative='two-sided')]})['checks'][0]
        self.assertEqual(result['status'], 'REFUTED')
        self.assertNotIn('possible_undeclared_one_tailed', result['details'])

    def test_negative_statistic_z_and_greater_relation_paths(self):
        # Negative t uses the 'less' tail; the abstention must still fire symmetrically.
        neg = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(id='neg', kind='statistic_consistency', test='t', df=[29],
                 statistic='-1.80', reported_p='.04', relation='=')]})['checks'][0]
        self.assertEqual(neg['status'], 'UNDETERMINED')
        self.assertTrue(neg['details']['possible_undeclared_one_tailed'])
        # z uses the normal distribution through the same default-tail path.
        z = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(id='z', kind='statistic_consistency', test='z', df=[],
                 statistic='1.80', reported_p='.04', relation='=')]})['checks'][0]
        self.assertEqual(z['status'], 'UNDETERMINED')
        self.assertTrue(z['details']['possible_undeclared_one_tailed'])
        # A '>' t report refuted under both tails stays REFUTED (covers the '>' branch).
        gt = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(id='gt', kind='statistic_consistency', test='t', df=[29],
                 statistic='1.80', reported_p='.09', relation='>')]})['checks'][0]
        self.assertEqual(gt['status'], 'REFUTED')
        # An upward F discrepancy reported as '>' abstains via the correction bound.
        fgt = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(id='fgt', kind='statistic_consistency', test='F', df=[2, 30],
                 statistic='3.46', reported_p='.05', relation='>')]})['checks'][0]
        self.assertEqual(fgt['status'], 'UNDETERMINED')
        self.assertTrue(fgt['details']['possible_undeclared_df_correction'])

    def test_verified_and_chi_square_and_rounding_guards_unchanged(self):
        # A matching default two-sided report stays VERIFIED (abstention never overturns it).
        ok = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(id='ok', kind='statistic_consistency', test='t', df=[12],
                 statistic='2.400', reported_p='0.03', relation='=')]})['checks'][0]
        self.assertEqual(ok['status'], 'VERIFIED')
        # chi-square has no one-tailed/sphericity escape; a bad report stays REFUTED.
        chi = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(id='chi', kind='statistic_consistency', test='chi2', df=[2],
                 statistic='10.000', reported_p='.0001', relation='<')]})['checks'][0]
        self.assertEqual(chi['status'], 'REFUTED')
        # A p far from any one-tailed value stays REFUTED (rounding guard from the suite).
        far = verify_toolkit_spec({'schema_version': '1.0', 'checks': [
            dict(id='far', kind='statistic_consistency', test='t', df=[12],
                 statistic='2.400', reported_p='0.5', relation='=')]})['checks'][0]
        self.assertEqual(far['status'], 'REFUTED')


if __name__ == '__main__':
    unittest.main()
