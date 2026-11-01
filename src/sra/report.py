from sra.models import AuditReport


def to_markdown(report: AuditReport) -> str:
    lines = [
        "# Scientific Reasoning Audit", "",
        f"- Source: {report.source}",
        f"- SHA-256: {report.sha256}",
        f"- Detected sections: {', '.join(report.section_names) or 'None'}",
        "", "## Screening findings", "",
    ]
    if not report.findings:
        lines.append("No configured screening signals were triggered. This does not establish validity.")
    for item in report.findings:
        lines.extend([f"### [{item.severity.upper()}] {item.title}", "", item.message])
        for excerpt in item.evidence:
            lines.append(f"> {excerpt}")
        lines.append("")
    lines.extend(["## Claim-evidence candidates", ""])
    if not report.claim_evidence_candidates:
        lines.append("No matching claim sentences were found by the current extraction rules.")
    for item in report.claim_evidence_candidates:
        lines.extend([
            f"Claim: {item.claim}", "",
            f"Candidate support: {item.candidate_support or 'No lexical candidate found'}",
            f"Token overlap: {item.lexical_overlap:.3f}",
            f"Interpretation: {item.interpretation}", "",
        ])
    lines.extend(["## Scope and limitations", "", report.scope_note, ""])
    return "\n".join(lines)
