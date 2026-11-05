"""Source-hash-bound templates for genuine external domain-expert assessments.

This module verifies completeness and source quotation provenance only.
It cannot certify reviewer qualifications, independence or scientific accuracy.
"""
from __future__ import annotations

import hashlib
import json
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
        "assessments": [
            {
                "rule_id": item["rule_id"],
                "question": item["review_question"],
                "automated_status": item["status"],
                "source_candidates": item["evidence"],
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
    provided = completed.get("assessments")
    if not isinstance(provided, list):
        raise ValueError("Expert review assessments must be a list.")
    expected_ids = {item["rule_id"] for item in expected["assessments"]}
    ids = [entry.get("rule_id") for entry in provided if isinstance(entry, dict)]
    if len(ids) != len(provided) or set(ids) != expected_ids or len(ids) != len(expected_ids):
        raise ValueError("Expert review must contain each rule ID once, without omissions.")
    reviewer_ids_seen: set[str] = set()
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
        reviewer_ids_seen.update(reviewer_ids)
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

    return {
        "schema_version": "1.0",
        "status": "STRUCTURALLY_ACCEPTED_FOR_EXPERT_OVERSIGHT",
        "discipline": discipline,
        "source_sha256": document.sha256,
        "contract_sha256": expected["contract_sha256"],
        "rule_count": len(expected_ids),
        "declared_reviewer_count": len(reviewer_ids_seen),
        "results": summaries,
        "limitations": [
            "Only structure, hashes, review coverage and exact source-quotation presence were checked.",
            "The software has not verified reviewer credentials, independent assessments, scientific adequacy or claims.",
            "Full expert adjudication and external validation remain human responsibilities.",
        ],
    }
