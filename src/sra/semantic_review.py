import json
import math
import re
from datetime import datetime, timedelta
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
REVIEWER_FIELDS = {"name", "model_or_agent", "reviewed_at_utc"}
TOP_LEVEL_FIELDS = {
    "schema_version", "review_type", "review_mode", "source_sha256",
    "graph_fingerprint", "evidence_catalog", "reviewer", "instructions", "relation_labels", "assessments",
}
ASSESSMENT_FIELDS = {
    "inference_node_id", "claim_node_id", "evidence_node_ids", "relation",
    "confidence", "rationale", "source_quotes", "missing_assumptions",
    "counter_evidence_node_ids", "reviewer_selected_evidence_node_ids",
}
MIN_QUOTE_CHARACTERS = 20


def build_semantic_review_template(
    audit_report: dict[str, Any],
    review_mode: str = "single",
) -> dict[str, Any]:
    if review_mode not in {"single", "parallel"}:
        raise ValueError("review_mode must be 'single' or 'parallel'.")
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
            "reviewer_selected_evidence_node_ids": [],
        })
    evidence_catalog = [
        {
            "node_id": node["node_id"],
            "text": node["text"],
            "source_location": node["source_location"],
        }
        for node in graph["nodes"]
        if node["node_type"] == "evidence"
    ]
    return {
        "schema_version": "1.3",
        "review_type": "external_semantic_reasoning_review",
        "review_mode": review_mode,
        "source_sha256": audit_report["sha256"],
        "graph_fingerprint": graph_fingerprint(graph),
        "evidence_catalog": evidence_catalog,
        "reviewer": {
            "name": "",
            "model_or_agent": "",
            "reviewed_at_utc": "",
        },
        "instructions": [
            (
                "Use one model to review all assessments."
                if review_mode == "single"
                else "Use parallel agents. Give every agent the complete manuscript and a clearly assigned subset of assessments; merge their outputs by inference_node_id and ensure none are missing or duplicated."
            ),
            "Review each claim-inference pair against the complete supplied manuscript, not only the lexical candidates.",
            "Distinguish entailment, partial support, contradiction, no support, and uncertainty.",
            "Do not infer causality from association alone. Examine design, assumptions, confounding, selection, measurement and alternative explanations where relevant.",
            "Use exact source excerpts in source_quotes. Do not fabricate evidence or references.",
            "The evidence_catalog contains every extracted Results node, its exact source text and location. Keep graph-linked lexical candidates in evidence_node_ids. If you identify other relevant Results passages, list their evidence_catalog IDs in reviewer_selected_evidence_node_ids; these are reviewer-selected passages, not automatically verified links.",
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
    errors: list[str] = []
    if not isinstance(review, dict):
        return {
            "schema_version": "1.3",
            "status": "REJECTED",
            "structural_validation_only": True,
            "review_mode": None,
            "assessment_count": 0,
            "validated_assessments": [],
            "errors": ["Semantic review root must be a JSON object."],
            "limitations": [
                "Structural acceptance does not prove semantic correctness or scientific truth."
            ],
        }

    graph = audit_report["reasoning_graph"]
    expected_fingerprint = graph_fingerprint(graph)
    input_schema_version = review.get("schema_version")
    legacy_schema = input_schema_version == "1.0"
    current_schema = input_schema_version == "1.3"
    strict_quotes = input_schema_version in {"1.2", "1.3"}
    effective_review_mode = "single" if legacy_schema else review.get("review_mode")

    required_top_fields = (
        TOP_LEVEL_FIELDS
        if current_schema
        else TOP_LEVEL_FIELDS - {"evidence_catalog"}
    )
    allowed_top_fields = required_top_fields if not legacy_schema else required_top_fields - {"review_mode"}
    missing_top_fields = (required_top_fields - ({"review_mode"} if legacy_schema else set())) - set(review)
    unexpected_top_fields = set(review) - allowed_top_fields
    if missing_top_fields:
        errors.append(f"Missing top-level semantic review fields: {sorted(missing_top_fields)}.")
    if unexpected_top_fields:
        errors.append(f"Unexpected top-level semantic review fields: {sorted(unexpected_top_fields)}.")

    instructions = review.get("instructions")
    if not isinstance(instructions, list) or any(not isinstance(value, str) for value in instructions):
        errors.append("instructions must be an array of strings.")
    relation_labels = review.get("relation_labels")
    if not isinstance(relation_labels, list) or any(
        not isinstance(value, str) or value not in ALLOWED_RELATIONS
        for value in relation_labels
    ):
        errors.append("relation_labels must be an array of supported relation labels.")

    reviewer = review.get("reviewer")
    if not isinstance(reviewer, dict):
        reviewer = {}
        errors.append("reviewer metadata is required.")
    unexpected_reviewer_fields = set(reviewer) - REVIEWER_FIELDS
    if unexpected_reviewer_fields:
        errors.append(f"Unexpected reviewer fields: {sorted(unexpected_reviewer_fields)}.")
    for field in ("name", "model_or_agent", "reviewed_at_utc"):
        if not isinstance(reviewer.get(field), str) or not reviewer[field].strip():
            errors.append(f"reviewer.{field} is required.")
    reviewed_at = reviewer.get("reviewed_at_utc")
    if isinstance(reviewed_at, str) and reviewed_at.strip():
        try:
            parsed_time = datetime.fromisoformat(reviewed_at.replace("Z", "+00:00"))
            if parsed_time.tzinfo is None:
                errors.append("reviewer.reviewed_at_utc must include a timezone.")
            elif current_schema and parsed_time.utcoffset() != timedelta(0):
                errors.append("reviewer.reviewed_at_utc must use UTC (Z or +00:00).")
        except ValueError:
            errors.append("reviewer.reviewed_at_utc must be ISO-8601.")

    if input_schema_version not in {"1.0", "1.1", "1.2", "1.3"}:
        errors.append("Unsupported semantic review schema_version.")
    if legacy_schema:
        if review.get("review_mode") not in {None, "single"}:
            errors.append("Legacy semantic review schema 1.0 supports single-model mode only.")
        effective_review_mode = "single"
    elif effective_review_mode not in {"single", "parallel"}:
        errors.append("review_mode must be 'single' or 'parallel'.")
    if review.get("review_type") != "external_semantic_reasoning_review":
        errors.append("Unsupported semantic review review_type.")
    if review.get("source_sha256") != audit_report.get("sha256"):
        errors.append("Source SHA-256 does not match the audited manuscript.")
    if review.get("graph_fingerprint") != expected_fingerprint:
        errors.append("Graph fingerprint does not match the current reasoning graph.")

    evidence_nodes_by_id = {
        node["node_id"]: node for node in graph["nodes"]
        if node.get("node_type") == "evidence"
    }
    if current_schema:
        catalog = review.get("evidence_catalog")
        if not isinstance(catalog, list):
            errors.append("evidence_catalog must be an array.")
        else:
            catalog_ids: list[str] = []
            for catalog_index, entry in enumerate(catalog):
                if not isinstance(entry, dict):
                    errors.append(f"Evidence catalog entry {catalog_index} must be an object.")
                    continue
                if set(entry) != {"node_id", "text", "source_location"}:
                    errors.append(f"Evidence catalog entry {catalog_index} has missing or unexpected fields.")
                    continue
                evidence_id = entry.get("node_id")
                if not isinstance(evidence_id, str) or evidence_id not in evidence_nodes_by_id:
                    errors.append(f"Evidence catalog entry {catalog_index} references an unknown evidence node.")
                    continue
                catalog_ids.append(evidence_id)
                actual_node = evidence_nodes_by_id[evidence_id]
                if entry.get("text") != actual_node.get("text"):
                    errors.append(f"Evidence catalog text does not match source node {evidence_id}.")
                if entry.get("source_location") != actual_node.get("source_location"):
                    errors.append(f"Evidence catalog location does not match source node {evidence_id}.")
            if len(catalog_ids) != len(set(catalog_ids)):
                errors.append("evidence_catalog contains duplicate node IDs.")
            if set(catalog_ids) != set(evidence_nodes_by_id):
                errors.append("evidence_catalog must contain every evidence node exactly once.")

    node_map = {node["node_id"]: node for node in graph["nodes"]}
    inference_nodes = {k for k, v in node_map.items() if v["node_type"] == "inference"}
    expected_claim_by_inference = {
        edge["source"]: edge["target"] for edge in graph["edges"]
        if edge.get("relation") == "yields_claim"
    }
    linked_evidence_by_inference: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        if edge.get("relation") == "lexical_candidate_basis":
            linked_evidence_by_inference.setdefault(edge.get("target"), set()).add(edge.get("source"))
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
        required_assessment_fields = (
            ASSESSMENT_FIELDS if current_schema
            else ASSESSMENT_FIELDS - {"reviewer_selected_evidence_node_ids"}
        )
        allowed_assessment_fields = ASSESSMENT_FIELDS if current_schema else required_assessment_fields
        missing_assessment_fields = required_assessment_fields - set(item)
        unexpected_assessment_fields = set(item) - allowed_assessment_fields
        if missing_assessment_fields:
            errors.append(
                f"Assessment {index} is missing required fields: {sorted(missing_assessment_fields)}."
            )
        if unexpected_assessment_fields:
            errors.append(
                f"Assessment {index} has unexpected fields: {sorted(unexpected_assessment_fields)}."
            )
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
        elif any(
            evidence_id not in linked_evidence_by_inference.get(inference_id, set())
            for evidence_id in evidence_ids
        ):
            errors.append(
                f"Assessment {index} selects evidence not linked to its inference node by the reasoning graph."
            )

        relation = item.get("relation")
        if not isinstance(relation, str) or relation not in ALLOWED_RELATIONS:
            errors.append(f"Assessment {index} has an invalid relation label.")
            relation = "unclear"
        elif isinstance(relation_labels, list) and relation not in relation_labels:
            errors.append(f"Assessment {index} relation is not declared in relation_labels.")
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
        reviewer_selected_ids = item.get("reviewer_selected_evidence_node_ids", [])
        if not isinstance(reviewer_selected_ids, list) or any(
            not isinstance(x, str) for x in reviewer_selected_ids
        ) or len(reviewer_selected_ids) != len(set(reviewer_selected_ids)) or any(
            evidence_id not in node_map or node_map[evidence_id]["node_type"] != "evidence"
            for evidence_id in reviewer_selected_ids
        ):
            errors.append(
                f"Assessment {index} has invalid or duplicate reviewer_selected_evidence_node_ids."
            )
            reviewer_selected_ids = []
        if set(evidence_ids) & set(reviewer_selected_ids):
            errors.append(
                f"Assessment {index} duplicates graph-linked and reviewer-selected evidence IDs."
            )

        selected_support_ids = evidence_ids + reviewer_selected_ids
        if relation in {"entailed", "partially_supported"} and not selected_support_ids:
            errors.append(
                f"Assessment {index} requires graph-linked or explicitly reviewer-selected evidence."
            )

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
        if set(selected_support_ids) & set(counter_ids):
            errors.append(f"Assessment {index} cannot classify the same node as support and counter-evidence.")
        if relation == "contradicted" and not counter_ids:
            errors.append(f"Assessment {index} requires at least one separately identified counter-evidence node.")

        relevant_ids = (
            counter_ids if relation == "contradicted"
            else selected_support_ids + counter_ids
        )
        cited_texts = [
            node_map[evidence_id]["text"]
            for evidence_id in relevant_ids
            if evidence_id in node_map
        ]
        for quote in quotes:
            normalized_quote = _normalize_quote(quote)
            if not quote.strip() or (strict_quotes and len(quote) < MIN_QUOTE_CHARACTERS):
                errors.append(
                    f"Assessment {index} contains an excerpt too short to be a meaningful evidence quotation."
                )
                break
            if normalized_quote not in normalized_source:
                errors.append(f"Assessment {index} contains a quote that is not found in the source.")
                break
            if not any(normalized_quote in _normalize_quote(text) for text in cited_texts):
                errors.append(
                    f"Assessment {index} quote is not contained in its selected evidence/counter-evidence node(s)."
                )
                break
        if relation in {"entailed", "partially_supported", "contradicted"} and not quotes:
            errors.append(f"Assessment {index} requires at least one evidence quotation.")

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
            "reviewer_selected_evidence_node_ids": reviewer_selected_ids,
            "validation_status": "structurally_validated_not_truth_verified",
        })

    missing = sorted(inference_nodes - seen)
    if missing:
        errors.append(f"Missing semantic assessments for {len(missing)} inference node(s).")

    return {
        "schema_version": "1.3",
        "status": "ACCEPTED_FOR_REVIEW" if not errors else "REJECTED",
        "structural_validation_only": True,
        "review_mode": effective_review_mode,
        "assessment_count": len(validated),
        "validated_assessments": validated,
        "errors": errors,
        "limitations": [
            "The auditor validates reviewer identity fields, node references, source hashes and quoted text only.",
            "Reviewer-selected evidence IDs are checked for node type and source-quote provenance, not semantic relevance.",
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
