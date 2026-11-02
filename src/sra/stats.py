import hashlib
import json
import math
from pathlib import Path
from typing import Any


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite.")
    return number


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
                "reported": observed,
                "calculated": None,
            })
            continue
        expected = _finite_number(observed, f"reported.{field}")
        actual = calculated[field]
        tolerance = tolerances.get(field, tolerances.get("default", 0.02))
        difference = abs(actual - expected)
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


def verify_welch_t_test(spec: dict[str, Any], input_sha256: str | None = None) -> dict:
    """Recalculate an independent two-group Welch t-test from summary statistics.

    Expected input:
      group_a/group_b: mean, sample standard deviation (sd), sample size (n)
      reported (optional): mean_difference, t, df, p_two_sided
      tolerances (optional): per-field absolute tolerances or default
    """
    if spec.get("test") != "welch_t":
        raise ValueError("Only test='welch_t' is supported by this verifier.")

    mean_a, sd_a, n_a = _group(spec, "group_a")
    mean_b, sd_b, n_b = _group(spec, "group_b")
    variance_a = sd_a**2 / n_a
    variance_b = sd_b**2 / n_b
    standard_error = math.sqrt(variance_a + variance_b)
    if standard_error == 0:
        raise ValueError("Welch t is undefined when both groups have zero standard error.")

    t_statistic = (mean_a - mean_b) / standard_error
    denominator = (variance_a**2 / (n_a - 1)) + (variance_b**2 / (n_b - 1))
    if denominator == 0:
        raise ValueError("Welch-Satterthwaite degrees of freedom are undefined.")
    degrees_freedom = (variance_a + variance_b) ** 2 / denominator

    try:
        from scipy import stats
    except ImportError as exc:
        raise RuntimeError(
            "Welch p-value and confidence interval require SciPy. Install with: "
            "pip install -e '.[statistics]'"
        ) from exc

    p_value = float(2.0 * stats.t.sf(abs(t_statistic), degrees_freedom))
    critical = float(stats.t.ppf(0.975, degrees_freedom))
    ci_low = (mean_a - mean_b) - critical * standard_error
    ci_high = (mean_a - mean_b) + critical * standard_error

    pooled_variance = (
        ((n_a - 1) * sd_a**2) + ((n_b - 1) * sd_b**2)
    ) / (n_a + n_b - 2)
    cohen_d = (mean_a - mean_b) / math.sqrt(pooled_variance) if pooled_variance > 0 else None
    hedges_g = None
    if cohen_d is not None:
        degrees = n_a + n_b - 2
        correction = math.exp(
            math.lgamma(degrees / 2)
            - 0.5 * math.log(degrees / 2)
            - math.lgamma((degrees - 1) / 2)
        )
        hedges_g = cohen_d * correction

    calculated = {
        "mean_difference": mean_a - mean_b,
        "standard_error": standard_error,
        "t": t_statistic,
        "df": degrees_freedom,
        "p_two_sided": p_value,
    }
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
    spec = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(spec, dict):
        raise ValueError("Statistics input must be a JSON object.")
    return verify_welch_t_test(spec, hashlib.sha256(raw).hexdigest())
