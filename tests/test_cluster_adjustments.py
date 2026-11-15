"""Independent dense/sampling identities for bounded CR2/CR3; no empirical labels."""
import copy
import unittest
from unittest.mock import patch

from test_dependent_data import clustered, run
from sra.toolkit_spec import prepare_toolkit_spec


class ClusterAdjustmentTests(unittest.TestCase):
    def test_adjusted_covariance_matches_independent_dense_construction(self):
        import numpy as np
        item = clustered()
        x = np.column_stack([np.ones(len(item['y'])), item['x']])
        y = np.asarray(item['y'], dtype=float)
        bread = np.linalg.inv(x.T@x)
        residuals = y-x@np.linalg.lstsq(x, y, rcond=None)[0]
        for method, power in [('CR2', -.5), ('CR3', -1.)]:
            meat = np.zeros((2, 2))
            for cluster in sorted(set(item['clusters'])):
                mask = np.asarray(item['clusters']) == cluster
                block = np.eye(sum(mask))-x[mask]@bread@x[mask].T
                eigenvalues, eigenvectors = np.linalg.eigh(block)
                adjusted = eigenvectors@np.diag(eigenvalues**power)@eigenvectors.T@residuals[mask]
                score = x[mask].T@adjusted
                meat += np.outer(score, score)
            result = run({**item, 'covariance_method': method})
            self.assertEqual(result['status'], 'CALCULATED')
            details = result['details']
            self.assertEqual(details['covariance_method'], method)
            self.assertEqual(details['correction_factor'], 1.)
            self.assertEqual(details['inference_df'], 3)
            np.testing.assert_allclose(details['covariance'], bread@meat@bread, rtol=1e-10, atol=1e-12)

    def test_cr3_equals_uncentered_delete_cluster_coefficient_differences(self):
        import numpy as np
        item = clustered()
        result = run({**item, 'covariance_method': 'CR3'})['details']
        differences = np.asarray([row['changes'] for row in result['leave_one_cluster_out']])
        np.testing.assert_allclose(result['covariance'], differences.T@differences, rtol=1e-10, atol=1e-12)

    def test_cr2_identity_working_model_covariance_identity(self):
        import numpy as np
        item = clustered(); item['covariance_method'] = 'CR2'; item['leave_one_cluster_out'] = False
        x = np.column_stack([np.ones(12), item['x']]); target = np.linalg.inv(x.T@x)
        # Sum over all unit disturbances exactly computes E[Vhat] for iid unit
        # errors because every fitted residual/adjusted score is linear in y.
        actual = np.zeros((2, 2))
        for column in np.eye(12):
            result = run({**item, 'y': column.tolist()})
            self.assertEqual(result['status'], 'CALCULATED')
            actual += result['details']['covariance']
        np.testing.assert_allclose(actual, target, rtol=1e-10, atol=1e-12)

    def test_singleton_clusters_match_hc2_and_unscaled_hc3(self):
        import numpy as np
        from statsmodels.regression.linear_model import OLS
        item = clustered(); item['clusters'] = [str(i) for i in range(12)]
        x = np.column_stack([np.ones(12), item['x']]); fit = OLS(item['y'], x).fit()
        for method, hc in [('CR2', 'HC2'), ('CR3', 'HC3')]:
            result = run({**item, 'covariance_method': method})
            self.assertEqual(result['status'], 'CALCULATED')
            np.testing.assert_allclose(result['details']['covariance'], fit.get_robustcov_results(hc).cov_params(), rtol=1e-10, atol=1e-12)

    def test_leverage_and_perfect_fit_abstain_while_retaining_estimates(self):
        for method in ('CR2', 'CR3'):
            item = clustered(); item['covariance_method'] = method; item['leave_one_cluster_out'] = False
            item['x'] = [[1]]*3+[[0]]*9
            result = run(item)
            self.assertEqual(result['status'], 'UNDETERMINED')
            self.assertIsNone(result['details']['covariance'])
            self.assertIn('unresolved_cluster_leverage', result['details']['unassessed_checks'])
            self.assertEqual(len(result['details']['coefficients']), 2)
            item = clustered(); item['covariance_method'] = method
            item['y'] = [3+2*row[0] for row in item['x']]
            self.assertEqual(run(item)['status'], 'UNDETERMINED')

    def test_adjustments_preserve_units_order_and_cr1_default(self):
        import numpy as np
        item = clustered(); before = copy.deepcopy(item)
        self.assertEqual(run(item), run({**item, 'covariance_method': 'CR1'}))
        for method in ('CR2', 'CR3'):
            baseline = run({**item, 'covariance_method': method})['details']
            transformed = {**item, 'covariance_method': method,
                           'x': [[100+10*row[0]] for row in item['x']]}
            change = np.asarray([[1, -10], [0, .1]])
            np.testing.assert_allclose(run(transformed)['details']['covariance'], change@baseline['covariance']@change.T, rtol=1e-10, atol=1e-12)
            reordered = {**item, 'covariance_method': method,
                         **{key: list(reversed(item[key])) for key in ('x', 'y', 'clusters')}}
            np.testing.assert_allclose(run(reordered)['details']['covariance'], baseline['covariance'], rtol=1e-10, atol=1e-12)
        self.assertEqual(item, before)

    def test_method_is_validated_before_any_backend(self):
        for method in ('HC2', 'CR4', None, [], True):
            with self.subTest(method=method), patch('sra.toolkit._backend', side_effect=AssertionError('No backend')):
                with self.assertRaises(ValueError):
                    prepare_toolkit_spec(dict(schema_version='1.0', checks=[{**clustered(), 'covariance_method': method}]))


if __name__ == '__main__':
    unittest.main()
