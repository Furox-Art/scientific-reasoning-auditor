"""Additional independently reproducible summary-statistics checks.

These calculations verify arithmetic conditional on user-provided statistics.
They do not validate raw data, sampling, experimental design or assumptions.
"""
from __future__ import annotations

import math
from typing import Any

from sra.stats import _compare_reported, _finite_number, _finite_result, _group, _display_precision_tolerance, _json_safe_report_value


SUPPORTED_TESTS = ("welch_t", "one_sample_t", "paired_t", "chi_square_2x2", "fisher_exact_2x2")


def _settings(spec: dict[str, Any], calculated: dict[str, float]) -> tuple[list[dict], str]:
    raw = spec.get("tolerances", {})
    if not isinstance(raw, dict):
        raise ValueError("tolerances must be an object.")
    tolerances = {key: _finite_number(value, f"tolerances.{key}") for key, value in raw.items()}
    if any(t < 0 for t in tolerances.values()):
        raise ValueError("Tolerances must be non-negative.")
    reported = spec.get("reported", {})
    if not isinstance(reported, dict):
        raise ValueError("reported must be an object.")
    for key, value in reported.items():
        if key in calculated:
            _finite_number(value, f"reported.{key}")
            if key in ("p_two_sided", "p_value") and not 0 < float(value) <= 1:
                raise ValueError(f"reported.{key} must be > 0 and <= 1; do not encode p=0.")
            if key not in tolerances and "default" not in tolerances:
                _display_precision_tolerance(value)
        else:
            _json_safe_report_value(value, f"reported.{key}")
    checks = _compare_reported(calculated, reported, tolerances)
    if any(item["status"] == "FAIL" for item in checks):
        status = "FAIL"
    elif not checks or any(item["status"] == "NOT_VERIFIED" for item in checks):
        status = "PARTIAL"
    else:
        status = "PASS"
    return checks, status


def _scipy_stats():
    try:
        from scipy import stats
    except ImportError as exc:
        raise RuntimeError(
            "Extended statistics verification requires SciPy. "
            "Install scientific-reasoning-auditor[statistics]."
        ) from exc
    return stats


def _valid_probability(value: Any, name: str = "p_two_sided") -> float:
    p = _finite_result(float(value), name)
    if not 0 < p <= 1:
        raise ValueError(f"{name} must be in (0, 1]; avoid reporting underflowed p=0.")
    return p


def _table_2x2(spec: dict[str, Any]) -> list[list[int]]:
    table = spec.get("table")
    if (not isinstance(table, list) or len(table) != 2
            or any(not isinstance(row, list) or len(row) != 2 for row in table)):
        raise ValueError("table must contain exactly two rows of two counts.")
    for i, row in enumerate(table):
        for j, count in enumerate(row):
            if type(count) is not int or count < 0:
                raise ValueError(f"table[{i}][{j}] must be a non-negative integer.")
            if count > 2**53:
                raise ValueError("Contingency-table counts exceed exact float integer precision.")
    if not any(table[0]) or not any(table[1]):
        raise ValueError("Each table row must contain a positive count.")
    if table[0][0] + table[1][0] == 0 or table[0][1] + table[1][1] == 0:
        raise ValueError("Each table column must contain a positive count.")
    if sum(map(sum, table)) > 2**53:
        raise ValueError("Total contingency-table count exceeds exact float integer precision.")
    return table


