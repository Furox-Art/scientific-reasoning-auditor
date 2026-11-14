"""Conditional dependent-data calculations with explicit numerical abstention."""
import math
from fractions import Fraction

from sra.research_checks import _numeric


def _unknown(reason):
    return dict(meaning='Calculation is unassessed: '+reason+'. No scientific validity verdict.',
                unassessed_checks=[reason])


def _guarded(operation):
    status, details = _numeric(operation)
    if status == 'CALCULATED' and details.get('unassessed_checks'):
        status = 'UNDETERMINED'
    return status, details


def _collapsed(values):
    return len({Fraction(v) for v in values}) != len({float(v) for v in values})


def _linear_fit(x, y, np):
    means = np.mean(x, axis=0)
    centered = x-means
    scales = np.max(np.abs(centered), axis=0)
    if np.any(scales == 0):
        return None
    z = np.column_stack([np.ones(len(y)), centered/scales])
    condition = float(np.linalg.cond(z))
    if not math.isfinite(condition) or condition > 1e8 or np.linalg.matrix_rank(z) != z.shape[1]:
        return None
    q, r = np.linalg.qr(z, mode='reduced')
    # Center y before QR to avoid avoidable cancellation from a large outcome offset.
    location = float(np.mean(y))
    beta_z = np.linalg.solve(r, q.T@(y-location))
    residuals = (y-location)-z@beta_z
    residual_norm = float(np.linalg.norm(residuals))
    resolution = float(32*np.finfo(float).eps*max(z.shape)*
                       (np.linalg.norm(y-location)+np.linalg.norm(z@beta_z)))
    beta_z[0] += location
    transform = np.zeros((z.shape[1], z.shape[1]))
    transform[0, 0] = 1
    transform[0, 1:] = -means/scales
    transform[1:, 1:] = np.diag(1/scales)
    return dict(z=z, r=r, residuals=residuals, transform=transform,
                beta=transform@beta_z, condition=condition,
                residual_norm=residual_norm, residual_resolution=resolution)


