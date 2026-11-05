"""Synthetic regression benchmark for planted manuscript-review signals.

IMPORTANT: This measures rule behavior on artificial fixtures, NOT accuracy on
real scientific papers. Real-world precision/recall require expert labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sra.checks import build_findings
from sra.document import parse_document_text


@dataclass(frozen=True)
class Case:
    name: str
    target: str
    expected: bool
    text: str


CASES = (
    Case("observational-causal", "reasoning.causal_claim_observational_design", True,
         "# Methods\nThis was an observational cohort study.\n# Results\nExposure was associated with disease.\n# Conclusion\nExposure caused disease."),
    Case("negated-causality", "reasoning.causal_claim_observational_design", False,
         "# Methods\nThis was an observational cohort study.\n# Results\nExposure was associated with disease.\n# Conclusion\nExposure did not cause disease."),
    Case("randomized-only", "reasoning.causal_claim_observational_design", False,
         "# Methods\nThis study was randomized.\n# Results\nThe treatment increased outcomes.\n# Conclusion\nThe treatment caused the outcomes."),
    Case("no-random-assignment", "reasoning.causal_claim_observational_design", True,
         "# Methods\nThis was an observational cohort study. No random assignment to treatment groups.\n# Results\nExposure was associated with the outcome.\n# Conclusion\nExposure caused the outcome."),
    Case("mixed-design", "reasoning.mixed_design_causal_review", True,
         "# Methods\nThis study was randomized. We also used an observational registry.\n# Results\nTreatment increased measured outcomes.\n# Conclusion\nTreatment caused measured outcomes."),
    Case("opposite-direction", "reasoning.directional_contradiction", True,
         "# Methods\nProtocol applied.\n# Results\nTreatment increased the measured score.\n# Conclusion\nTreatment decreased the measured score."),
    Case("same-direction", "reasoning.directional_contradiction", False,
         "# Methods\nProtocol applied.\n# Results\nTreatment increased the measured score.\n# Conclusion\nTreatment increased the measured score."),
    Case("multi-endpoint-reversal", "reasoning.directional_contradiction", True,
         "# Methods\nProtocol applied.\n# Results\nTreatment increased glucose but decreased cholesterol.\n# Conclusion\nTreatment decreased glucose but increased cholesterol."),
    Case("unrelated-endpoints", "reasoning.directional_contradiction", False,
         "# Methods\nProtocol applied.\n# Results\nTreatment increased glucose.\n# Conclusion\nTreatment decreased cholesterol."),
    Case("missing-results", "structure.results_missing", True,
         "# Methods\nAn observational protocol was used.\n# Conclusion\nNo result was documented."),
)


def benchmark() -> dict:
    records = [asdict(case) for case in CASES]
    digest = hashlib.sha256(json.dumps(
        records, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    results = []
    tp = fp = tn = fn = 0
    for case in CASES:
        document = parse_document_text(
            case.text,
            sha256=hashlib.sha256(case.text.encode("utf-8")).hexdigest(),
        )
        findings, _, _ = build_findings(document)
        observed = case.target in {finding.check_id for finding in findings}
        if case.expected and observed:
            tp += 1
        elif case.expected:
            fn += 1
        elif observed:
            fp += 1
        else:
            tn += 1
        results.append({
            "name": case.name, "target": case.target,
            "expected": case.expected, "observed": observed,
            "matched": case.expected == observed,
        })
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    return {
        "scope": "synthetic-rule-regression-only",
        "warning": "Synthetic fixture metrics do not estimate accuracy on published manuscripts.",
        "case_count": len(CASES),
        "fixtures_passed": tp + tn,
        "fixtures_failed": fn + fp,
        "sampling_uncertainty": "Not applicable: fixtures are purposively constructed, not a random manuscript sample.",
        "fixture_sha256": digest,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "precision": precision,
        "recall": recall,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--require-perfect-on-synthetic", action="store_true")
    args = parser.parse_args()
    result = benchmark()
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        from pathlib import Path
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    if args.require_perfect_on_synthetic and (result["confusion"]["fn"] or result["confusion"]["fp"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
