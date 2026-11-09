"""Read the numbers printed in a table row as column=value statements.

Reported statistics usually live in a table, and the audit's rules compare
prose. A table row such as ``A   12   4.1   3.2   0.03`` under the header
``Group n mean SD p`` says exactly what ``SD = 3.2`` and ``p = 0.03`` would say,
so the row is turned into statements the existing checks can read.

Deliberately narrow: only columns whose headings name a statistic the audit
understands, only rows whose cell count matches the header, and only when the
row actually carries a number in that column. A table the parser does not
understand yields nothing rather than a guess.
"""

from __future__ import annotations

import re

from sra.document import without_fenced_code

#: Column headings the audit knows how to read, mapped to the statement key.
COLUMN_KEYS = {
    "p": "p",
    "p value": "p",
    "p-value": "p",
    "pval": "p",
    "sd": "SD",
    "s.d.": "SD",
    "std": "SD",
    "std dev": "SD",
    "se": "SE",
    "s.e.": "SE",
    "sem": "SE",
    "n": "n",
    "no.": "n",
}

#: A table row is at least two runs of text separated by two or more spaces, the
#: shape layout-aware extraction produces for aligned columns.
CELL_SPLIT = re.compile(r"\s{2,}")

#: A cell that is a plain number, with the minus and decimal variants printers use.
NUMBER = re.compile(r"^[-\u2212]?\s*\d+(?:[.\u00b7]\d+)?$")


def _cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped:
        return []
    return [cell.strip() for cell in CELL_SPLIT.split(stripped) if cell.strip()]


def table_statements(text: str) -> list[tuple[str, int, str, str]]:
    """Return ``(statement, line, column_heading, value)`` for table numbers.

    ``statement`` is ``"<column> = <value>"``, ready for the sentence rules.
    """
    statements: list[tuple[str, int, str, str]] = []
    header: list[str] | None = None
    header_keys: list[str | None] = []
    for line_number, line in enumerate(without_fenced_code(text).splitlines(), start=1):
        cells = _cells(line)
        if len(cells) < 2:
            header = None
            header_keys = []
            continue
        keys = [COLUMN_KEYS.get(cell.lower().strip(".:")) for cell in cells]
        if sum(1 for key in keys if key) >= 2:
            header = list(cells)
            header_keys = keys
            continue
        if header is None or len(cells) != len(header):
            continue
        for heading, cell, key in zip(header, cells, header_keys):
            if not key or not NUMBER.match(cell):
                continue
            value = cell.replace("\u2212", "-").replace("\u00b7", ".")
            statements.append((f"{key} = {value}", line_number, heading, value))
    return statements

def table_findings(text: str) -> list:
    """Run the plausibility rules over the numbers read out of tables."""
    from sra.models import Finding
    from sra.statistical_consistency import impossible_dispersion, impossible_p_value

    findings: list[Finding] = []
    for statement, line_number, heading, _value in table_statements(text):
        for finding in impossible_p_value(statement + ".") + impossible_dispersion(statement + "."):
            finding.evidence = [f"{statement} (table column {heading!r})"]
            finding.evidence_locations = [
                {"line": line_number, "kind": "table_cell", "column": heading}
            ]
            findings.append(finding)
    return findings
