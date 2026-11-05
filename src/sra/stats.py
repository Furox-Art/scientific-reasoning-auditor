import hashlib
import json
import math
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Any


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError(f"{field} must be a number.")
    try:
        number = float(value)
    except (ArithmeticError, ValueError) as exc:
        raise ValueError(f"{field} is outside the supported numeric range.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite and within the supported numeric range.")
    if isinstance(value, Decimal):
        if not value.is_zero() and number == 0.0:
            raise ValueError(
                f"{field} is too small to be represented as a non-zero floating-point value."
            )
        if Decimal(str(number)) != value:
            raise ValueError(
                f"{field} has more decimal precision than the supported floating-point representation."
            )
    elif isinstance(value, int) and not isinstance(value, bool) and int(number) != value:
        raise ValueError(
            f"{field} is not exactly representable in the supported floating-point representation."
        )
    return number


def _finite_result(value: float, field: str) -> float:
    """Reject overflowed or otherwise non-finite intermediate calculations."""
    if not math.isfinite(value):
        raise ValueError(
            f"{field} is outside the supported floating-point range; "
            "rescale the input values before verification."
        )
    return value


def _group(spec: dict, name: str) -> tuple[float, float, int]:
    item = spec.get(name)
    if not isinstance(item, dict):
        raise ValueError(f"{name} must be an object with mean, sd, and n.")
    mean = _finite_number(item.get("mean"), f"{name}.mean")
    sd = _finite_number(item.get("sd"), f"{name}.sd")
    n_value = item.get("n")
    if isinstance(n_value, bool) or not isinstance(n_value, int) or n_value < 2:
        raise ValueError(f"{name}.n must be an integer >= 2.")
    if sd < 0:
        raise ValueError(f"{name}.sd must be >= 0.")
    return mean, sd, n_value


