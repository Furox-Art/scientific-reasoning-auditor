"""Readable separate findings; all user text is escaped."""
import json
from sra.report import _safe_md


def toolkit_markdown(report):
    lines = ["# Deterministic inspection toolkit", "", "## Findings for the user", "",
             "The manuscript is read-only. Findings are a separate report.",
             f"Execution: {report['execution_status']}",f"Source binding: {report['source_binding']['status']}",
             f"Report SHA-256: {report['report_sha256']}", ""]
    for row in report["checks"]:
        lines.extend([f"### {_safe_md(row['id'])}: {row['status']}",
                      f"Check: {_safe_md(row['kind'])}; backend: {_safe_md(row['backend'])} {_safe_md(row['backend_version'])}",
                      _safe_md(row["details"]["meaning"]), ""])
        for key,value in row["details"].items():
            if key != "meaning":
                lines.append(f"- {_safe_md(key)}: {_safe_md(json.dumps(value,ensure_ascii=False,allow_nan=False))}")
    lines.extend(["", "## Interpretation limits", ""])
    lines.extend(f"- {_safe_md(limit)}" for limit in report["limitations"])
    return "\n".join(lines)+"\n"
