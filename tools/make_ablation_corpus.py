"""Write the synthetic ablation corpus and its expected-findings spec.

Each case plants one condition and keeps everything else intact, so a rule that
stays silent is visible as a miss rather than hidden behind a noisy neighbour.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "benchmarks" / "rule_ablation"

TAIL = "# Limitations\nThe sample was small.\n# References\n1. Example et al. 2020.\n"

CASES = {
    "clean.md": (
        "# Methods\nWe randomized 40 participants and measured the endpoint.\n"
        "# Results\nThe treated group increased the endpoint by 2.1 points "
        "(95% CI 0.4 to 3.8, p = 0.02).\n"
        "# Conclusion\nThe intervention increased the endpoint.\n" + TAIL,
        [],
    ),
    "structure_missing.md": (
        "# Results\nScores rose.\n# Conclusion\nScores rose.\n",
        [
            "structure.methods_missing",
            "structure.limitations_missing",
            "structure.references_missing",
        ],
    ),
    "missing_results.md": (
        "# Methods\nWe measured ten samples.\n# Conclusion\nThe samples differ.\n" + TAIL,
        ["structure.results_missing"],
    ),
    "missing_conclusion.md": (
        "# Methods\nWe measured ten samples.\n# Results\nThe samples differ.\n" + TAIL,
        ["structure.conclusion_missing"],
    ),
    "absolute_claim.md": (
        "# Methods\nWe measured ten samples.\n"
        "# Results\nThe treated group increased.\n"
        "# Conclusion\nThis proves conclusively that the treatment works.\n" + TAIL,
        ["language.absolute_claim"],
    ),
    "observational_causal.md": (
        "# Methods\nThis was a retrospective cohort study of hospital records.\n"
        "# Results\nExposed patients increased more.\n"
        "# Conclusion\nThe exposure caused the improvement.\n" + TAIL,
        ["reasoning.causal_claim_observational_design"],
    ),
    "association_and_causal.md": (
        "# Methods\nWe analyzed a cohort of 200 records.\n"
        "# Results\nThe exposed group recorded a higher score.\n"
        "# Conclusion\nThe exposure was associated with a higher score and causes it.\n"
        + TAIL,
        [
            "reasoning.association_and_causal_claims",
            "reasoning.correlation_causation_review",
        ],
    ),
    "mixed_design.md": (
        "# Methods\nWe used a randomized design for the first aim and an observational "
        "cohort for the second.\n"
        "# Results\nBoth samples increased.\n"
        "# Conclusion\nThe intervention caused the improvement.\n" + TAIL,
        ["reasoning.mixed_design_causal_review"],
    ),
    "directional.md": (
        "# Methods\nWe compared two cohorts on one endpoint.\n"
        "# Results\nThe treated cohort increased the endpoint value.\n"
        "# Conclusion\nThe treated cohort decreased the endpoint value.\n" + TAIL,
        ["reasoning.directional_contradiction"],
    ),
    "conclusion_without_evidence.md": (
        "# Methods\nWe surveyed participants.\n"
        "# Results\nParticipants reported satisfaction.\n"
        "# Conclusion\nUltrasonic cavitation increased membrane disruption.\n" + TAIL,
        ["reasoning.conclusion_without_lexical_candidate"],
    ),
    "multiplicity.md": (
        "# Methods\nFour groups were compared.\n"
        "# Results\nGroup A increased (p = 0.01). Group B increased (p = 0.03). "
        "Group C increased (p = 0.049).\n"
        "# Conclusion\nThe groups increased differently.\n" + TAIL,
        ["statistics.multiplicity_unaddressed"],
    ),
    "design_mismatch.md": (
        "# Methods\nEach participant was measured before and after the intervention: a "
        "paired design.\n"
        "# Results\nScores increased, independent-samples t-test p = 0.02.\n"
        "# Conclusion\nThe intervention increased scores.\n" + TAIL,
        ["statistics.design_test_mismatch"],
    ),
    "impossible_values.md": (
        "# Methods\nWe compared three groups with t-tests.\n"
        "# Results\nThe treated arm reported SD = -1.2 and n = 0 (p = 0.000).\n"
        "# Conclusion\nThe effect increased.\n" + TAIL,
        [
            "statistics.impossible_p_value",
            "statistics.impossible_dispersion",
            "statistics.group_count_test_mismatch",
        ],
    ),
    "interval_conflict.md": (
        "# Methods\nOne model was fitted.\n"
        "# Results\nThe effect was 1.2 (95% CI -0.5 to 2.0, p = 0.002). "
        "Mean score was 4.1 (95% CI 2.0 to 3.0).\n"
        "# Conclusion\nThe treatment increased the outcome.\n" + TAIL,
        [
            "statistics.confidence_interval_p_conflict",
            "statistics.mean_outside_confidence_interval",
        ],
    ),
    "table_values.md": (
        "# Methods\nWe measured four samples.\n"
        "# Results\n"
        "Group             n            mean            SD               p\n"
        "A                 12           4.1             3.2              0.03\n"
        "C                 10           -0.4            -1.2             0.000\n"
        "# Conclusion\nThe groups increased.\n" + TAIL,
        ["statistics.impossible_p_value", "statistics.impossible_dispersion"],
    ),
    "rate_ratio_repeat.md": (
        "# Methods\nRates were compared across two periods.\n"
        "# Results\n"
        "rate ratio: 1.8; 95% CI 1.2-2.6; p = 0.01\n"
        "rate ratio: 1.8; 95% CI 0.9-3.4; p = 0.01\n"
        "# Conclusion\nThe rate increased.\n" + TAIL,
        ["statistics.repeated_rate_ratio_ci_conflict"],
    ),
}


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    for stale in ROOT.glob("*.md"):
        stale.unlink()
    cases = []
    for name, (text, expected) in CASES.items():
        (ROOT / name).write_text(text, encoding="utf-8")
        cases.append({"document": name, "expected": expected})
    (ROOT / "cases.json").write_text(
        json.dumps({"kind": "synthetic_rule_ablation_corpus", "cases": cases}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(cases)} cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