def _display_precision_tolerance(value: Any) -> float:
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
        if not decimal_value.is_finite():
            raise ValueError("Reported-value precision must be finite.")
        exponent = decimal_value.as_tuple().exponent
        if not isinstance(exponent, int):
            raise ValueError("Reported-value precision has an invalid decimal exponent.")
        # Construct half of the last displayed decimal unit without context-based
        # Decimal arithmetic (which can raise InvalidOperation for extreme exponents).
        tolerance_decimal = Decimal((0, (5,), exponent - 1))
    except (DecimalException, ArithmeticError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("Reported-value precision exceeds the supported numeric range.") from exc
    return _finite_number(tolerance_decimal, "Reported-value precision tolerance")


def _json_safe_report_value(value: Any, field: str) -> Any:
    """Normalize JSON-origin values so the verifier never returns NaN/Infinity."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{field} must be finite.")
        try:
            return _finite_number(value, field)
        except ValueError:
            # This value is explicitly NOT_VERIFIED, so preserve exact Decimal
            # content as text instead of blocking unrelated statistical checks
            # or silently rounding it to binary64.
            return str(value)
    if isinstance(value, float):
        return _finite_number(value, field)
    if isinstance(value, dict):
        return {key: _json_safe_report_value(item, f"{field}.{key}") for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_report_value(item, f"{field}[{index}]") for index, item in enumerate(value)]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    raise ValueError(f"{field} contains a value that is not JSON-compatible.")


def _compare_reported(
    calculated: dict[str, float],
    reported: dict[str, Any],
    tolerances: dict[str, float],
) -> list[dict]:
    checks = []
    for field, observed in reported.items():
        if field not in calculated:
            checks.append({
                "field": field,
                "status": "NOT_VERIFIED",
                "message": "No independent calculation is available for this reported field.",
                "reported": _json_safe_report_value(observed, f"reported.{field}"),
                "calculated": None,
            })
            continue
        expected = _finite_number(observed, f"reported.{field}")
        if field == "p_two_sided" and not 0 < expected <= 1:
            raise ValueError("reported.p_two_sided must be > 0 and <= 1; do not encode p=0.")
        actual = calculated[field]
        tolerance = tolerances.get(field, tolerances.get("default"))
        if tolerance is None:
            tolerance = _display_precision_tolerance(observed)
        difference = _finite_result(abs(actual - expected), f"reported.{field} difference")
        passed = difference <= tolerance
        checks.append({
            "field": field,
            "status": "PASS" if passed else "FAIL",
            "reported": expected,
            "calculated": actual,
            "absolute_difference": difference,
            "absolute_tolerance": tolerance,
            "message": (
                "Reported value matches the independent calculation within tolerance."
                if passed else
                "Reported value differs from the independent calculation beyond tolerance."
            ),
        })
    return checks


def _hedges_correction(degrees: int) -> float:
    """Return Hedges' small-sample correction without large-df cancellation.

    With z=(df-1)/2, J(df)=Gamma(z+1/2)/(sqrt(z+1/2)*Gamma(z)).
    For large z, use the log-gamma-ratio asymptotic expansion rather than
    subtracting two O(z log z) log-gamma values. The omitted next term is
    O(z**-7), negligible beyond the selected threshold.
    """
    if degrees < 2:
        raise ValueError("Hedges' g requires pooled degrees of freedom >= 2.")
    z = (degrees - 1) / 2
    try:
        if z >= 50.0:
            inverse_z = 1.0 / z
            log_correction = (
                -0.5 * math.log1p(0.5 * inverse_z)
                - inverse_z / 8.0
                + inverse_z**3 / 192.0
                - inverse_z**5 / 640.0
            )
        else:
            log_correction = (
                math.lgamma(z + 0.5)
                - math.lgamma(z)
                - 0.5 * math.log(z + 0.5)
            )
        correction = math.exp(log_correction)
    except (OverflowError, ValueError) as exc:
        raise ValueError("Hedges' g correction exceeded the supported numeric range.") from exc
    correction = _finite_result(correction, "Hedges' g correction")
    if not 0.0 < correction <= 1.0:
        raise ValueError("Hedges' g correction must be in the interval (0, 1].")
    return correction


def verify_welch_t_test(spec: dict[str, Any], input_sha256: str | None = None) -> dict:
    """Recalculate an independent two-group Welch t-test from summary statistics.

    Expected input:
      group_a/group_b: mean, sample standard deviation (sd), sample size (n)
      reported (optional): mean_difference, t, df, p_two_sided
      tolerances (optional): per-field absolute tolerances or default. Without
      an override, tolerance is half the last displayed decimal place.
    """
    if spec.get("test") != "welch_t":
        raise ValueError("Only test='welch_t' is supported by this verifier.")

    mean_a, sd_a, n_a = _group(spec, "group_a")
    mean_b, sd_b, n_b = _group(spec, "group_b")
    try:
        root_n_a = _finite_result(math.sqrt(n_a), "group_a square-root sample size")
        root_n_b = _finite_result(math.sqrt(n_b), "group_b square-root sample size")
        contribution_a = _finite_result(sd_a / root_n_a, "group_a standard-error contribution")
        contribution_b = _finite_result(sd_b / root_n_b, "group_b standard-error contribution")
        if sd_a > 0 and contribution_a == 0.0:
            raise ValueError("group_a standard-error contribution underflowed the supported floating-point range.")
        if sd_b > 0 and contribution_b == 0.0:
            raise ValueError("group_b standard-error contribution underflowed the supported floating-point range.")
        standard_error = _finite_result(
            math.hypot(contribution_a, contribution_b), "Welch standard error"
        )
        if standard_error == 0:
            raise ValueError("Welch t is undefined when both groups have zero standard error.")

        mean_difference = _finite_result(mean_a - mean_b, "mean difference")
        t_statistic = _finite_result(mean_difference / standard_error, "Welch t statistic")
        if mean_difference != 0.0 and t_statistic == 0.0:
            raise ValueError("Welch t statistic underflowed the supported floating-point range.")

        # The variance weights are computed from standard-error ratios. This avoids
        # squaring large/small raw variances and is algebraically equivalent to
        # the Welch-Satterthwaite formula.
        ratio_a = contribution_a / standard_error
        ratio_b = contribution_b / standard_error
        weight_a = ratio_a * ratio_a
        weight_b = ratio_b * ratio_b
        denominator_a = weight_a * weight_a / (n_a - 1)
        denominator_b = weight_b * weight_b / (n_b - 1)
        denominator = _finite_result(
            denominator_a + denominator_b, "Welch-Satterthwaite denominator"
        )
        if denominator == 0:
            raise ValueError(
                "Welch-Satterthwaite degrees of freedom are outside the supported "
                "floating-point range."
            )
        degrees_freedom = _finite_result(
            1.0 / denominator, "Welch-Satterthwaite degrees of freedom"
        )
        if degrees_freedom <= 0:
            raise ValueError("Welch-Satterthwaite degrees of freedom must be positive.")

        # Compute pooled SD directly with normalized sample-size weights. Working
        # with SD rather than variance avoids squaring values near float limits.
        max_sd = max(sd_a, sd_b)
        pooled_sd = 0.0
        if max_sd > 0:
            max_group_df = max(n_a - 1, n_b - 1)
            root_count_scale = _finite_result(
                math.sqrt(max_group_df), "pooled-variance sample-size scale"
            )
            count_root_a = math.sqrt(n_a - 1) / root_count_scale
            count_root_b = math.sqrt(n_b - 1) / root_count_scale
            count_norm = math.hypot(count_root_a, count_root_b)
            scaled_sd_a = sd_a / max_sd
            scaled_sd_b = sd_b / max_sd
            pooled_sd_factor = math.hypot(
                count_root_a * scaled_sd_a,
                count_root_b * scaled_sd_b,
            ) / count_norm
            pooled_sd = _finite_result(max_sd * pooled_sd_factor, "pooled standard deviation")
            if pooled_sd == 0.0:
                raise ValueError(
                    "Positive pooled variance underflowed the supported floating-point range."
                )
    except OverflowError as exc:
        raise ValueError(
            "Welch calculation exceeded the supported floating-point range; "
            "rescale the input values before verification."
        ) from exc

    tolerances_raw = spec.get("tolerances", {})
    if not isinstance(tolerances_raw, dict):
        raise ValueError("tolerances must be an object.")
    tolerances = {
        key: _finite_number(value, f"tolerances.{key}")
        for key, value in tolerances_raw.items()
    }
    if any(value < 0 for value in tolerances.values()):
        raise ValueError("Tolerances must be non-negative.")

    reported = spec.get("reported", {})
    if not isinstance(reported, dict):
        raise ValueError("reported must be an object.")
    calculated_fields = {"mean_difference", "standard_error", "t", "df", "p_two_sided"}
    for field, observed in reported.items():
        if field in calculated_fields:
            expected = _finite_number(observed, f"reported.{field}")
            if field == "p_two_sided" and not 0 < expected <= 1:
                raise ValueError("reported.p_two_sided must be > 0 and <= 1; do not encode p=0.")
            if field not in tolerances and "default" not in tolerances:
                _display_precision_tolerance(observed)
        else:
            _json_safe_report_value(observed, f"reported.{field}")

    try:
        from scipy import stats
    except ImportError as exc:
        raise RuntimeError(
            "Welch p-value and confidence interval require SciPy. Install with: "
            "pip install -e '.[statistics]'"
        ) from exc

    p_value = _finite_result(float(2.0 * stats.t.sf(abs(t_statistic), degrees_freedom)), "Welch p-value")
    if p_value == 0.0:
        raise ValueError(
            "The Welch p-value underflowed the supported floating-point range; "
            "a zero p-value would be misleading. Use a higher-precision method."
        )
    critical = _finite_result(float(stats.t.ppf(0.975, degrees_freedom)), "95% t critical value")
    ci_low = _finite_result(mean_difference - critical * standard_error, "95% confidence interval lower bound")
    ci_high = _finite_result(mean_difference + critical * standard_error, "95% confidence interval upper bound")

    cohen_d = _finite_result(mean_difference / pooled_sd, "pooled Cohen's d") if pooled_sd > 0 else None
    if cohen_d == 0.0 and mean_difference != 0.0 and pooled_sd > 0:
        raise ValueError("Pooled Cohen's d underflowed the supported floating-point range.")
    hedges_g = None
    if cohen_d is not None:
        degrees = n_a + n_b - 2
        correction = _hedges_correction(degrees)
        hedges_g = _finite_result(cohen_d * correction, "Hedges' g")
        if cohen_d != 0.0 and hedges_g == 0.0:
            raise ValueError("Hedges' g underflowed the supported floating-point range.")

    calculated = {
        "mean_difference": mean_difference,
        "standard_error": standard_error,
        "t": t_statistic,
        "df": degrees_freedom,
        "p_two_sided": p_value,
    }
    checks = _compare_reported(calculated, reported, tolerances)

    if any(check["status"] == "FAIL" for check in checks):
        overall_status = "FAIL"
    elif not checks or any(check["status"] == "NOT_VERIFIED" for check in checks):
        overall_status = "PARTIAL"
    else:
        overall_status = "PASS"

    return {
        "schema_version": "1.0",
        "test": "welch_t",
        "method": "Welch two-sample t-test (independent groups, unequal variances)",
        "status": overall_status,
        "input_sha256": input_sha256,
        "inputs": {
            "group_a": {"mean": mean_a, "sd": sd_a, "n": n_a},
            "group_b": {"mean": mean_b, "sd": sd_b, "n": n_b},
        },
        "calculated": {
            **calculated,
            "confidence_interval_95": [ci_low, ci_high],
            "cohen_d_pooled": cohen_d,
            "hedges_g": hedges_g,
        },
        "reported_checks": checks,
        "assumptions": [
            "The two groups are independent.",
            "Summary means and sample standard deviations are correctly reported.",
            "The observations are sufficiently well behaved for the Welch t-test.",
        ],
        "limitations": [
            "This verifies arithmetic conditional on supplied summary statistics; it does not validate raw data, sampling, measurement, study design, or the choice of statistical test.",
            "A PASS means reported values agree within the configured tolerances, not that the scientific conclusion is true.",
            "Rounded reported values may require tolerances appropriate to the manuscript's displayed precision.",
        ],
    }


def verify_stats_file(path: str | Path) -> dict:
    file_path = Path(path).expanduser().resolve()
    raw = file_path.read_bytes()
    def reject_nonstandard_constant(token: str) -> None:
        raise ValueError(f"Non-standard JSON numeric constant {token!r} is not permitted.")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        # A duplicate key makes a reported scientific input ambiguous across
        # JSON parsers (first-wins vs last-wins). Reject it at every depth.
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON key {key!r} is not permitted.")
            result[key] = value
        return result

    spec = json.loads(
        raw.decode("utf-8-sig"),
        parse_float=Decimal,
        parse_constant=reject_nonstandard_constant,
        object_pairs_hook=reject_duplicate_keys,
    )
    if not isinstance(spec, dict):
        raise ValueError("Statistics input must be a JSON object.")
    fingerprint = hashlib.sha256(raw).hexdigest()
    if spec.get("test") == "welch_t":
        return verify_welch_t_test(spec, fingerprint)
    from sra.stats_extended import verify_extended_stats
    return verify_extended_stats(spec, fingerprint)
