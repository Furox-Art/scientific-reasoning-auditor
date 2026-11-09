"""Measure what each rule contributes on a corpus with known-planted findings.

A rule that never fires and a rule that fires on everything look identical in a
test suite that only asserts "this finding appeared". This module scores rules
against a corpus whose expected findings are declared up front, so both kinds of
dead weight become visible:

* ``fn`` — the corpus plants the condition and the rule stayed silent;
* ``fp`` — the rule fired where nothing was planted;
* ``unexercised`` — nothing in the corpus can plant this rule at all.

The corpus here is synthetic. It measures whether a rule is wired and how
narrowly it fires; it says nothing about accuracy on real manuscripts, and every
report carries that sentence.
"""

from __future__ import annotations

import json
from pathlib import Path

from sra.audit import audit_file

SYNTHETIC_NOTE = (
    "Synthetic corpus: these numbers describe rule wiring and firing breadth, "
    "not accuracy on real manuscripts. Precision and recall on real papers require "
    "independent expert labels."
)


def _load_spec(spec_path: str | Path) -> tuple[Path, list[dict]]:
    path = Path(spec_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("Ablation spec must be an object with a cases list.")
    cases = payload["cases"]
    if not cases:
        raise ValueError("Ablation spec has no cases.")
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Every ablation case must be an object.")
        if not isinstance(case.get("document"), str) or not case["document"]:
            raise ValueError("Every ablation case needs a document path.")
        expected = case.get("expected")
        if not isinstance(expected, list) or any(not isinstance(item, str) for item in expected):
            raise ValueError("Every ablation case needs an expected list of check ids.")
    return path.parent, cases


def evaluate_rule_corpus(spec_path: str | Path, all_rules: list[str]) -> dict:
    """Score every rule in ``all_rules`` against the corpus in ``spec_path``."""
    root, cases = _load_spec(spec_path)
    per_rule = {
        rule: {"tp": 0, "fp": 0, "fn": 0, "cases_fired": 0} for rule in sorted(all_rules)
    }
    case_results: list[dict] = []

    for case in cases:
        document = root / case["document"]
        expected = set(case["expected"])
        observed = {finding.check_id for finding in audit_file(document).findings}
        unknown = expected - set(all_rules)
        if unknown:
            raise ValueError(f"{document.name}: expected rules that do not exist: {sorted(unknown)}")
        for rule in expected:
            per_rule[rule]["tp" if rule in observed else "fn"] += 1
        for rule in observed:
            if rule in per_rule:
                per_rule[rule]["cases_fired"] += 1
            if rule not in expected and rule in per_rule:
                per_rule[rule]["fp"] += 1
        case_results.append({
            "document": case["document"],
            "expected": sorted(expected),
            "observed": sorted(observed),
            "missing": sorted(expected - observed),
            "extra": sorted(observed - expected),
        })

    summary = {
        "rules": len(per_rule),
        "exercised": sum(1 for value in per_rule.values() if value["cases_fired"]),
        "with_false_positive": sorted(
            rule for rule, value in per_rule.items() if value["fp"]
        ),
        "never_fired": sorted(
            rule for rule, value in per_rule.items()
            if value["cases_fired"] == 0
        ),
        "missed_planted": sorted(
            rule for rule, value in per_rule.items() if value["fn"]
        ),
    }
    return {
        "kind": "rule_ablation_synthetic",
        "note": SYNTHETIC_NOTE,
        "cases": len(cases),
        "per_rule": per_rule,
        "summary": summary,
        "case_results": case_results,
    }