def cluster_robust_regression(item, scipy_stats):
    import numpy as np
    def calculate():
        series = list(zip(*item['x']))+[item['y']]
        if any(_collapsed(values) for values in series):
            return _unknown('input_values_collapse_in_float64')
        x, y = np.asarray(item['x'], dtype=float), np.asarray(item['y'], dtype=float)
        fit = _linear_fit(x, y, np)
        if fit is None:
            return _unknown('rank_deficient_or_ill_conditioned_design')
        clusters = sorted(set(item['clusters']))
        indices = np.asarray(item['clusters'])
        n, k, g = len(y), fit['z'].shape[1], len(clusters)
        correction = g/(g-1)*(n-1)/(n-k)
        covariance = None
        resolved = fit['residual_norm'] > fit['residual_resolution']
        se_resolution = np.zeros(k)
        if resolved:
            r_inv = np.linalg.solve(fit['r'], np.eye(k))
            influences, errors = [], []
            for cluster in clusters:
                mask = indices == cluster
                score = fit['z'][mask].T@fit['residuals'][mask]
                influences.append(fit['transform']@(r_inv@(r_inv.T@score)))
                score_error = (32*np.finfo(float).eps*max(fit['z'][mask].shape)*
                               (np.abs(fit['z'][mask]).T@np.abs(fit['residuals'][mask])))
                # QR/prediction rounding enters the scores through residuals as
                # well as through the final dot product. Propagate its L2 guard
                # by Cauchy-Schwarz for each normalized predictor column.
                score_error += np.linalg.norm(fit['z'][mask], axis=0)*fit['residual_resolution']
                errors.append(np.abs(fit['transform'])@(np.abs(r_inv)@(np.abs(r_inv.T)@score_error)))
            influences = np.asarray(influences)
            covariance = correction*influences.T@influences
            se_resolution = math.sqrt(correction)*np.linalg.norm(np.asarray(errors), axis=0)
        critical = float(scipy_stats.t.isf(float(item['alpha'])/2, g-1))
        coefficients, unknown = [], [] if resolved else ['residuals_below_numeric_resolution']
        for i, name in enumerate(['intercept']+item['terms']):
            estimate = float(fit['beta'][i])
            se = math.sqrt(float(covariance[i, i])) if resolved else None
            record = dict(term=name, estimate=estimate, standard_error=se,
                          standard_error_resolution_bound=float(se_resolution[i]) if resolved else None,
                          t_statistic=None, p_value=None, confidence_interval=None)
            if se is None:
                coefficients.append(record)
                continue
            if se <= se_resolution[i]:
                record['standard_error'] = None
                unknown.append('unresolved_cluster_score_uncertainty:'+name)
            else:
                statistic = estimate/se
                p_value = float(2*scipy_stats.t.sf(abs(statistic), g-1))
                interval = [estimate-critical*se, estimate+critical*se]
                if interval[0] < estimate < interval[1]:
                    record['confidence_interval'] = interval
                else:
                    unknown.append('confidence_interval_resolution_lost:'+name)
                if not math.isfinite(statistic) or not math.isfinite(p_value) or not 0 < p_value <= 1:
                    unknown.append('unusable_tail_probability:'+name)
                else:
                    record.update(t_statistic=statistic, p_value=p_value)
            coefficients.append(record)
        omissions = []
        if item['leave_one_cluster_out']:
            for cluster in clusters:
                mask = indices != cluster
                omitted = _linear_fit(x[mask], y[mask], np)
                if omitted is None:
                    omissions.append(dict(cluster=cluster, status='UNDETERMINED', reason='omission_design_unidentified'))
                    unknown.append('cluster_omission:'+cluster)
                else:
                    omissions.append(dict(cluster=cluster, status='CALCULATED',
                        coefficients=[float(v) for v in omitted['beta']],
                        changes=[float(v) for v in omitted['beta']-fit['beta']]))
        return dict(meaning='OLS mean model with one-way CR1 cluster covariance and t(G-1) inference; independence between clusters, mean specification and small-cluster reliability are not verified. Omissions refit coefficients only, not cluster inference.',
                    nobs=n, coefficient_count=k, cluster_count=g, inference_df=g-1,
                    correction_factor=correction, design_condition_number=fit['condition'],
                    covariance_method='CR1', covariance=covariance.tolist() if resolved and all(c['standard_error'] is not None for c in coefficients) else None, coefficients=coefficients,
                    residual_l2_norm=fit['residual_norm'], residual_resolution_bound=fit['residual_resolution'],
                    alpha=float(item['alpha']), leave_one_cluster_out=omissions, unassessed_checks=unknown,
                    assumptions_verified=False, small_cluster_inference_certified=False)
    return _guarded(calculate)