def verify_extended_stats(spec: dict[str, Any], input_sha256: str | None = None) -> dict[str, Any]:
    if not isinstance(spec, dict):
        raise ValueError("Statistics input must be an object.")
    test = spec.get("test")
    if test not in SUPPORTED_TESTS[1:]:
        raise ValueError(f"Supported extended tests: {', '.join(SUPPORTED_TESTS[1:])}.")
    stats = _scipy_stats()
    calculated: dict[str, float]
    extra: dict[str, Any] = {}
    warnings: list[str] = []
    assumptions: list[str]
    method: str

    if test in ("one_sample_t", "paired_t"):
        key = "sample" if test == "one_sample_t" else "differences"
        mean, sd, n = _group(spec, key)
        null_mean = _finite_number(spec.get("mu0", 0), "mu0")
        if sd == 0:
            raise ValueError(f"{key}.sd must be positive to calculate a t statistic.")
        mean_difference = _finite_result(mean - null_mean, "mean difference")
        standard_error = _finite_result(sd / math.sqrt(n), "standard error")
        if standard_error == 0:
            raise ValueError("Standard error underflowed the supported floating-point range.")
        t_stat = _finite_result(mean_difference / standard_error, "t statistic")
        if mean_difference and t_stat == 0:
            raise ValueError("t statistic underflowed the supported floating-point range.")
        df = n - 1
        p = _valid_probability(2.0 * stats.t.sf(abs(t_stat), df))
        critical = _finite_result(float(stats.t.ppf(0.975, df)), "t critical")
        half_width = _finite_result(critical * standard_error, "confidence interval half-width")
        ci = [
            _finite_result(mean_difference - half_width, "confidence interval lower"),
            _finite_result(mean_difference + half_width, "confidence interval upper"),
        ]
        calculated = {
            "mean_difference": mean_difference,
            "standard_error": standard_error,
            "t": t_stat,
            "df": float(df),
            "p_two_sided": p,
        }
        extra = {"confidence_interval_95": ci, "mu0": null_mean}
        if test == "one_sample_t":
            method = "Two-sided one-sample Student t-test (mean versus mu0)"
            assumptions = [
                "Observations are independent and sample SD uses n-1 denominator.",
                "Population is approximately normal or sample is sufficiently large.",
            ]
        else:
            method = "Two-sided paired t-test on provided within-pair differences"
            assumptions = [
                "Paired differences, not separate group means, are the supplied sample.",
                "Pairs are independent and differences are approximately normal or sample is sufficiently large.",
            ]
        extra["inputs"] = {key: {"mean": mean, "sd": sd, "n": n}}
    else:
        table = _table_2x2(spec)
        if test == "fisher_exact_2x2" and sum(map(sum, table)) > 1_000_000:
            raise ValueError("Fisher exact total count exceeds the supported limit of 1000000.")
        a, b = table[0]
        c, d = table[1]
        n = a + b + c + d
        e = [
            [(a+b)*(a+c)/n, (a+b)*(b+d)/n],
            [(c+d)*(a+c)/n, (c+d)*(b+d)/n],
        ]
        extra["inputs"] = {"table": table}
        extra["expected_counts"] = e
        if test == "chi_square_2x2":
            chi2 = _finite_result(float(sum(
                (table[i][j] - e[i][j]) ** 2 / e[i][j]
                for i in range(2) for j in range(2)
            )), "chi-square")
            p = _valid_probability(stats.chi2.sf(chi2, 1))
            calculated = {"chi_square": chi2, "df": 1.0, "p_value": p}
            method = "Pearson chi-square test of independence for a 2x2 table, without Yates correction"
            assumptions = [
                "Observations are independent; table entries are absolute event counts.",
                "Chi-square approximation relies on adequate expected cell counts.",
            ]
            if min(map(min, e)) < 5:
                warnings.append(
                    "At least one expected count is below 5; chi-square approximation may be unreliable. "
                    "Consider Fisher's exact test."
                )
        else:
            result = stats.fisher_exact(table, alternative="two-sided")
            p = _valid_probability(result.pvalue)
            calculated = {"p_two_sided": p}
            if math.isfinite(float(result.statistic)):
                calculated["odds_ratio"] = _finite_result(float(result.statistic), "odds_ratio")
            else:
                extra["odds_ratio"] = None
                warnings.append("Uncorrected sample odds ratio is infinite or undefined due to zero cells.")
            method = "Two-sided Fisher exact test for a 2x2 table (fixed margins)"
            assumptions = [
                "Observations are independent and counts are non-negative whole numbers.",
                "Two-sided definition follows SciPy's Fisher exact implementation.",
            ]
        extra["total_n"] = n

    checks, status = _settings(spec, calculated)
    return {
        "schema_version": "1.0", "test": test, "method": method, "status": status,
        "input_sha256": input_sha256,
        "calculated": {**calculated, **{k: v for k, v in extra.items() if k not in ("inputs",)}},
        "inputs": extra["inputs"],
        "reported_checks": checks, "warnings": warnings,
        "assumptions": assumptions,
        "limitations": [
            "Recalculation is conditional on supplied summary data; raw data, study design, data integrity and assumptions are not independently verified.",
            "A PASS means selected reported numbers agree within tolerance, not that the inference or choice of statistical method is valid.",
            "CI estimates are two-sided 95% t intervals on mean differences when available; Fisher's exact test does not calculate a confidence interval here.",
        ],
    }
