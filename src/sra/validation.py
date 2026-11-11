"""Evaluate *separately obtained* blinded expert labels against frozen PMC outputs.

A benchmark report without reviewed labels cannot yield performance metrics.
Reviewer identity and independence are user-supplied assertions, not verified.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path


def _wilson(successes: int, trials: int) -> list[float] | None:
    if trials == 0:
        return None
    z = 1.959963984540054
    p = successes / trials
    denominator = 1 + z*z/trials
    center = (p + z*z/(2*trials))/denominator
    margin = z*math.sqrt(p*(1-p)/trials + z*z/(4*trials*trials))/denominator
    return [max(0.0, center-margin), min(1.0, center+margin)]


def _metrics(counts: dict[str, int]) -> dict:
    tp, fp, fn, tn = (counts[k] for k in ("tp", "fp", "fn", "tn"))
    def ratio(n: int, d: int) -> float | None:
        return n/d if d else None
    return {
        **counts,
        "precision": ratio(tp, tp+fp),
        "recall": ratio(tp, tp+fn),
        "specificity": ratio(tn, tn+fp),
        "precision_ci95_wilson": _wilson(tp, tp+fp),
        "recall_ci95_wilson": _wilson(tp, tp+fn),
        "specificity_ci95_wilson": _wilson(tn, tn+fp),
    }


def evaluate_blinded_labels(benchmark_path: str | Path, labels_path: str | Path) -> dict:
    benchmark_bytes = Path(benchmark_path).read_bytes()
    labels_bytes = Path(labels_path).read_bytes()
    benchmark = json.loads(benchmark_bytes)
    labels = json.loads(labels_bytes)
    if not isinstance(benchmark, dict) or not isinstance(labels, dict):
        raise ValueError("Benchmark and labels must be JSON objects.")
    if benchmark.get("kind") != "unlabeled_real_paper_smoke_test":
        raise ValueError("Expected an SRA PMC smoke-test report.")
    paper_entries = benchmark.get("paper_results", [])
    if not isinstance(paper_entries, list) or any(not isinstance(item, dict) for item in paper_entries):
        raise ValueError("Benchmark paper_results must be a list of objects.")
    papers = {item["pmcid"]: item for item in paper_entries if item.get("status") == "PROCESSED"}
    if sum(item.get("status") == "PROCESSED" for item in paper_entries) != len(papers):
        raise ValueError("Benchmark has duplicate processed PMCIDs.")
    if not papers:
        raise ValueError("No processed papers in benchmark.")
    codes = labels.get("finding_codes")
    cases = labels.get("cases")
    if (not isinstance(codes, list) or not codes
            or any(not isinstance(item, str) or not item for item in codes)
            or len(codes) != len(set(codes))):
        raise ValueError("finding_codes must be a nonempty list of unique codes.")
    if not isinstance(cases, list):
        raise ValueError("cases must be a list.")
    expected = {(pmcid, code) for pmcid in papers for code in codes}
    observed = set()
    counts = {code: {"tp": 0, "fp": 0, "fn": 0, "tn": 0} for code in codes}
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Every case must be an object.")
        key = (case.get("pmcid"), case.get("code"))
        if key not in expected or key in observed:
            raise ValueError("Unknown or repeated (PMCID, code) annotation unit.")
        observed.add(key)
        paper = papers[key[0]]
        if not isinstance(paper.get("writing_finding_codes"), list):
            raise ValueError("Benchmark lacks frozen writing_finding_codes; rerun current benchmark.")
        label_hash = case.get("source_sha256")
        paper_hash = paper.get("response_sha256")
        if (not isinstance(label_hash, str) or re.fullmatch(r"[0-9a-f]{64}", label_hash) is None
                or not isinstance(paper_hash, str) or re.fullmatch(r"[0-9a-f]{64}", paper_hash) is None):
            raise ValueError("Expert label and benchmark require valid source SHA-256 hashes.")
        if label_hash != paper_hash:
            raise ValueError("Expert label source hash differs from the retrieved paper source.")
        if type(case.get("expert_label")) is not bool:
            raise ValueError("expert_label must be boolean.")
        reviewers = case.get("reviewer_ids")
        if (not isinstance(reviewers, list) or len(reviewers) < 2
                or any(not isinstance(x, str) or not x.strip() for x in reviewers)
                or len(set(reviewers)) < 2 or case.get("adjudicated") is not True):
            raise ValueError("Every case requires two declared distinct reviewers and adjudication.")
        pred = key[1] in paper["writing_finding_codes"]
        truth = case["expert_label"]
        category = "tp" if (pred and truth) else "fp" if pred else "fn" if truth else "tn"
        counts[key[1]][category] += 1
    if observed != expected:
        raise ValueError(
            f"Annotation coverage incomplete: {len(observed)}/{len(expected)} units. "
            "Label all negative and positive paper/code combinations to avoid selection bias."
        )
    combined = {name: sum(c[name] for c in counts.values())
                for name in ("tp", "fp", "fn", "tn")}
    return {
        "kind": "conditional_expert_label_comparison",
        "source_benchmark_sha256": hashlib.sha256(benchmark_bytes).hexdigest(),
        "expert_labels_sha256": hashlib.sha256(labels_bytes).hexdigest(),
        "paper_count": len(papers),
        "labelled_units": len(cases),
        "metrics_by_finding_code": {key: _metrics(value) for key, value in counts.items()},
        "micro_average": _metrics(combined),
        "limitations": [
            "Reviewers and independence are declared in the label file, not verified by software.",
            "Exact document-level finding-code labels do not validate claim-level semantic correctness.",
            "Wilson intervals assume an appropriate sampling design; selection bias and paper clustering are not accounted for.",
            "Results apply only to the given labelled corpus, guidelines and predeclared outcome codes.",
        ],
    }
