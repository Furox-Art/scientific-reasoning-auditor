from sra.models import AuditReport


def to_markdown(report: AuditReport) -> str:
    manifest = report.reproducibility_manifest
    lines = [
        "# Scientific Reasoning Audit",
        "",
        f"- Source: {report.source}",
        f"- SHA-256: {report.sha256}",
        f"- Detected sections: {', '.join(report.section_names) or 'None'}",
        f"- Audit version: {manifest.get('auditor_version', 'unknown')}",
        f"- Environment fingerprint: {manifest.get('environment_fingerprint', 'unknown')}",
        "",
        "## Screening and reasoning findings",
        "",
    ]
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
                prefix += f" ({section})"
            lines.append(f"> **{prefix}:** {excerpt}")
        lines.append("")

    lines.extend(["## Claim–evidence candidates", ""])
    if not report.claim_evidence_candidates:
        lines.append("No matching conclusion claim sentences were found by the current extraction rules.")
    for item in report.claim_evidence_candidates:
        claim_location = f"line {item.claim_line}" if item.claim_line else "line unknown"
        support_location = f"line {item.support_line}" if item.support_line else "not located"
        lines.extend([
            f"**Claim ({claim_location}):** {item.claim}",
            "",
            f"**Candidate result support ({support_location}):** {item.candidate_support or 'No lexical candidate found'}",
            f"- Token overlap (Jaccard): {item.lexical_overlap:.3f}",
            f"- Match status: {item.match_status}",
            f"- Interpretation: {item.interpretation}",
            "",
        ])

    lines.extend(["## Reasoning map", ""])
    if not report.reasoning_map:
        lines.append("No reasoning relations were extracted.")
    for relation in report.reasoning_map:
        lines.append(f"- **{relation.get('relation', 'relation')}** — {relation.get('status', 'unknown')}")
        if relation.get("claim"):
            lines.append(f"  - Claim: {relation['claim']}")
        if relation.get("results_sentence"):
            lines.append(f"  - Results: {relation['results_sentence']}")
            lines.append(f"  - Conclusion: {relation.get('conclusion_sentence', '')}")
        if relation.get("note"):
            lines.append(f"  - {relation['note']}")

    lines.extend(["", "## Reproducibility manifest", ""])
    lines.append(f"- Manifest schema: {manifest.get('manifest_schema_version', 'unknown')}")
    lines.append(f"- Generated (UTC): {manifest.get('generated_at_utc', 'unknown')}")
    lines.append(f"- Python: {manifest.get('runtime', {}).get('python_version', 'unknown')}")
    lines.append(f"- Platform: {manifest.get('runtime', {}).get('platform', 'unknown')}")
    lines.append(f"- Parser: {manifest.get('parser', {}).get('backend', 'unknown')}")
    lines.append(f"- Ruleset: {manifest.get('ruleset_version', 'unknown')}")
    lines.append(f"- Configuration SHA-256: {manifest.get('configuration_sha256', 'unknown')}")
    lines.append(f"- Source-code revision: {manifest.get('source_code_revision') or 'not captured by this runtime'}")
    lines.extend(["", "## Scope and limitations", "", report.scope_note, ""])
    return "\n".join(lines)
