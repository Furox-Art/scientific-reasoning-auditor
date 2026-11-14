"""Strict dependency-independent inputs for dependent-data and exact sensitivity checks."""
from fractions import Fraction

DEPENDENT_KINDS = ('cluster_robust_regression', 'correlated_meta_analysis', 'missing_binary_sensitivity')


def _numeric(value, low, high):
    from sra.toolkit_spec import number
    text = str(number(value))
    if not Fraction(str(low)) <= Fraction(text) <= Fraction(str(high)):
        raise ValueError('Dependent-data numeric value is outside the supported range.')
    return text


def _identifier(value, seen):
    from sra.toolkit_spec import _NAME
    if not isinstance(value, str) or not _NAME.fullmatch(value) or value in seen:
        raise ValueError('Declare distinct simple identifiers.')
    seen.add(value)


def _covariance(value, size):
    if not isinstance(value, list) or len(value) != size or any(not isinstance(row, list) or len(row) != size for row in value):
        raise ValueError('Covariance dimensions must match study order.')
    result = [[_numeric(v, -1e12, 1e12) for v in row] for row in value]
    exact = [[Fraction(v) for v in row] for row in result]
    for i in range(size):
        if not Fraction('1e-12') <= exact[i][i] <= Fraction('1e12'):
            raise ValueError('Covariance diagonal must be positive and bounded.')
        for j in range(i):
            if exact[i][j] != exact[j][i] or exact[i][j]**2 > exact[i][i]*exact[j][j]:
                raise ValueError('Covariance must be exactly symmetric with feasible pairwise bounds.')
    return result


def prepare_dependent(item):
    from sra.toolkit_spec import _fields, _text
    kind, base = item['kind'], ('id', 'kind')
    result = dict(item)
    if kind == 'cluster_robust_regression':
        _fields(item, base+('x', 'y', 'clusters'), ('terms', 'alpha', 'leave_one_cluster_out'))
        x, y, clusters = item['x'], item['y'], item['clusters']
        if (not isinstance(x, list) or not 6 <= len(x) <= 5000 or not isinstance(x[0], list) or
                not 1 <= len(x[0]) <= 8 or any(not isinstance(row, list) or len(row) != len(x[0]) for row in x) or
                not isinstance(y, list) or not isinstance(clusters, list) or len(y) != len(x) or len(clusters) != len(x)):
            raise ValueError('Regression requires 6..5000 paired rows, 1..8 predictors and aligned cluster IDs.')
        for ident in clusters:
            if _text(ident, 64) != ident.strip():
                raise ValueError('Cluster IDs must not have surrounding whitespace.')
        count = len(set(clusters))
        if count < 3 or count <= len(x[0])+1:
            raise ValueError('Require at least three clusters and more clusters than fitted coefficients.')
        leave = item.get('leave_one_cluster_out', False)
        if type(leave) is not bool or (leave and count > 50):
            raise ValueError('Cluster omission is boolean and limited to 50 clusters.')
        terms = item.get('terms', [f'x{i+1}' for i in range(len(x[0]))])
        if not isinstance(terms, list) or len(terms) != len(x[0]):
            raise ValueError('Term names must match predictor columns.')
        seen = {'intercept'}
        for name in terms:
            _identifier(name, seen)
        result.update(x=[[_numeric(v, -1e12, 1e12) for v in row] for row in x],
                      y=[_numeric(v, -1e12, 1e12) for v in y], terms=terms,
                      leave_one_cluster_out=leave, alpha=_numeric(item.get('alpha', '.05'), '.001', '.2'))
    elif kind == 'correlated_meta_analysis':
        _fields(item, base+('studies', 'covariance', 'effect_scale'), ('alpha', 'covariance_scenarios'))
        studies = item['studies']
        if not isinstance(studies, list) or not 2 <= len(studies) <= 30 or item['effect_scale'] not in ('mean_difference', 'standardized_mean_difference', 'log_risk_ratio', 'log_odds_ratio'):
            raise ValueError('Declare 2..30 estimates on one supported common effect scale.')
        seen, normalized = set(), []
        for row in studies:
            _fields(row, ('id', 'effect'))
            _identifier(row['id'], seen)
            normalized.append(dict(id=row['id'], effect=_numeric(row['effect'], -1e6, 1e6)))
        covariance = _covariance(item['covariance'], len(studies))
        scenarios = item.get('covariance_scenarios', [])
        if not isinstance(scenarios, list) or len(scenarios) > 5:
            raise ValueError('Supply at most five named covariance scenarios.')
        seen, alternatives = set(), []
        for row in scenarios:
            _fields(row, ('id', 'covariance'))
            _identifier(row['id'], seen)
            matrix = _covariance(row['covariance'], len(studies))
            if any(Fraction(matrix[i][i]) != Fraction(covariance[i][i]) for i in range(len(studies))):
                raise ValueError('Cross-covariance scenarios must preserve diagonal variances.')
            alternatives.append(dict(id=row['id'], covariance=matrix))
        result.update(studies=normalized, covariance=covariance, covariance_scenarios=alternatives,
                      alpha=_numeric(item.get('alpha', '.05'), '.001', '.2'))
    else:
        _fields(item, base+('treatment', 'control'), ('threshold', 'control_missing_events_grid'))
        for arm in ('treatment', 'control'):
            row = item[arm]
            _fields(row, ('events', 'observed', 'missing'))
            if (any(type(row[key]) is not int for key in row) or not 1 <= row['observed'] <= 1000000 or
                    not 0 <= row['events'] <= row['observed'] or not 0 <= row['missing'] <= 1000000-row['observed']):
                raise ValueError('Binary counts require valid integer events/observed/missing and total <=1000000 per arm.')
        missing = item['control']['missing']
        grid = item.get('control_missing_events_grid', sorted({0, missing//2, missing}))
        if not isinstance(grid, list) or not 1 <= len(grid) <= 100 or any(type(v) is not int or not 0 <= v <= missing for v in grid) or len(set(grid)) != len(grid):
            raise ValueError('Control missing-event grid requires 1..100 distinct feasible integer counts.')
        result.update(threshold=_numeric(item.get('threshold', '0'), -1, 1), control_missing_events_grid=sorted(grid))
    return result
