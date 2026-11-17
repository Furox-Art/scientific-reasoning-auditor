"""Conservative normal-model confidence bounds; no measurement-validity claim."""
import importlib
import math
import warnings

from sra.provenance import _package_version


def _stats():
    return importlib.import_module('scipy.stats')


def normal_agreement_confidence(mean, sd, n, requested_level):
    """Propagate a Bonferroni mean/SD confidence rectangle to mu +/- 1.96 sigma.

    Each two-sided mean/SD interval has error alpha/2. The union bound gives
    simultaneous coverage >= 1-alpha under independent normal differences.
    This construction is conservative; it is not an exact joint LoA interval.
    """
    level = float(requested_level)
    common = dict(requested_confidence_level=requested_level, confidence_level=level,
                  method='bonferroni_mean_sd_rectangle', df=n - 1,
                  backend='scipy.stats', backend_version=_package_version('scipy'),
                  meaning='Simultaneous conservative confidence bounds for normal population mu +/- 1.96 sigma, conditional on independent normal differences. Not a prediction interval, general validity certificate or probability that the assumptions are true.')
    try:
        stats = _stats()
        from sra.toolkit import _STATISTICS_LOCK
        with _STATISTICS_LOCK, warnings.catch_warnings(record=True) as numerical_warnings:
            warnings.simplefilter('always')
            tail = (1 - level) / 4
            t = float(stats.t.ppf(1 - tail, n - 1))
            chi_low = float(stats.chi2.ppf(tail, n - 1))
            chi_high = float(stats.chi2.ppf(1 - tail, n - 1))
        if numerical_warnings or not all(math.isfinite(value) for value in (t, chi_low, chi_high)) or not (t > 0 and 0 < chi_low < chi_high):
            return dict(common, status='UNDETERMINED', reason='invalid_or_warned_quantiles')
        margin = t * sd / math.sqrt(n)
        mean_bounds = [mean - margin, mean + margin]
        sd_bounds = [sd * math.sqrt((n - 1) / chi_high), sd * math.sqrt((n - 1) / chi_low)]
        lower = [mean_bounds[0] - 1.96 * sd_bounds[1], mean_bounds[1] - 1.96 * sd_bounds[0]]
        upper = [mean_bounds[0] + 1.96 * sd_bounds[0], mean_bounds[1] + 1.96 * sd_bounds[1]]
        values = mean_bounds + sd_bounds + lower + upper
        if not all(math.isfinite(value) for value in values) or not (mean_bounds[0] < mean_bounds[1] and 0 < sd_bounds[0] < sd_bounds[1] and lower[0] < lower[1] and upper[0] < upper[1]):
            return dict(common, status='UNDETERMINED', reason='invalid_confidence_bounds')
        # Final endpoint ULPs alone miss cancellation of much larger terms.
        # Include the construction scale and a conservative quantile/roundoff
        # safety margin. This is deliberately not a certified error enclosure.
        terms = values + [mean, sd, margin]
        scale = max(abs(value) for value in terms)
        guard = max(scale * 1e-10, 16 * max(math.ulp(value) for value in terms))
        return dict(common, status='CALCULATED', marginal_confidence_level=(1 + level) / 2,
                    numerical_guard=dict(absolute=guard, construction_scale=scale,
                                         relative_margin=1e-10, certified_error_bound=False),
                    mean_interval=mean_bounds, sd_interval=sd_bounds,
                    lower_limit_interval=lower, upper_limit_interval=upper,
                    quantiles=dict(t=t, chi_square_lower=chi_low, chi_square_upper=chi_high))
    except ImportError:
        return dict(common, status='UNDETERMINED', reason='optional_backend_unavailable')
    except (ArithmeticError, ValueError, RuntimeError, TypeError):
        return dict(common, status='UNDETERMINED', reason='confidence_backend_did_not_complete')


def confidence_decision(region, bounds):
    low, high = region['lower_limit_interval'], region['upper_limit_interval']
    comparisons = ((low[0], bounds[0]), (high[1], bounds[1]),
                   (low[1], bounds[0]), (high[0], bounds[1]))
    if any(abs(value - bound) <= max(region['numerical_guard']['absolute'], 16 * max(math.ulp(value), math.ulp(bound)))
           for value, bound in comparisons):
        return 'UNDETERMINED'
    if low[0] >= bounds[0] and high[1] <= bounds[1]:
        return 'VERIFIED'
    if low[1] < bounds[0] or high[0] > bounds[1]:
        return 'REFUTED'
    return 'UNDETERMINED'
