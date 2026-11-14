"""Separate, source-located formal logic findings for the user."""
from sra.report import _safe_md

_REASONS = {
    "NEGATED_CLAIM_UNSATISFIABLE": "The assumptions leave no possible case where this claim is false.",
    "CLAIM_UNSATISFIABLE": "The assumptions leave no possible case where this claim is true.",
    "BOTH_POSSIBLE": "The claim can be either true or false under the supplied assumptions.",
    "INCONSISTENT_PREMISES": "The assumptions conflict; no claim is accepted from inconsistent premises.",
    "SOLVER_RESOURCE_LIMIT": "The bounded solver could not determine this result; it is not a proof.",
}


def logic_markdown(report: dict) -> str:
    lines = ["# Deterministic formal logic review", "",
             f"**Engine:** Z3 {_safe_md(report['engine']['version'])}",
             f"**Execution:** {report['execution_status']}",
             f"**Premises:** {report['premises']['status']}",
             f"**Source binding:** {report['source_binding']['status']}",
             f"**Report SHA-256:** {report['report_sha256']}",
             "", "Results are conditional on the supplied formulas and assumptions; the manuscript is unchanged.",
             "", "## Assumptions", ""]
    for item in report["assumptions"]:
        lines.append(f"- **{_safe_md(item['id'])}:** {_safe_md(item['expression'])}")
    lines.extend(["", "## Findings for the user", ""])
    for item in report["claims"]:
        lines.extend([f"### {_safe_md(item['id'])}: {item['status']}",
                      _safe_md(item["expression"]), _REASONS[item["reason"]], ""])
        source = item["source"]
        if source.get("quote"):
            lines.append(f"> Line {source.get('line') or 'not supplied'}: {_safe_md(source['quote'])}")
        lines.append("Basis: " + (", ".join(_safe_md(key) for key in item["basis_assumption_ids"]) or "no assumptions"))
    lines.extend(["", "## Scope and limits", ""])
    lines.extend(f"- {_safe_md(limit)}" for limit in report["limitations"])
    return "\n".join(lines) + "\n"
