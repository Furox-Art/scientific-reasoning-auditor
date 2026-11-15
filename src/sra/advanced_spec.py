"""Bounded, dependency-independent inputs for three explicitly scoped methods."""
from fractions import Fraction

ADVANCED_KINDS = ('multilevel_meta_analysis', 'wild_cluster_bootstrap', 'cluster_power_analysis')
SCALES = ('mean_difference', 'standardized_mean_difference', 'log_risk_ratio', 'log_odds_ratio')


def prepare_advanced(item):
    from sra.toolkit_spec import _fields, _text
    from sra.dependent_spec import _numeric, _identifier, _covariance, prepare_dependent
    kind, base = item['kind'], ('id', 'kind')
    result = dict(item)
    if kind == 'multilevel_meta_analysis':
        _fields(item, base+('studies', 'covariance', 'effect_scale', 'tau2_max'), ('alpha',))
        studies = item['studies']
        if not isinstance(studies, list) or not 3 <= len(studies) <= 30 or item['effect_scale'] not in SCALES:
            raise ValueError('Declare 3..30 effects on one supported scale.')
        seen, normalized = set(), []
        for row in studies:
            _fields(row, ('id', 'group', 'effect'))
            _identifier(row['id'], seen)
            group = _text(row['group'], 64)
            if group != group.strip():
                raise ValueError('Group IDs must not have surrounding whitespace.')
            normalized.append(dict(id=row['id'], group=group, effect=_numeric(row['effect'], -1e6, 1e6)))
        if len({row['group'] for row in normalized}) < 3:
            raise ValueError('At least three declared groups are required.')
        result.update(studies=normalized, covariance=_covariance(item['covariance'], len(studies)),
                      tau2_max=_numeric(item['tau2_max'], '1e-12', '1e12'),
                      alpha=_numeric(item.get('alpha', '.05'), '.001', '.2'))
    elif kind == 'wild_cluster_bootstrap':
        _fields(item, base+('x', 'y', 'clusters', 'term'), ('terms', 'null_value'))
        regression = prepare_dependent({key: value for key, value in item.items()
            if key not in ('term', 'null_value')} | {'kind': 'cluster_robust_regression'})
        if len(regression['x']) > 500 or len(regression['terms']) > 4 or len(set(regression['clusters'])) > 10:
            raise ValueError('Exhaustive bootstrap supports at most 500 rows, 4 predictors and 10 clusters.')
        if item['term'] not in regression['terms']:
            raise ValueError('Bootstrap term must name a declared predictor, not the intercept.')
        result.update({key: regression[key] for key in ('x', 'y', 'clusters', 'terms')})
        result['null_value'] = _numeric(item.get('null_value', '0'), -1e6, 1e6)
    else:
        mode = item.get('mode')
        if mode not in ('calculate', 'sample_size'):
            raise ValueError('Cluster power mode must be calculate or sample_size.')
        required = ('clusters_per_arm',) if mode == 'calculate' else ('target_power',)
        _fields(item, base+('mode', 'cluster_size', 'icc', 'effect_size')+required,
                ('alpha',)+(() if mode == 'calculate' else ('max_clusters_per_arm',)))
        m = item['cluster_size']
        if type(m) is not int or not 1 <= m <= 100000:
            raise ValueError('Cluster size must be an integer in [1,100000].')
        key = 'clusters_per_arm' if mode == 'calculate' else 'max_clusters_per_arm'
        k = item.get(key, 10000)
        if type(k) is not int or not 2 <= k <= 10000:
            raise ValueError('Clusters per arm must be an integer in [2,10000].')
        result.update({key: k}, icc=_numeric(item['icc'], 0, 1),
                      effect_size=_numeric(item['effect_size'], 0, 10),
                      alpha=_numeric(item.get('alpha', '.05'), '.001', '.2'))
        if mode == 'sample_size':
            target = _numeric(item['target_power'], '.001', '.9999')
            if Fraction(target) <= Fraction(result['alpha']):
                raise ValueError('Target power must exceed alpha.')
            result['target_power'] = target
    return result
