"""Aggregate validated (externally supplied) domain assessments across papers.

No expert assessments are generated here. A syntactically accepted label
file is not evidence that its claimed human reviewers are real/qualified.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from sra.validation import _wilson


def aggregate_domain_reports(paths: list[str | Path]) -> dict:
    if not isinstance(paths, list) or not 2 <= len(paths) <= 10000:
        raise ValueError("Provide between 2 and 10000 validated domain report paths.")
    seen_sources: set[str] = set()
    domain = None
    rule_set = None
    totals = Counter()
    by_rule: dict[str, Counter[str]] = {}
    agreement_total = 0
    assessor_pairs = 0
    sources = []
    for path in paths:
        raw = Path(path).read_bytes()
        if len(raw) > 2_000_000:
            raise ValueError("Each validated domain report must be at most 2 MB.")
        report = json.loads(raw)
        if (not isinstance(report, dict)
                or report.get("status") != "STRUCTURALLY_ACCEPTED_FOR_EXPERT_OVERSIGHT"
                or report.get("blinded_template") is not True):
            raise ValueError("Expected a structurally accepted blinded domain-adjudication report.")
        name = report.get("discipline")
        fingerprint = report.get("ruleset_sha256")
        source_sha = report.get("source_sha256")
        if (not isinstance(name, str) or not name
                or not isinstance(fingerprint, str) or len(fingerprint) != 64
                or not isinstance(source_sha, str) or len(source_sha) != 64):
            raise ValueError("Missing report discipline, source or ruleset hash.")
        if domain is None:
            domain, rule_set = name, fingerprint
        if (name, fingerprint) != (domain, rule_set):
            raise ValueError("Reports must use identical discipline and exact ruleset SHA-256.")
        if source_sha in seen_sources:
            raise ValueError("Duplicate manuscript hash found across input reports.")
        seen_sources.add(source_sha)
        votes = report.get("reviewer_agreement")
        comparison = report.get("comparison_against_adjudicated_verdicts")
        if not isinstance(votes, dict) or not isinstance(comparison, dict):
            raise ValueError("Missing reviewer agreement or candidate comparison data.")
        n = votes.get("rule_count")
        disagreements = votes.get("disagreements")
        rows = comparison.get("per_rule")
        if (type(n) is not int or n <= 0 or type(disagreements) is not int
                or not 0 <= disagreements <= n or not isinstance(rows, list)
                or len(rows) != n):
            raise ValueError("Malformed per-rule or reviewer agreement data.")
        ids = set()
        local = Counter()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Malformed domain per-rule row.")
            key, outcome = row.get("rule_id"), row.get("outcome")
            if (not isinstance(key, str) or not key or key in ids
                    or outcome not in ("tp", "fp", "fn", "tn",
                                       "excluded_uncertain", "excluded_not_applicable")):
                raise ValueError("Repeated/invalid rule IDs or outcome values.")
            ids.add(key)
            local[outcome] += 1
            by_rule.setdefault(key, Counter())[outcome] += 1
        if dict(local) != {
            key: count for key, count in comparison.get("confusion_matrix", {}).items()
            if count != 0
        }:
            raise ValueError("Report confusion matrix conflicts with per-rule outcomes.")
        totals.update(local)
        agreement_total += n - disagreements
        assessor_pairs += n
        sources.append({
            "source_sha256": source_sha,
            "input_report_sha256": hashlib.sha256(raw).hexdigest(),
            "assessed_rules": n,
        })

    def rate(a: int, b: int) -> dict:
        return {"value": a/b if b else None, "wilson_95": _wilson(a, b), "denominator": b}

    tp, fp, fn, tn = (totals.get(key, 0) for key in ("tp", "fp", "fn", "tn"))
    return {
        "schema_version": "1.0",
        "kind": "cohort_aggregated_external_domain_adjudications",
        "discipline": domain,
        "ruleset_sha256": rule_set,
        "manuscripts": len(seen_sources),
        "adjudicated_rule_units": sum(totals.values()),
        "confusion_matrix": {k: totals.get(k, 0) for k in (
            "tp", "fp", "fn", "tn", "excluded_uncertain", "excluded_not_applicable"
        )},
        "conditional_candidate_metrics": {
            "precision": rate(tp, tp+fp),
            "recall": rate(tp, tp+fn),
            "specificity": rate(tn, tn+fp),
        },
        "reviewer_agreement": {
            "pooled_raw_agreement": rate(agreement_total, assessor_pairs),
            "note": "Pooled raw agreement, not a pooled Cohen kappa.",
        },
        "by_rule_outcomes": {key: dict(value) for key, value in sorted(by_rule.items())},
        "source_provenance": sources,
        "limitations": [
            "Expert identities, competence, independence, and blinding are not verified by software.",
            "Cohort selection and document-level clustering can invalidate naive confidence interval generalization.",
            "These metrics measure automated evidence-candidate retrieval against declared manual verdicts, NOT scientific truth or full reporting guideline compliance.",
            "Reports must originate from genuine independent expert review. Synthetic or test-fixture labels are not valid evidence.",
        ],
    }
