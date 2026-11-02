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


def graph_fingerprint(graph: dict[str, Any]) -> str:
    payload = {
        "schema_version": graph.get("schema_version"),
        "source_sha256": graph.get("source_sha256"),
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
        "schema_version": "1.1",
        "source_sha256": document.sha256,
        "node_types": [
            "method", "evidence", "assumption", "assumption_gap",
            "limitation", "inference", "claim", "document_context",
        ],
        "edge_relations": [
            "method_context_candidate", "method_document_context", "limitation_document_context",
            "lexical_candidate_basis", "yields_claim",
            "assumption_candidate_required_for", "assumption_review_required",
            "qualifies_claim_candidate", "possible_contradiction_candidate",
            "document_context_membership",
        ],
        "nodes": nodes,
        "edges": edges,
        "validation": validate_reasoning_graph(nodes, edges),
    }
    graph["graph_fingerprint"] = graph_fingerprint(graph)
    return graph


def validate_reasoning_graph(nodes: list[dict], edges: list[dict]) -> dict[str, Any]:
    invalid_nodes: list[int] = []
    invalid_edges: list[int] = []
    ids: list[str] = []
    node_records: list[dict] = []

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

    duplicate_ids = sorted(node_id for node_id, count in Counter(ids).items() if count > 1)
    known = set(ids)

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
        if source not in known or target not in known:
            dangling.append(edge_id)

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
    evidence_inputs = {
        edge["target"] for edge in valid_edges
        if edge.get("relation") == "lexical_candidate_basis"
        and edge["source"] in known and edge["target"] in known
    }
    missing_evidence = sorted(inference_ids - evidence_inputs)
    failed = bool(
        invalid_nodes or invalid_edges or duplicate_ids or duplicate_edge_ids
        or dangling or cycle_present
    )
    return {
        "status": "FAIL" if failed else "PASS",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "invalid_node_entries": invalid_nodes,
        "invalid_edge_entries": invalid_edges,
        "duplicate_node_ids": duplicate_ids,
        "duplicate_edge_ids": duplicate_edge_ids,
        "dangling_edges": dangling,
        "dependency_cycle_detected": cycle_present,
        "inferences_without_lexical_evidence": missing_evidence,
        "limitations": [
            "Graph integrity validation checks structure, not truth or semantic validity.",
            "An inference without a lexical evidence edge may still be supported by paraphrased or external evidence.",
        ],
    }
