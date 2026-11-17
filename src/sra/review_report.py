"""Human-readable unified review; retain module-specific evidence and limits."""
import json
import re

from sra.paper_review import paper_review_markdown
from sra.models import AuditReport, ClaimEvidenceCandidate, Finding
from sra.report import _safe_md, to_markdown
from sra.writing import writing_report_markdown
from sra.logic_report import logic_markdown
from sra.toolkit_report import toolkit_markdown
from sra.criteria import criteria_markdown


def review_markdown(report: dict, *, style: str = "natural") -> str:
    """Render English prose without changing analysis or rewriting the manuscript.

    Natural reports shorten the coverage worksheet; technical reports retain its
    full procedures. Both retain module evidence, verdicts and interpretation limits.
    """
    if style not in ("natural", "technical"):
        raise ValueError("Report style must be natural or technical.")
    if style == "natural":
        return _natural_markdown(report)
    return _technical_markdown(report)


def _technical_markdown(report: dict) -> str:
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
    if 'criteria_matrix' in report:
        lines.extend(['', criteria_markdown(report['criteria_matrix'])])
    lines.extend(["", "## Coverage gaps", ""])
    lines.extend(f"- {_safe_md(gap)}" for gap in report["coverage_gaps"])
    lines.extend(["", "## Excluded findings and applicability", ""])
    for item in report["excluded_findings"]:
        lines.append(f"- **{_safe_md(item['finding']['check_id'])}:** {_safe_md(item['reason'])}")
    if not report["excluded_findings"]:
        lines.append("No findings were excluded by the declared study type.")
    lines.extend(_module_details(report))
    lines.extend(["", "## Interpretation limits", ""])
    lines.extend(f"- {_safe_md(item)}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def _module_details(report: dict) -> list[str]:
    lines = []
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
                if item.get('publication_status'):
                    publication=item['publication_status']
                    lines.append(f"  - Registered publication update status: {_safe_md(publication['publication_status'])}")
                    for update in publication['updates']:
                        lines.append(f"  - {_safe_md(update['direction'])}: {_safe_md(update['type'])} ({_safe_md(update['doi'])})")
            lines.extend(f"- {_safe_md(limit)}" for limit in result["limitations"])
        else:
            # A fence longer than every run in the data keeps even malicious
            # fence/HTML content inert while preserving readable JSON layout.
            serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
            fence = "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", serialized)), default=0))
            lines.append(f"{fence}json\n{serialized}\n{fence}")
    return lines


def _natural_markdown(report: dict) -> str:
    complete = report["execution_status"] == "complete"
    lines = ["# Scientific review", "",
             "Requested checks finished." if complete else "Some requested checks did not finish.",
             "This describes execution, not the scientific validity of the paper.", "",
             f"- **Source:** {_safe_md(report['source'])}",
             f"- **Source SHA-256:** {_safe_md(report['source_sha256'])}",
             f"- **Execution:** {_safe_md(report['execution_status'])}",
             "", _safe_md(report["execution_scope"]), "",
             f"- **Declared study type:** {_safe_md(report['configuration']['study_type'])}",
             f"- **Applicability review required:** {_safe_md(report['applicability']['review_required'])}",
             "", "## What ran", ""]
    explanations = {
        "completed": "Finished",
        "failed": "Failed",
        "unavailable": "Unavailable",
        "not_requested": "Not requested",
        "not_applicable": "Excluded by the declared study type",
    }
    groups = {}
    for name, module in report["modules"].items():
        groups.setdefault(module["status"], []).append(name)
    for status, names in groups.items():
        label = explanations.get(status, "Inspect this module's execution state")
        lines.append(f"- **{label}** ({_safe_md(status)}): " +
                     ", ".join(_safe_md(name) for name in names) + ".")
        for name in names:
            reason = report["modules"][name]["reason"]
            if reason:
                lines.append(f"  - **{_safe_md(name)}:** {_safe_md(reason)}")
    lines.extend(["", "## Coverage gaps", ""])
    lines.extend(f"- {_safe_md(gap.replace('_', ' '))}." for gap in report["coverage_gaps"])
    if "criteria_matrix" in report:
        matrix = report["criteria_matrix"]
        lines.extend(["", "## Scientific criteria coverage", "",
                      "All scientific verdicts remain NOT_ASSESSED. Finished checks do not establish that a criterion is satisfied.",
                      "Required evidence, procedures and evidence pointers are in the JSON report and the technical presentation.", "",
                      "| Criterion | Applicability | This run |",
                      "| --- | --- | --- |"])
        for row in matrix["criteria"]:
            cells = [_safe_md(row[key].replace("_", " ") if key != "title" else row[key]).replace("|", "&#124;") for key in
                     ("title", "applicability", "execution_status")]
            lines.append("| " + " | ".join(cells) + " |")
        lines.extend(["", f"- **Catalog SHA-256:** {_safe_md(matrix['catalog_sha256'])}",
                      f"- **Matrix SHA-256:** {_safe_md(matrix['matrix_sha256'])}"])
        lines.extend(f"- {_safe_md(limit)}" for limit in matrix["limitations"])
    lines.extend(["", "## Excluded findings", ""])
    for item in report["excluded_findings"]:
        lines.append(f"- **{_safe_md(item['finding']['check_id'])}:** {_safe_md(item['reason'])}")
    if not report["excluded_findings"]:
        lines.append("No findings were excluded by the declared study type.")
    lines.extend(["", "## Findings and check results", "",
                  "VERIFIED and REFUTED apply to supplied inputs and assumptions. UNDETERMINED means the check could not decide.",
                  "Text cues and model advice require review; neither establishes a scientific error."])
    lines.extend(_module_details(report))
    lines.extend(["", "## Interpretation limits", ""])
    lines.extend(f"- {_safe_md(item)}" for item in report["limitations"])
    return "\n".join(lines) + "\n"
