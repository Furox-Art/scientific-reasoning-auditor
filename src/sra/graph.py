import hashlib
from collections import Counter
import json
import re
from typing import Any

from sra.checks import (
    LIMITATIONS,
    METHODS,
    RESULTS,
    _norm_words,
    _section_entries,
    _jaccard,
    _has_affirmed_match,
    _sentences,
)
from sra.document import ParsedDocument
from sra.models import ClaimEvidenceCandidate


ASSUMPTION_MARKER = re.compile(
    r"\b(assumption|assumptions|assume|assumes|assumed|assuming|under the assumption)\b|"
    r"varsayım|varsayımı|varsayıyoruz|varsayılır|kabulüyle|kabul edilerek",
    re.IGNORECASE,
)
CAUSAL_MARKER = re.compile(
    r"\b(cause|causes|caused|causal|leads? to|resulted in|induces?|"
    r"increas\w*|decreas\w*|reduc\w*|improv\w*|worsen\w*|raises?|lowers?)\b|"
    r"neden olur|sebep olur|yol açar|artır\w*|azalt\w*|iyileştir\w*|kötüleştir\w*",
    re.IGNORECASE,
)


def _stable_id(source_hash: str, node_type: str, line: int | None, text: str, ordinal: int) -> str:
    raw = f"{source_hash}|{node_type}|{line}|{ordinal}|{text}"
    suffix = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{node_type}:{suffix}"


def _edge_id(source: str, target: str, relation: str) -> str:
    raw = f"{source}|{target}|{relation}"
    return "edge:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _graph_contract() -> dict[str, Any]:
    return {
        "fingerprint_algorithm": GRAPH_FINGERPRINT_ALGORITHM,
        "node_types": list(GRAPH_NODE_TYPES),
        "node_statuses": list(GRAPH_NODE_STATUSES),
        "edge_relations": list(GRAPH_EDGE_RELATIONS),
        "edge_statuses": list(GRAPH_EDGE_STATUSES),
        "edge_endpoint_types": {
            relation: {
                "source": sorted(source_types),
                "target": sorted(target_types),
            }
            for relation, (source_types, target_types) in EDGE_ENDPOINT_TYPES.items()
        },
    }


