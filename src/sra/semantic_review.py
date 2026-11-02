import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from sra.graph import graph_fingerprint


ALLOWED_RELATIONS = {
    "entailed",
    "partially_supported",
    "contradicted",
    "not_supported",
    "unclear",
}


def build_semantic_review_template(audit_report: dict[str, Any]) -> dict[str, Any]:
    graph = audit_report["reasoning_graph"]
    assessments = []
    for inference in (n for n in graph["nodes"] if n["node_type"] == "inference"):
        claim_id = next(
            edge["target"] for edge in graph["edges"]
            if edge["source"] == inference["node_id"] and edge["relation"] == "yields_claim"
        )
        evidence_ids = [
            edge["source"] for edge in graph["edges"]
            if edge["target"] == inference["node_id"] and edge["relation"] == "lexical_candidate_basis"
        ]
        assessments.append({
            "inference_node_id": inference["node_id"],
            "claim_node_id": claim_id,
            "evidence_node_ids": evidence_ids,
            "relation": "",
            "confidence": None,
            "rationale": "",
            "source_quotes": [],
            "missing_assumptions": [],
            "counter_evidence_node_ids": [],
        })
    return {
        "schema_version": "1.0",
        "review_type": "external_semantic_reasoning_review",
        "source_sha256": audit_report["sha256"],
        "graph_fingerprint": graph_fingerprint(graph),
        "reviewer": {
            "name": "",
            "model_or_agent": "",
            "reviewed_at_utc": "",
        },
        "instructions": [
            "Review each claim-inference pair against the complete supplied manuscript, not only the lexical candidates.",
            "Distinguish entailment, partial support, contradiction, no support, and uncertainty.",
            "Do not infer causality from association alone. Examine design, assumptions, confounding, selection, measurement and alternative explanations where relevant.",
            "Use exact source excerpts in source_quotes. Do not fabricate evidence or references.",
            "List material assumptions needed for the inference in missing_assumptions, especially assumptions not established by the manuscript.",
            "Confidence is confidence in this semantic assessment, not a probability that the scientific claim is true.",
            "This template does not run an LLM. A capable reviewer or external agent must fill it, after which the auditor validates its identifiers, source hash and quotes.",
        ],
        "relation_labels": sorted(ALLOWED_RELATIONS),
        "assessments": assessments,
    }


