import html

from sra.models import AuditReport


def _safe_md(value: object) -> str:
    """Render external/user text as inert Markdown, without raw HTML or links."""
    text = html.escape(str(value).replace("\r", " ").replace("\n", " "), quote=False)
    for marker in ("\\", "`", "*", "_", "[", "]", "#"):
        text = text.replace(marker, "\\" + marker)
    return text


def to_markdown(report: AuditReport) -> str:
    manifest = report.reproducibility_manifest
    graph = report.reasoning_graph
    lines = ["# Scientific Reasoning Audit", "", f"- Source: {_safe_md(report.source)}", f"- SHA-256: {report.sha256}", f"- Detected sections: {', '.join(_safe_md(n) for n in report.section_names) or 'None'}", f"- Audit version: {manifest.get('auditor_version', 'unknown')}", f"- Environment fingerprint: {manifest.get('environment_fingerprint', 'unknown')}", "", "## Screening and reasoning findings", ""]
    if not report.findings:
        lines.append("No configured screening signals were triggered. This does not establish validity.")
    for item in report.findings:
        lines.extend([f"### [{item.severity.upper()}] {item.title}", "", item.message])
        for index, excerpt in enumerate(item.evidence):
            location = item.evidence_locations[index] if index < len(item.evidence_locations) else {}
            line = location.get("line")
            section = location.get("section")
            prefix = f"Line {line}" if line is not None else "Evidence"
            if section:
                prefix += f" ({_safe_md(section)})"
            lines.append(f"> **{prefix}:** {_safe_md(excerpt)}")
        lines.append("")

    lines.extend(["## Claim–evidence candidates", ""])
    if not report.claim_evidence_candidates:
        lines.append("No matching Discussion/Conclusion claim sentences were found by the current extraction rules.")
    for item in report.claim_evidence_candidates:
        claim_location = f"line {item.claim_line}" if item.claim_line else "line unknown"
        if item.claim_section:
            claim_location += f" — {_safe_md(item.claim_section)}"
        support_location = f"line {item.support_line}" if item.support_line else "not located"
        if item.support_section:
            support_location += f" — {_safe_md(item.support_section)}"
        lines.extend([f"**Claim ({claim_location}):** {_safe_md(item.claim)}", "", f"**Candidate result evidence ({support_location}):** {_safe_md(item.candidate_support or 'No lexical candidate found')}", f"- Token overlap (Jaccard): {item.lexical_overlap:.3f}", f"- Match status: {item.match_status}", f"- Interpretation: {item.interpretation}", ""])

    lines.extend(["## Reasoning graph", ""])
    validation = graph.get("validation", {})
    lines.append(f"- Nodes: {validation.get('node_count', 0)}; edges: {validation.get('edge_count', 0)}")
    lines.append(f"- Structural graph validation: {validation.get('status', 'unknown')}")
    lines.append(f"- Graph fingerprint: {graph.get('graph_fingerprint', 'unknown')}")
    lines.append("")
    for node in graph.get("nodes", []):
        loc = node.get("source_location", {})
        where = f"line {loc.get('line')}" if loc.get("line") else "no line"
        if loc.get("section"):
            where += f", {_safe_md(loc['section'])}"
        lines.append(f"- **{node['node_type']}** {node['node_id']} ({where}; {node.get('status')}) — {_safe_md(node['text'])}")
    lines.extend(["", "### Graph relations", ""])
    for edge in graph.get("edges", []):
        lines.append(f"- {edge['source']} —{edge['relation']}→ {edge['target']} ({edge['status']})")
    if validation.get("inferences_without_lexical_evidence"):
        lines.extend(["", "Inferences without a lexical evidence edge:"])
        lines.extend([f"- {item}" for item in validation["inferences_without_lexical_evidence"]])
        lines.append("These may still have paraphrased or external evidence.")

    lines.extend(["", "## Existing reasoning signals", ""])
    for relation in report.reasoning_map:
        lines.append(f"- **{relation.get('relation', 'relation')}** — {relation.get('status', 'unknown')}")
        if relation.get("claim"):
            lines.append(f"  - Claim: {_safe_md(relation['claim'])}")
        if relation.get("results_sentence"):
            lines.append(f"  - Results: {_safe_md(relation['results_sentence'])}")
            lines.append(f"  - {_safe_md(relation.get('conclusion_section') or 'Discussion/Conclusion')}: {_safe_md(relation.get('conclusion_sentence', ''))}")
        if relation.get("note"):
            lines.append(f"  - {_safe_md(relation['note'])}")

    if report.semantic_review:
        semantic = report.semantic_review
        lines.extend(["", "## External semantic review", "", f"- Import status: {semantic.get('status')}", f"- Assessments structurally validated: {semantic.get('assessment_count', 0)}", "- Structural validation does not prove the semantic judgment is correct."])
        for item in semantic.get("validated_assessments", []):
            confidence = item.get("confidence")
            confidence_text = (
                f"{confidence:.2f}"
                if isinstance(confidence, (int, float)) and not isinstance(confidence, bool)
                else "invalid"
            )
            lines.append(f"- **{item.get('relation', 'unknown')}** (confidence {confidence_text}) — {_safe_md(item.get('rationale', ''))}")
            if item.get("missing_assumptions"):
                lines.append(f"  - Missing assumptions: {'; '.join(_safe_md(x) for x in item['missing_assumptions'])}")
            selected_ids = item.get("reviewer_selected_evidence_node_ids", [])
            if selected_ids:
                lines.append(
                    "  - Reviewer-selected evidence IDs (provenance checked; relevance not verified): "
                    + "; ".join(selected_ids)
                )
        for error in semantic.get("errors", []):
            lines.append(f"- Validation error: {_safe_md(error)}")

    lines.extend(["", "## Reproducibility manifest", "", f"- Manifest schema: {manifest.get('manifest_schema_version', 'unknown')}", f"- Generated (UTC): {manifest.get('generated_at_utc', 'unknown')}", f"- Python: {manifest.get('runtime', {}).get('python_version', 'unknown')}", f"- Platform: {manifest.get('runtime', {}).get('platform', 'unknown')}", f"- Parser: {manifest.get('parser', {}).get('backend', 'unknown')}", f"- Ruleset: {manifest.get('ruleset_version', 'unknown')}", f"- Configuration SHA-256: {manifest.get('configuration_sha256', 'unknown')}", f"- Source-code revision: {manifest.get('source_code_revision') or 'not captured by this runtime'}", f"- Source-code SHA-256: {manifest.get('source_code_sha256') or 'not captured'}", "", "## Scope and limitations", "", report.scope_note, ""])
    return "\n".join(lines)