def legacy_graph_fingerprint_v1_1(graph: dict[str, Any]) -> str:
    """Reproduce the public v0.5.1 graph fingerprint for unchanged node/edge data."""
    payload = {
        "schema_version": "1.1",
        "source_sha256": graph.get("source_sha256"),
        "nodes": graph.get("nodes", []),
        "edges": graph.get("edges", []),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def graph_fingerprint(graph: dict[str, Any]) -> str:
    payload = {
        "schema_version": graph.get("schema_version"),
        "fingerprint_algorithm": graph.get("fingerprint_algorithm"),
        "source_sha256": graph.get("source_sha256"),
        "node_types": graph.get("node_types"),
        "node_statuses": graph.get("node_statuses"),
        "edge_relations": graph.get("edge_relations"),
        "edge_statuses": graph.get("edge_statuses"),
        "edge_endpoint_types": graph.get("edge_endpoint_types"),
        "nodes": graph.get("nodes", []),
        "edges": graph.get("edges", []),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _node(
    source_hash: str,
    node_type: str,
    entry: dict,
    ordinal: int,
    extraction_method: str,
    status: str = "extracted_heuristically",
) -> dict:
    text = entry["text"]
    line = entry.get("line")
    return {
        "node_id": _stable_id(source_hash, node_type, line, text, ordinal),
        "node_type": node_type,
        "text": text,
        "source_location": {
            "line": line,
            "section": entry.get("section"),
        },
        "extraction_method": extraction_method,
        "status": status,
        "metadata": {},
    }


def _make_edge(source: str, target: str, relation: str, status: str, **metadata) -> dict:
    return {
        "edge_id": _edge_id(source, target, relation),
        "source": source,
        "target": target,
        "relation": relation,
        "status": status,
        "metadata": metadata,
    }


GRAPH_SCHEMA_VERSION = "1.4"
GRAPH_FINGERPRINT_ALGORITHM = "sha256-canonical-json-graph-contract-v2"
GRAPH_NODE_FIELDS = frozenset({
    "node_id", "node_type", "text", "source_location",
    "extraction_method", "status", "metadata",
})
GRAPH_EDGE_FIELDS = frozenset({
    "edge_id", "source", "target", "relation", "status", "metadata",
})
GRAPH_OBJECT_FIELDS = frozenset({
    "schema_version",
    "fingerprint_algorithm",
    "source_sha256",
    "node_types",
    "node_statuses",
    "edge_relations",
    "edge_statuses",
    "edge_endpoint_types",
    "nodes",
    "edges",
    "validation",
    "graph_fingerprint",
})


GRAPH_NODE_TYPES = (
    "method", "evidence", "assumption", "assumption_gap",
    "limitation", "inference", "claim", "document_context",
)
GRAPH_NODE_STATUSES = (
    "extracted_heuristically", "not_semantically_verified", "document_context_only",
    "candidate_assumptions_found_review_required", "not_linked_to_claim_review_required",
    "not_extracted_review_required",
)
GRAPH_EDGE_RELATIONS = (
    "method_context_candidate", "method_document_context", "limitation_document_context",
    "lexical_candidate_basis", "yields_claim", "assumption_candidate_required_for",
    "assumption_review_required", "qualifies_claim_candidate",
    "possible_contradiction_candidate", "document_context_membership",
)
GRAPH_EDGE_STATUSES = (
    "structural_extraction_only", "heuristic_only", "structural_grouping_only",
    "document_context_only", "rule_based_gap_signal", "heuristic_review_required",
)
EDGE_ENDPOINT_TYPES = {
    "method_context_candidate": ({"method"}, {"evidence"}),
    "method_document_context": ({"document_context"}, {"inference"}),
    "limitation_document_context": ({"document_context"}, {"inference"}),
    "lexical_candidate_basis": ({"evidence"}, {"inference"}),
    "yields_claim": ({"inference"}, {"claim"}),
    "assumption_candidate_required_for": ({"assumption"}, {"inference"}),
    "assumption_review_required": ({"assumption_gap"}, {"inference"}),
    "qualifies_claim_candidate": ({"limitation"}, {"claim"}),
    "possible_contradiction_candidate": ({"evidence"}, {"claim"}),
    "document_context_membership": ({"method", "limitation"}, {"document_context"}),
}


def _edge_key_by_line(nodes: list[dict], node_type: str) -> dict[tuple[int | None, str], dict]:
    return {
        (node["source_location"].get("line"), node["text"]): node
        for node in nodes if node["node_type"] == node_type
    }


def _explicit_assumption_entries(document: ParsedDocument) -> list[dict]:
    entries = []
    for name, value in document.sections.items():
        if name.lower().strip() in {"references", "bibliography", "kaynakça"}:
            continue
        section_entries = _sentences(value, document.section_start_lines.get(name, 1), name)
        entries.extend(item for item in section_entries if ASSUMPTION_MARKER.search(item["text"]))
    return entries


def build_reasoning_graph(
    document: ParsedDocument,
    candidates: list[ClaimEvidenceCandidate],
    reasoning_map: list[dict],
) -> dict[str, Any]:
    nodes: list[dict] = []
    edges: list[dict] = []
    counters: dict[str, int] = {}

    def add_nodes(node_type: str, entries: list[dict], method: str) -> list[dict]:
        created = []
        for entry in entries:
            counters[node_type] = counters.get(node_type, 0) + 1
            item = _node(document.sha256, node_type, entry, counters[node_type], method)
            nodes.append(item)
            created.append(item)
        return created

    methods = add_nodes("method", _section_entries(document, METHODS), "heading_and_sentence_rules_v1")
    evidence = add_nodes("evidence", _section_entries(document, RESULTS), "heading_and_sentence_rules_v1")
    assumptions = add_nodes(
        "assumption", _explicit_assumption_entries(document), "explicit_assumption_phrase_rules_v1"
    )
    limitations_entries = _section_entries(document, LIMITATIONS)
    limitations = add_nodes("limitation", limitations_entries, "limitations_section_rules_v1")

    claim_nodes: list[dict] = []
    inference_nodes: list[dict] = []
    evidence_by_location = _edge_key_by_line(evidence, "evidence")

    for candidate in candidates:
        claim_entry = {
            "text": candidate.claim,
            "line": candidate.claim_line,
            "section": candidate.claim_section,
        }
        counters["claim"] = counters.get("claim", 0) + 1
        claim_node = _node(
            document.sha256, "claim", claim_entry, counters["claim"], "claim_marker_and_discussion_conclusion_rules_v1"
        )
        claim_node["metadata"] = {
            "candidate_match_status": candidate.match_status,
            "lexical_overlap": candidate.lexical_overlap,
        }
        nodes.append(claim_node)
        claim_nodes.append(claim_node)

        inference_entry = {
            "text": f"Assess whether the available results justify this claim: {candidate.claim}",
            "line": candidate.claim_line,
            "section": candidate.claim_section,
        }
        counters["inference"] = counters.get("inference", 0) + 1
        inference_node = _node(
            document.sha256, "inference", inference_entry, counters["inference"],
            "one_inference_per_extracted_claim_v1", "not_semantically_verified"
        )
        inference_node["metadata"] = {
            "review_required": True,
            "candidate_match_status": candidate.match_status,
        }
        nodes.append(inference_node)
        inference_nodes.append(inference_node)
        edges.append(_make_edge(
            inference_node["node_id"], claim_node["node_id"], "yields_claim",
            "structural_extraction_only"
        ))

        if candidate.candidate_support and candidate.support_line is not None:
            evidence_node = evidence_by_location.get((candidate.support_line, candidate.candidate_support))
            if evidence_node:
                edges.append(_make_edge(
                    evidence_node["node_id"], inference_node["node_id"],
                    "lexical_candidate_basis", "heuristic_only",
                    lexical_overlap=candidate.lexical_overlap,
                ))

    # Group document-level context once per section, avoiding a Cartesian
    # product between every method/limitation sentence and every inference.
    context_groups = (
        ("methods", methods, "method_document_context"),
        ("limitations", limitations, "limitation_document_context"),
    )
    for context_type, members, inference_relation in context_groups:
        if not members:
            continue
        counters["document_context"] = counters.get("document_context", 0) + 1
        context_entry = {
            "text": f"Document-level {context_type} context containing {len(members)} extracted passage(s).",
            "line": None,
            "section": context_type,
        }
        context_node = _node(
            document.sha256, "document_context", context_entry,
            counters["document_context"], "section_context_group_v1", "document_context_only"
        )
        context_node["metadata"] = {
            "context_type": context_type,
            "member_count": len(members),
        }
        nodes.append(context_node)
        for member in members:
            edges.append(_make_edge(
                member["node_id"], context_node["node_id"],
                "document_context_membership", "structural_grouping_only",
                member_type=member["node_type"],
            ))
        for inference in inference_nodes:
            edges.append(_make_edge(
                context_node["node_id"], inference["node_id"],
                inference_relation, "document_context_only",
            ))

    # Connect methods to evidence only when text overlap is present. Never imply
    # that mere co-location proves that a method generated a particular result.
    for method in methods:
        method_terms = _norm_words(method["text"])
        for item in evidence:
            overlap = _jaccard(method_terms, _norm_words(item["text"]))
            if overlap >= 0.12 and len(method_terms & _norm_words(item["text"])) >= 2:
                edges.append(_make_edge(
                    method["node_id"], item["node_id"], "method_context_candidate",
                    "heuristic_only", lexical_overlap=round(overlap, 3),
                ))

    # Assumptions are extracted only when explicitly signalled. Missing explicit
    # wording is represented as a gap, not as proof that no assumption exists.
    assumptions_by_text = []
    for assumption in assumptions:
        assumptions_by_text.append((assumption, _norm_words(assumption["text"])))
    for claim, inference in zip(claim_nodes, inference_nodes):
        claim_terms = _norm_words(claim["text"])
        linked = False
        for assumption, assumption_terms in assumptions_by_text:
            overlap = _jaccard(claim_terms, assumption_terms)
            if overlap >= 0.10 and len(claim_terms & assumption_terms) >= 2:
                edges.append(_make_edge(
                    assumption["node_id"], inference["node_id"], "assumption_candidate_required_for",
                    "heuristic_only", lexical_overlap=round(overlap, 3),
                ))
                linked = True
        if _has_affirmed_match(claim["text"], CAUSAL_MARKER):
            if linked:
                gap_text = (
                    "Lexically similar assumption statement(s) were found, but lexical overlap does not establish "
                    "that they satisfy causal-identification requirements. Review confounding, exchangeability, "
                    "consistency, positivity, selection, measurement and interference as applicable."
                )
                gap_status = "candidate_assumptions_found_review_required"
            elif assumptions:
                gap_text = (
                    "Explicit assumption statement(s) were extracted, but no lexical relation to this causal claim "
                    "was established. This is not proof the assumptions are irrelevant."
                )
                gap_status = "not_linked_to_claim_review_required"
            else:
                gap_text = (
                    "No explicit causal-identification assumption was extracted by the current rules. "
                    "This is not proof that assumptions are absent from the full manuscript."
                )
                gap_status = "not_extracted_review_required"
            entry = {"text": gap_text, "line": None, "section": None}
            counters["assumption_gap"] = counters.get("assumption_gap", 0) + 1
            gap = _node(
                document.sha256, "assumption_gap", entry, counters["assumption_gap"],
                "causal_claim_assumption_gap_rule_v1", gap_status
            )
            nodes.append(gap)
            edges.append(_make_edge(
                gap["node_id"], inference["node_id"], "assumption_review_required",
                "rule_based_gap_signal",
            ))

    for limitation in limitations:
        limit_terms = _norm_words(limitation["text"])
        for claim in claim_nodes:
            overlap = _jaccard(limit_terms, _norm_words(claim["text"]))
            if overlap >= 0.10 and len(limit_terms & _norm_words(claim["text"])) >= 2:
                edges.append(_make_edge(
                    limitation["node_id"], claim["node_id"], "qualifies_claim_candidate",
                    "heuristic_only", lexical_overlap=round(overlap, 3),
                ))

    # Reuse contradiction signals already identified by the deterministic
    # screening layer; the graph records them as candidates, not semantic facts.
    for relation in reasoning_map:
        if relation.get("relation") != "possible_directional_contradiction":
            continue
        result = evidence_by_location.get((
            relation.get("results_line"), relation.get("results_sentence")
        ))
        target_claim = next(
            (item for item in claim_nodes
             if item["text"] == relation.get("conclusion_sentence")
             and item["source_location"].get("line") == relation.get("conclusion_line")),
            None,
        )
        if result and target_claim:
            edges.append(_make_edge(
                result["node_id"], target_claim["node_id"],
                "possible_contradiction_candidate", "heuristic_review_required",
                topic_overlap=relation.get("topic_overlap"),
            ))

    graph = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "source_sha256": document.sha256,
        **_graph_contract(),
        "nodes": nodes,
        "edges": edges,
        "validation": None,
    }
    graph["graph_fingerprint"] = graph_fingerprint(graph)
    graph["validation"] = validate_reasoning_graph_object(
        graph, allow_unset_validation=True
    )
    return graph


def validate_reasoning_graph_object(
    graph: dict[str, Any], *, allow_unset_validation: bool = False
) -> dict[str, Any]:
    """Validate a complete graph object, including supported schema version and canonical contract."""
    if not isinstance(graph, dict):
        invalid = validate_reasoning_graph(None, None)
        invalid["invalid_schema_version"] = [None]
        invalid["invalid_graph_fingerprint"] = [None]
        invalid["invalid_graph_validation"] = ["validation"]
        invalid["status"] = "FAIL"
        return invalid

    metadata = {
        key: graph.get(key)
        for key in _graph_contract()
    }
    metadata["source_sha256"] = graph.get("source_sha256")
    unexpected_graph_fields = sorted(set(graph) - GRAPH_OBJECT_FIELDS)
    source_hash = graph.get("source_sha256")
    invalid_source_sha256 = (
        [] if isinstance(source_hash, str) and re.fullmatch(r"[a-f0-9]{64}", source_hash)
        else [source_hash]
    )
    result = validate_reasoning_graph(
        graph.get("nodes"),
        graph.get("edges"),
        metadata=metadata,
        strict_objects=True,
    )
    schema_version = graph.get("schema_version")
    result["invalid_schema_version"] = (
        [] if schema_version == GRAPH_SCHEMA_VERSION else [schema_version]
    )
    result["invalid_graph_fields"] = unexpected_graph_fields
    result["invalid_source_sha256"] = invalid_source_sha256
    if result["invalid_schema_version"] or unexpected_graph_fields or invalid_source_sha256:
        result["status"] = "FAIL"
    expected_fingerprint = graph_fingerprint(graph)
    actual_fingerprint = graph.get("graph_fingerprint")
    result["invalid_graph_fingerprint"] = (
        [] if actual_fingerprint == expected_fingerprint else [actual_fingerprint]
    )
    if result["invalid_graph_fingerprint"]:
        result["status"] = "FAIL"
    stored_validation = graph.get("validation")
    result["invalid_graph_validation"] = []
    if not allow_unset_validation and (
        not isinstance(stored_validation, dict) or stored_validation != result
    ):
        result["invalid_graph_validation"] = ["validation"]
        result["status"] = "FAIL"
    return result


def validate_reasoning_graph(
    nodes: list[dict],
    edges: list[dict],
    *,
    metadata: dict[str, Any] | None = None,
    strict_objects: bool = False,
) -> dict[str, Any]:
    """Validate node/edge structure; metadata, when supplied, is checked against the canonical contract."""
    invalid_nodes: list[int] = []
    invalid_node_types: list[int] = []
    invalid_node_statuses: list[int] = []
    invalid_node_schema: list[int] = []
    invalid_edges: list[int] = []
    invalid_edge_schema: list[int] = []
    invalid_schema_metadata: list[str] = []
    invalid_edge_relations: list[int] = []
    invalid_edge_statuses: list[int] = []
    invalid_edge_ids: list[int] = []
    invalid_edge_endpoint_types: list[int] = []
    ids: list[str] = []
    node_records: list[dict] = []
    node_ordinals: Counter[str] = Counter()
    expected_metadata = _graph_contract()
    if metadata is not None:
        if not isinstance(metadata, dict):
            invalid_schema_metadata.append("metadata")
        else:
            for key, expected_value in expected_metadata.items():
                if metadata.get(key) != expected_value:
                    invalid_schema_metadata.append(key)

    if not isinstance(nodes, list):
        nodes = []
        invalid_nodes.append(-1)
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            invalid_nodes.append(index)
            continue
        node_id = node.get("node_id")
        if not isinstance(node_id, str) or not node_id.strip():
            invalid_nodes.append(index)
            continue
        ids.append(node_id)
        node_records.append(node)
        if strict_objects:
            location = node.get("source_location")
            location_valid = (
                isinstance(location, dict)
                and set(location) == {"line", "section"}
                and (
                    location.get("line") is None
                    or (
                        isinstance(location.get("line"), int)
                        and not isinstance(location.get("line"), bool)
                        and location.get("line") >= 1
                    )
                )
                and (
                    location.get("section") is None
                    or isinstance(location.get("section"), str)
                )
            )
            node_type = node.get("node_type")
            if node_type in GRAPH_NODE_TYPES:
                node_ordinals[node_type] += 1
                expected_node_id = _stable_id(
                    str(metadata.get("source_sha256") if isinstance(metadata, dict) else ""),
                    node_type,
                    location.get("line") if isinstance(location, dict) else None,
                    node.get("text") if isinstance(node.get("text"), str) else "",
                    node_ordinals[node_type],
                )
            else:
                expected_node_id = None
            node_valid = (
                set(node) == GRAPH_NODE_FIELDS
                and isinstance(node.get("text"), str)
                and bool(node.get("text").strip())
                and location_valid
                and isinstance(node.get("extraction_method"), str)
                and bool(node.get("extraction_method").strip())
                and isinstance(node.get("metadata"), dict)
                and node.get("node_type") in GRAPH_NODE_TYPES
                and isinstance(expected_node_id, str)
                and node_id == expected_node_id
            )
            if not node_valid:
                invalid_node_schema.append(index)
        if node.get("node_type") not in GRAPH_NODE_TYPES:
            invalid_node_types.append(index)
        if node.get("status") not in GRAPH_NODE_STATUSES:
            invalid_node_statuses.append(index)

    duplicate_ids = sorted(node_id for node_id, count in Counter(ids).items() if count > 1)
    known = set(ids)
    node_types_by_id = {
        node["node_id"]: node.get("node_type")
        for node in node_records
    }

    if not isinstance(edges, list):
        edges = []
        invalid_edges.append(-1)
    valid_edges: list[dict] = []
    edge_ids: list[str] = []
    dangling: list[str] = []
    for index, edge in enumerate(edges):
        if not isinstance(edge, dict):
            invalid_edges.append(index)
            continue
        edge_id = edge.get("edge_id")
        source = edge.get("source")
        target = edge.get("target")
        if any(not isinstance(value, str) or not value.strip()
               for value in (edge_id, source, target)):
            invalid_edges.append(index)
            continue
        edge_ids.append(edge_id)
        valid_edges.append(edge)
        if strict_objects:
            if (
                set(edge) != GRAPH_EDGE_FIELDS
                or not isinstance(edge.get("relation"), str)
                or not isinstance(edge.get("status"), str)
                or not isinstance(edge.get("metadata"), dict)
            ):
                invalid_edge_schema.append(index)
        if source not in known or target not in known:
            dangling.append(edge_id)
        relation = edge.get("relation")
        if relation not in GRAPH_EDGE_RELATIONS:
            invalid_edge_relations.append(index)
        else:
            expected_edge_id = _edge_id(source, target, relation)
            if edge_id != expected_edge_id:
                invalid_edge_ids.append(index)
            endpoint_types = EDGE_ENDPOINT_TYPES[relation]
            source_node_type = node_types_by_id.get(source)
            target_node_type = node_types_by_id.get(target)
            if (
                source in node_types_by_id
                and target in node_types_by_id
                and (
                    not isinstance(source_node_type, str)
                    or source_node_type not in endpoint_types[0]
                    or not isinstance(target_node_type, str)
                    or target_node_type not in endpoint_types[1]
                )
            ):
                invalid_edge_endpoint_types.append(index)
        if edge.get("status") not in GRAPH_EDGE_STATUSES:
            invalid_edge_statuses.append(index)

    duplicate_edge_ids = sorted(
        edge_id for edge_id, count in Counter(edge_ids).items() if count > 1
    )

    adjacency: dict[str, list[str]] = {node_id: [] for node_id in known}
    indegree: dict[str, int] = {node_id: 0 for node_id in known}
    for edge in valid_edges:
        source, target = edge["source"], edge["target"]
        if source in known and target in known:
            adjacency[source].append(target)
            indegree[target] += 1

    queue = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        current = queue.pop()
        visited += 1
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
    cycle_present = visited != len(known)

    inference_ids = {
        node["node_id"] for node in node_records
        if node.get("node_type") == "inference"
    }
    claim_ids = {
        node["node_id"] for node in node_records
        if node.get("node_type") == "claim"
    }
    claims_by_inference: dict[str, list[str]] = {}
    inferences_by_claim: dict[str, list[str]] = {}
    for edge in valid_edges:
        if edge.get("relation") == "yields_claim":
            claims_by_inference.setdefault(edge["source"], []).append(edge["target"])
            inferences_by_claim.setdefault(edge["target"], []).append(edge["source"])
    invalid_claim_inference_links = sorted(
        [f"inference:{node_id}" for node_id in inference_ids
         if len(claims_by_inference.get(node_id, [])) != 1]
        + [f"claim:{node_id}" for node_id in claim_ids
           if len(inferences_by_claim.get(node_id, [])) != 1]
    )
    invalid_graph_content = []
    if not node_records:
        invalid_graph_content.append("empty_nodes")
    if not edges:
        invalid_graph_content.append("empty_edges")
    evidence_inputs = {
        edge["target"] for edge in valid_edges
        if edge.get("relation") == "lexical_candidate_basis"
        and edge["source"] in known and edge["target"] in known
        and node_types_by_id.get(edge["source"]) == "evidence"
        and node_types_by_id.get(edge["target"]) == "inference"
    }
    missing_evidence = sorted(inference_ids - evidence_inputs)
    failed = bool(
        invalid_nodes or invalid_node_types or invalid_node_statuses or invalid_node_schema
        or invalid_edges or invalid_edge_schema or invalid_schema_metadata
        or invalid_edge_relations or invalid_edge_statuses
        or invalid_edge_ids or invalid_edge_endpoint_types
        or duplicate_ids or duplicate_edge_ids or dangling or cycle_present
        or invalid_graph_content or invalid_claim_inference_links
    )
    return {
        "status": "FAIL" if failed else "PASS",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "invalid_node_entries": invalid_nodes,
        "invalid_schema_metadata": invalid_schema_metadata,
        "invalid_node_types": invalid_node_types,
        "invalid_node_statuses": invalid_node_statuses,
        "invalid_node_schema": invalid_node_schema,
        "invalid_edge_entries": invalid_edges,
        "invalid_edge_schema": invalid_edge_schema,
        "invalid_edge_relations": invalid_edge_relations,
        "invalid_edge_statuses": invalid_edge_statuses,
        "invalid_edge_ids": invalid_edge_ids,
        "invalid_edge_endpoint_types": invalid_edge_endpoint_types,
        "duplicate_node_ids": duplicate_ids,
        "duplicate_edge_ids": duplicate_edge_ids,
        "dangling_edges": dangling,
        "dependency_cycle_detected": cycle_present,
        "invalid_graph_content": invalid_graph_content,
        "invalid_claim_inference_links": invalid_claim_inference_links,
        "inferences_without_lexical_evidence": missing_evidence,
        "limitations": [
            "Graph integrity validation checks schema, references and structure, not truth or semantic validity.",
            "An inference without a lexical evidence edge may still be supported by paraphrased or external evidence.",
        ],
    }