def _normalize_quote(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def validate_semantic_review(
    review: dict[str, Any],
    audit_report: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    graph = audit_report["reasoning_graph"]
    expected_fingerprint = graph_fingerprint(graph)
    errors: list[str] = []

    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict):
        reviewer = {}
        errors.append("reviewer metadata is required.")
    for field in ("name", "model_or_agent", "reviewed_at_utc"):
        if not isinstance(reviewer.get(field), str) or not reviewer[field].strip():
            errors.append(f"reviewer.{field} is required.")
    reviewed_at = reviewer.get("reviewed_at_utc")
    if isinstance(reviewed_at, str) and reviewed_at.strip():
        try:
            parsed_time = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                errors.append("reviewer.reviewed_at_utc must include a timezone.")
        except ValueError:
            errors.append("reviewer.reviewed_at_utc must be ISO-8601.")

    if review.get("schema_version") != "1.0":
        errors.append("Unsupported semantic review schema_version.")
    if review.get("review_type") != "external_semantic_reasoning_review":
        errors.append("Unsupported semantic review review_type.")
    if review.get("source_sha256") != audit_report.get("sha256"):
        errors.append("Source SHA-256 does not match the audited manuscript.")
    if review.get("graph_fingerprint") != expected_fingerprint:
        errors.append("Graph fingerprint does not match the current reasoning graph.")

    node_map = {node["node_id"]: node for node in graph["nodes"]}
    inference_nodes = {k for k, v in node_map.items() if v["node_type"] == "inference"}
    expected_claim_by_inference = {
        edge["source"]: edge["target"] for edge in graph["edges"]
        if edge.get("relation") == "yields_claim"
    }
    assessment_items = review.get("assessments")
    if not isinstance(assessment_items, list):
        assessment_items = []
        errors.append("assessments must be a JSON array.")

    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(assessment_items):
        if not isinstance(item, dict):
            errors.append(f"Assessment {index} must be an object.")
            continue
        inference_id = item.get("inference_node_id")
        if not isinstance(inference_id, str) or inference_id not in inference_nodes:
            errors.append(f"Assessment {index} references an unknown inference node.")
            continue
        if inference_id in seen:
            errors.append(f"Duplicate assessment for inference node {inference_id}.")
            continue
        seen.add(inference_id)

        claim_id = item.get("claim_node_id")
        if not isinstance(claim_id, str) or claim_id not in node_map or node_map[claim_id]["node_type"] != "claim":
            errors.append(f"Assessment {index} references an invalid claim node.")
        elif expected_claim_by_inference.get(inference_id) != claim_id:
            errors.append(f"Assessment {index} claim node does not match its inference node.")
        evidence_ids = item.get("evidence_node_ids", [])
        if not isinstance(evidence_ids, list) or any(not isinstance(x, str) for x in evidence_ids) or len(evidence_ids) != len(set(evidence_ids)) or any(
            evidence_id not in node_map or node_map[evidence_id]["node_type"] != "evidence"
            for evidence_id in evidence_ids
        ):
            errors.append(f"Assessment {index} has invalid or duplicate evidence_node_ids.")
            evidence_ids = []

        relation = item.get("relation")
        if not isinstance(relation, str) or relation not in ALLOWED_RELATIONS:
            errors.append(f"Assessment {index} has an invalid relation label.")
        confidence = item.get("confidence")
        try:
            confidence_number = float(confidence) if not isinstance(confidence, bool) else float("nan")
        except (TypeError, ValueError, OverflowError):
            confidence_number = float("nan")
        if (
            not isinstance(confidence, (int, float))
            or not math.isfinite(confidence_number)
            or not 0 <= confidence_number <= 1
        ):
            errors.append(f"Assessment {index} confidence must be finite and numeric in [0, 1].")
        rationale = item.get("rationale")
        if not isinstance(rationale, str) or not rationale.strip():
            errors.append(f"Assessment {index} rationale is required.")

        quotes = item.get("source_quotes", [])
        if not isinstance(quotes, list) or any(not isinstance(q, str) for q in quotes):
            errors.append(f"Assessment {index} source_quotes must be an array of strings.")
            quotes = []
        normalized_source = _normalize_quote(source_text)
        for quote in quotes:
            if not quote.strip() or _normalize_quote(quote) not in normalized_source:
                errors.append(f"Assessment {index} contains a quote that is not found in the source.")
                break
        if relation in {"entailed", "partially_supported", "contradicted"} and not quotes:
            errors.append(f"Assessment {index} requires at least one verifiable source quote.")
        if relation in {"entailed", "partially_supported", "contradicted"} and not evidence_ids:
            errors.append(f"Assessment {index} requires at least one evidence node.")

        missing_assumptions = item.get("missing_assumptions", [])
        if not isinstance(missing_assumptions, list) or any(not isinstance(x, str) for x in missing_assumptions):
            errors.append(f"Assessment {index} missing_assumptions must be an array of strings.")
            missing_assumptions = []

        counter_ids = item.get("counter_evidence_node_ids", [])
        if not isinstance(counter_ids, list) or any(not isinstance(x, str) for x in counter_ids) or len(counter_ids) != len(set(counter_ids)) or any(
            counter_id not in node_map or node_map[counter_id]["node_type"] != "evidence"
            for counter_id in counter_ids
        ):
            errors.append(f"Assessment {index} has invalid or duplicate counter_evidence_node_ids.")
            counter_ids = []

        if relation in {"entailed", "partially_supported", "contradicted"} and quotes:
            cited_texts = [
                node_map[evidence_id]["text"]
                for evidence_id in evidence_ids + counter_ids
                if evidence_id in node_map
            ]
            if not any(
                _normalize_quote(quote) in _normalize_quote(text)
                for quote in quotes for text in cited_texts
            ):
                errors.append(
                    f"Assessment {index} quotes source text but not text from its cited evidence node(s)."
                )

        validated.append({
            "inference_node_id": inference_id,
            "claim_node_id": claim_id,
            "evidence_node_ids": evidence_ids,
            "relation": relation,
            "confidence": confidence,
            "rationale": rationale.strip() if isinstance(rationale, str) else "",
            "source_quotes": quotes,
            "missing_assumptions": missing_assumptions,
            "counter_evidence_node_ids": counter_ids,
            "validation_status": "structurally_validated_not_truth_verified",
        })

    missing = sorted(inference_nodes - seen)
    if missing:
        errors.append(f"Missing semantic assessments for {len(missing)} inference node(s).")

    return {
        "schema_version": "1.0",
        "status": "ACCEPTED_FOR_REVIEW" if not errors else "REJECTED",
        "structural_validation_only": True,
        "assessment_count": len(validated),
        "validated_assessments": validated,
        "errors": errors,
        "limitations": [
            "The auditor validates reviewer identity fields, node references, source hashes and quoted text only.",
            "It does not independently prove that an LLM's semantic judgment or rationale is correct.",
            "Accepted assessments still require scientific expert adjudication for high-stakes conclusions.",
        ],
    }


def load_semantic_review(path: str | Path) -> dict:
    file_path = Path(path).expanduser().resolve()
    result = json.loads(file_path.read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise ValueError("Semantic review JSON root must be an object.")
    return result
