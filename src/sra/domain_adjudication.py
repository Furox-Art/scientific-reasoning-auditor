"""Source-hash-bound templates for genuine external domain-expert assessments.

This module verifies completeness and source quotation provenance only.
It cannot certify reviewer qualifications, independence or scientific accuracy.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from typing import Any

from sra.document import ParsedDocument
from sra.domain_evidence import review_domain

VERDICTS = (
    "adequately_reported",
    "partially_reported",
    "not_reported",
    "not_applicable",
    "uncertain",
)


def _contract_fingerprint(review: dict[str, Any]) -> str:
    payload = {
        "discipline": review["discipline"],
        "source_sha256": review["source_sha256"],
        "ruleset_sha256": review["ruleset_sha256"],
        "rule_ids": [item["rule_id"] for item in review["items"]],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()


def make_domain_template(document: ParsedDocument, discipline: str) -> dict:
    review = review_domain(document, discipline)
    return {
        "schema_version": "1.0",
        "kind": "manual_domain_expert_assessment_template",
        "source_sha256": document.sha256,
        "discipline": discipline,
        "ruleset_sha256": review["ruleset_sha256"],
        "contract_sha256": _contract_fingerprint(review),
        "blinded": True,
        "assessments": [
            {
                "rule_id": item["rule_id"],
                "question": item["review_question"],
                # Deliberately do not show automated predictions or extracted
                # candidate spans to reviewers before independent assessment.
                "reviewer_assessments": [],
                "adjudicated_verdict": None,
                "adjudication_rationale": None,
            }
            for item in review["items"]
        ],
        "instructions": [
            "Do not reuse automated text cues as scientific truth.",
            "Two real, distinct, qualified reviewers must assess the full manuscript separately.",
            "Record individual verdicts and a reasoned adjudicated verdict for every rule.",
            "For positive/partial verdicts provide exact source quotations (at least 12 characters).",
            "A valid template or accepted import cannot prove qualifications or independent review.",
        ],
    }


def _verify_expert_entry(entry: dict, document: ParsedDocument) -> None:
    if not isinstance(entry, dict):
        raise ValueError("Each reviewer assessment must be an object.")
    reviewer_id = entry.get("reviewer_id")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise ValueError("A reviewer_id is required for each assessor.")
    verdict = entry.get("verdict")
    if verdict not in VERDICTS:
        raise ValueError(f"Expert verdict must be one of {VERDICTS}.")
    rationale = entry.get("rationale")
    if not isinstance(rationale, str) or len(rationale.strip()) < 20:
        raise ValueError("Each expert rationale must contain at least 20 characters.")
    quote = entry.get("source_quote")
    if verdict in ("adequately_reported", "partially_reported"):
        if not isinstance(quote, str) or len(quote.strip()) < 12:
            raise ValueError("Positive/partial findings require a 12+ character exact source quote.")
        if quote not in document.text:
            raise ValueError("Expert quotation is absent from the source manuscript.")
    elif quote is not None and (not isinstance(quote, str) or quote not in document.text):
        raise ValueError("Provided source quotation is absent from manuscript.")


def validate_domain_adjudication(
    document: ParsedDocument, discipline: str, completed: dict
) -> dict:
    if not isinstance(completed, dict):
        raise ValueError("Completed expert review must be a JSON object.")
    expected = make_domain_template(document, discipline)
    for field in ("source_sha256", "discipline", "ruleset_sha256", "contract_sha256"):
        if completed.get(field) != expected[field]:
            raise ValueError(f"Expert review {field} does not match the manuscript/ruleset.")
    if completed.get("blinded") is not True:
        raise ValueError("Review must use a blinded template.")
    provided = completed.get("assessments")
    if not isinstance(provided, list):
        raise ValueError("Expert review assessments must be a list.")
    expected_ids = {item["rule_id"] for item in expected["assessments"]}
    ids = [entry.get("rule_id") for entry in provided if isinstance(entry, dict)]
    if len(ids) != len(provided) or set(ids) != expected_ids or len(ids) != len(expected_ids):
        raise ValueError("Expert review must contain each rule ID once, without omissions.")
    reviewer_ids_seen: set[str] = set()
    reviewer_pair: frozenset[str] | None = None
    summaries = []
    for entry in provided:
        reviewers = entry.get("reviewer_assessments")
        if not isinstance(reviewers, list) or len(reviewers) != 2:
            raise ValueError("Each rule needs exactly two declared reviewer assessments.")
        for reviewer in reviewers:
            _verify_expert_entry(reviewer, document)
        reviewer_ids = [reviewer["reviewer_id"].strip() for reviewer in reviewers]
        if reviewer_ids[0] == reviewer_ids[1]:
            raise ValueError("Reviewer IDs must differ for each rule.")
        ids_for_rule = frozenset(reviewer_ids)
        if reviewer_pair is None:
            reviewer_pair = ids_for_rule
        elif ids_for_rule != reviewer_pair:
            raise ValueError("The same two reviewer IDs must assess every rule.")
        reviewer_ids_seen.update(reviewer_ids)
        if "automated_status" in entry or "source_candidates" in entry:
            raise ValueError("Blinded reviews must not contain pre-filled automated evidence.")
        verdict = entry.get("adjudicated_verdict")
        if verdict not in VERDICTS:
            raise ValueError("Every rule needs an adjudicated verdict.")
        adjudication_rationale = entry.get("adjudication_rationale")
        if not isinstance(adjudication_rationale, str) or len(adjudication_rationale.strip()) < 20:
            raise ValueError("Adjudication rationale must contain at least 20 characters.")
        if verdict in ("adequately_reported", "partially_reported"):
            if not any(
                reviewer["verdict"] in ("adequately_reported", "partially_reported")
                for reviewer in reviewers
            ):
                raise ValueError(
                    "A positive final verdict requires supporting source-quoted reviewer assessment."
                )
        summaries.append({
            "rule_id": entry["rule_id"],
            "reviewer_verdicts": [reviewer["verdict"] for reviewer in reviewers],
            "adjudicated_verdict": verdict,
            "reviewers_disagreed": reviewers[0]["verdict"] != reviewers[1]["verdict"],
        })

    automatic_by_rule = {
        item["rule_id"]: item
        for item in review_domain(document, discipline)["items"]
    }
    comparison = {key: 0 for key in ("tp", "fp", "fn", "tn", "excluded_not_applicable", "excluded_uncertain")}
    compared_by_rule = []
    for entry in summaries:
        final = entry["adjudicated_verdict"]
        predicted = automatic_by_rule[entry["rule_id"]]["status"] == "TEXTUAL_EVIDENCE_CANDIDATE"
        if final in ("not_applicable", "uncertain"):
            comparison["excluded_" + final] += 1
            bucket = "excluded_" + final
        else:
            positive = final in ("adequately_reported", "partially_reported")
            bucket = "tp" if predicted and positive else "fp" if predicted else "fn" if positive else "tn"
            comparison[bucket] += 1
        compared_by_rule.append({
            "rule_id": entry["rule_id"], "outcome": bucket,
            "automatic_candidate_found": predicted,
            "adjudicated_verdict": final,
        })
    ids = sorted(reviewer_ids_seen)
    agreement_counts = {name: Counter() for name in ids}
    matched_verdicts = 0
    for item in provided:
        votes = {r["reviewer_id"].strip(): r["verdict"] for r in item["reviewer_assessments"]}
        for name in ids:
            agreement_counts[name][votes[name]] += 1
        matched_verdicts += votes[ids[0]] == votes[ids[1]]
    n = len(provided)
    agreement = matched_verdicts / n
    chance = sum(
        agreement_counts[ids[0]][label] / n * agreement_counts[ids[1]][label] / n
        for label in VERDICTS
    )
    kappa = (agreement - chance) / (1 - chance) if chance < 1 else None

    def _rate(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    return {
        "schema_version": "1.0",
        "status": "STRUCTURALLY_ACCEPTED_FOR_EXPERT_OVERSIGHT",
        "discipline": discipline,
        "source_sha256": document.sha256,
        "contract_sha256": expected["contract_sha256"],
        "ruleset_sha256": expected["ruleset_sha256"],
        "rule_count": len(expected_ids),
        "declared_reviewer_count": len(reviewer_ids_seen),
        "results": summaries,
        "reviewer_agreement": {
            "raw_exact_agreement": agreement,
            "cohen_kappa": kappa,
            "rule_count": n,
            "disagreements": n - matched_verdicts,
            "interpretation": "Agreement is not proof that either reviewer is scientifically correct.",
        },
        "comparison_against_adjudicated_verdicts": {
            "confusion_matrix": comparison,
            "candidate_precision": _rate(comparison["tp"], comparison["tp"] + comparison["fp"]),
            "candidate_recall": _rate(comparison["tp"], comparison["tp"] + comparison["fn"]),
            "candidate_specificity": _rate(comparison["tn"], comparison["tn"] + comparison["fp"]),
            "per_rule": compared_by_rule,
            "interpretation": (
                "Only candidate retrieval vs adjudicated document-level reporting verdicts. "
                "Not scientific correctness, completeness or reporting-guideline compliance."
            ),
        },
        "blinded_template": True,
        "limitations": [
            "Only structure, hashes, review coverage and exact source-quotation presence were checked.",
            "Reviewer IDs and the template's blinded flag are declarations, not verified reviewer identities, independent assessments, scientific adequacy or claims.",
            "Agreement and candidate retrieval rates from one manuscript with few checklist items are not generalizable performance estimates.",
            "Full expert adjudication and external validation remain human responsibilities.",
        ],
    }