def correlated_meta_analysis(item, scipy_stats):
    import numpy as np
    from scipy.linalg import cho_factor, solve_triangular
    effects = np.asarray([row['effect'] for row in item['studies']], dtype=float)
    def pool(values, matrix):
        covariance = np.asarray(matrix, dtype=float)
        try:
            factor = cho_factor(covariance, lower=True, check_finite=True)
        except np.linalg.LinAlgError:
            return _unknown('covariance_not_positive_definite')
        condition = float(np.linalg.cond(covariance))
        if not math.isfinite(condition) or condition > 1e10:
            return _unknown('ill_conditioned_covariance')
        whitened_one = solve_triangular(factor[0], np.ones(len(values)), lower=True)
        location = float(values[0])
        whitened_values = solve_triangular(factor[0], values-location, lower=True)
        information = float(whitened_one@whitened_one)
        if not math.isfinite(information) or information <= 0:
            return _unknown('nonpositive_pooling_information')
        weights = solve_triangular(factor[0].T, whitened_one, lower=False)/information
        delta = float(whitened_one@whitened_values/information)
        estimate, se = location+delta, math.sqrt(1/information)
        residuals = whitened_values-delta*whitened_one
        q = float(residuals@residuals)
        critical = float(scipy_stats.norm.isf(float(item['alpha'])/2))
        interval = [estimate-critical*se, estimate+critical*se]
        resolved = interval[0] < estimate < interval[1]
        return dict(estimate=estimate, standard_error=se, weights=[float(w) for w in weights],
                    confidence_interval=interval if resolved else None,
                    unassessed_checks=[] if resolved else ['confidence_interval_resolution_lost'],
                    covariance_condition_number=condition, q=q, q_df=len(values)-1)
    def calculate():
        if _collapsed([study['effect'] for study in item['studies']]):
            return _unknown('input_values_collapse_in_float64')
        baseline = pool(effects, item['covariance'])
        if 'estimate' not in baseline:
            return baseline
        unknown, omissions, scenarios = baseline.pop('unassessed_checks'), [], []
        probability = float(scipy_stats.chi2.sf(baseline['q'], baseline['q_df']))
        baseline['q_p_value'] = probability if math.isfinite(probability) and 0 < probability <= 1 else None
        if baseline['q_p_value'] is None:
            unknown.append('heterogeneity_tail_probability')
        covariance = np.asarray(item['covariance'], dtype=float)
        for i, study in enumerate(item['studies']):
            keep = np.arange(len(effects)) != i
            result = pool(effects[keep], covariance[np.ix_(keep, keep)])
            if 'estimate' not in result:
                unknown.append('estimate_omission:'+study['id'])
                omissions.append(dict(omitted_study=study['id'], status='UNDETERMINED', **result))
            else:
                omissions.append(dict(omitted_study=study['id'], status='CALCULATED',
                                      estimate=result['estimate'], standard_error=result['standard_error']))
        for scenario in item['covariance_scenarios']:
            result = pool(effects, scenario['covariance'])
            status = 'UNDETERMINED' if result.get('unassessed_checks') else 'CALCULATED'
            if status == 'UNDETERMINED':
                unknown.append('covariance_scenario:'+scenario['id'])
            scenarios.append(dict(id=scenario['id'], status=status, **result))
        return dict(meaning='Common-effect GLS using supplied fixed sampling covariance; normal intervals and generalized Q are conditional on that covariance/model. Negative weights are possible, not probabilities. No random/multilevel heterogeneity model is estimated.',
                    **baseline, model='common_effect_known_covariance', effect_scale=item['effect_scale'],
                    study_order=[s['id'] for s in item['studies']], alpha=float(item['alpha']),
                    leave_one_out=omissions, covariance_scenarios=scenarios, unassessed_checks=unknown,
                    covariance_authenticity_verified=False, assumptions_verified=False)
    return _guarded(calculate)


def missing_binary_sensitivity(item, backend):
    treatment, control = item['treatment'], item['control']
    nt, nc = (arm['observed']+arm['missing'] for arm in (treatment, control))
    et, ec, mt, mc = treatment['events'], control['events'], treatment['missing'], control['missing']
    threshold = Fraction(item['threshold'])
    lower, upper = Fraction(et, nt)-Fraction(ec+mc, nc), Fraction(et+mt, nt)-Fraction(ec, nc)
    frontier = []
    for b in item['control_missing_events_grid']:
        boundary = nt*(threshold+Fraction(ec+b, nc))-et
        minimum = max(0, math.floor(boundary)+1)
        frontier.append(dict(control_missing_events=b, minimum_treatment_missing_events=minimum if minimum <= mt else None))
    complete = Fraction(et, treatment['observed'])-Fraction(ec, control['observed'])
    return 'CALCULATED', dict(meaning='Exact deterministic risk-difference bounds and strict threshold tipping counts over binary missing outcomes; no significance test, missingness mechanism, imputation model or treatment-benefit conclusion.',
        direction='treatment_minus_control', threshold_exact=str(threshold), comparison='strictly_greater_than',
        complete_case_risk_difference=float(complete), complete_case_risk_difference_exact=str(complete),
        risk_difference_bounds=dict(lower=float(lower), upper=float(upper), lower_exact=str(lower), upper_exact=str(upper)),
        threshold_status='all_above_threshold' if lower > threshold else 'none_above_threshold' if upper <= threshold else 'depends_on_missing_outcomes',
        totals=dict(treatment=nt, control=nc), tipping_frontier=frontier, sampling_uncertainty_assessed=False,
        missingness_assumptions_verified=False)
