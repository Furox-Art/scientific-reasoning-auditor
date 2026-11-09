"""Build a two-column table PDF at test time, without a PDF writer dependency.

Word and LaTeX emit each table cell as its own positioned text object. Plain
extraction then reads such a table column by column (``Group A C n 12 10 ...``),
while layout-aware extraction reconstructs the rows. These helpers build that
layout so the extraction test can tell the two apart.
"""

from __future__ import annotations

from pathlib import Path

HEADER = ((60, "Group"), (150, "n"), (210, "mean"), (290, "SD"), (370, "p"))
ROWS = (
    ((60, "A"), (150, "12"), (210, "4.1"), (290, "3.2"), (370, "0.03")),
    ((60, "C"), (150, "10"), (210, "-0.4"), (290, "-1.2"), (370, "0.000")),
)


def _operator(x: int, y: int, text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /F1 10 Tf {x} {y} Td ({escaped}) Tj ET"


def table_pdf(path: Path) -> Path:
    """Write a one-page PDF whose only content is a four-article table."""
    operators = [
        _operator(60, 720, "# Methods"),
        _operator(60, 700, "Three groups were compared with t-tests."),
        _operator(60, 676, "# Results"),
    ]
    for y, cells in ((656, HEADER), (640, ROWS[0]), (624, ROWS[1])):
        for x, cell in cells:
            operators.append(_operator(x, y, cell))
    operators.append(_operator(60, 600, "# Conclusion"))
    operators.append(_operator(60, 580, "The treatment changed the outcome."))

    content = "\n".join(operators).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    start_xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n"
        f"{start_xref}\n%%EOF\n"
    ).encode()

    path.write_bytes(bytes(out))
    return path
