"""Human-readable unified review; retain module-specific evidence and limits."""
import json
import re

from sra.paper_review import paper_review_markdown
from sra.models import AuditReport, ClaimEvidenceCandidate, Finding
from sra.report import _safe_md, to_markdown
from sra.writing import writing_report_markdown
from sra.logic_report import logic_markdown
from sra.toolkit_report import toolkit_markdown


def review_markdown(report: dict) -> str:
    lines = ["# Cross-disciplinary scientific review", "",
             f"**Source:** {_safe_md(report['source'])}",
             f"**SHA-256:** {report['source_sha256']}",
             f"**Execution:** {report['execution_status']}",
             report["execution_scope"], "",
             f"**Declared study type:** {_safe_md(report['configuration']['study_type'])}",
             f"**Applicability review required:** {report['applicability']['review_required']}",
             "", "## Module execution", ""]
    for name, module in report["modules"].items():
        lines.append(f"- **{_safe_md(name)}:** {module['status']}" +
                     (f" — {_safe_md(module['reason'])}" if module["reason"] else ""))
    lines.extend(["", "## Coverage gaps", ""])
    lines.extend(f"- {_safe_md(gap)}" for gap in report["coverage_gaps"])
    lines.extend(["", "## Excluded findings and applicability", ""])
    for item in report["excluded_findings"]:
        lines.append(f"- **{_safe_md(item['finding']['check_id'])}:** {_safe_md(item['reason'])}")
    if not report["excluded_findings"]:
        lines.append("No findings were excluded by the declared study type.")
    for name, module in report["modules"].items():
        if module["result"] is None:
            continue
        result = module["result"]
        lines.extend(["", f"## {_safe_md(name)} details", ""])
        if name == "reasoning":
            typed = AuditReport(**{
                **result, "findings": [Finding(**item) for item in result["findings"]],
                "claim_evidence_candidates": [ClaimEvidenceCandidate(**item) for item in result["claim_evidence_candidates"]],
            })
            lines.append(to_markdown(typed))
        elif name == "writing":
            lines.append(writing_report_markdown(result))
        elif name == "model":
            lines.append(paper_review_markdown(result))
        elif name == "logic":
            lines.append(logic_markdown(result))
        elif name == "toolkit":
            lines.append(toolkit_markdown(result))
        elif name=='preparation':
            from sra.inspection import inspection_markdown
            lines.append(inspection_markdown(result))
        elif name.startswith("discipline:"):
            lines.append(_safe_md(result["guidance"]))
            for item in result["items"]:
                lines.extend(["", f"### {_safe_md(item['review_question'])}",
                              f"- Text screening: {_safe_md(item['status'])}",
                              "- Expert assessment: required"])
                for evidence in item["evidence"]:
                    lines.append(f"> Line {evidence['line']} ({_safe_md(evidence['section'])}): {_safe_md(evidence['excerpt'])}")
            lines.extend(f"- {_safe_md(limit)}" for limit in result["limitations"])
        elif name == "citations":
            lines.extend(["### DOI metadata", f"- Identifiers found: {result['found_count']}",
                          f"- Included in this bounded scan: {result['checked_count']}",
                          f"- Truncated: {result['truncated']}",
                          f"- External lookup requested: {result['online_lookup']}"])
            for item in result["results"]:
                lines.append(f"- {_safe_md(item['doi'])}: {_safe_md(item['status'])}")
            lines.extend(f"- {_safe_md(limit)}" for limit in result["limitations"])
        else:
            # A fence longer than every run in the data keeps even malicious
            # fence/HTML content inert while preserving readable JSON layout.
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
            fence = "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", serialized)), default=0))
            lines.append(f"{fence}json\n{serialized}\n{fence}")
    lines.extend(["", "## Interpretation limits", ""])
    lines.extend(f"- {_safe_md(item)}" for item in report["limitations"])
    return "\n".join(lines) + "\n"
