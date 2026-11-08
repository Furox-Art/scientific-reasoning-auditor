import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ParsedDocument:
    source: str
    text: str
    sha256: str
    sections: dict[str, str]
    section_start_lines: dict[str, int]
    input_format: str
    source_size_bytes: int
    parser_backend: str


HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$")
FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})")
PLAIN_HEADING_ALIASES = {
    "abstract", "introduction", "background", "methods", "method", "methodology",
    "materials and methods", "methods and materials", "results", "findings",
    "results and discussion", "discussion", "conclusion", "conclusions",
    "general discussion", "limitations", "study limitations", "references",
    "bibliography", "literature cited", "özet", "giriş", "yöntem", "yöntemler",
    "materyal ve metot", "gereç ve yöntem", "bulgular", "sonuçlar", "tartışma",
    "sonuç", "sonuç ve tartışma", "sınırlılıklar", "çalışmanın sınırlılıkları",
    "kaynakça",
}
PLAIN_PREFIX = re.compile(r"^(?:(?:\d+(?:\.\d+)*|[IVXLC]+)[.)]?\s+)?(.+?)\s*[:.]?$", re.I)


def without_fenced_code(text: str) -> str:
    """Remove Markdown fenced-code contents while retaining line breaks for locations."""
    output: list[str] = []
    fence_char: str | None = None
    fence_length = 0
    for line in text.splitlines(keepends=True):
        line_without_ending = line.rstrip("\r\n")
        fence = FENCE_OPEN.match(line_without_ending)
        if fence:
            marker = fence.group(1)
            if fence_char is None:
                fence_char, fence_length = marker[0], len(marker)
            elif (
                marker[0] == fence_char
                and len(marker) >= fence_length
                and not line_without_ending[fence.end(1):].strip()
            ):
                fence_char, fence_length = None, 0
            output.append("\n" if line.endswith(("\n", "\r")) else "")
        elif fence_char is not None:
            output.append("\n" if line.endswith(("\n", "\r")) else "")
        else:
            output.append(line)
    return "".join(output)

def _heading_records(text: str, allow_plain: bool) -> list[tuple[str, int, int]]:
    """Return (heading, content_start_offset, heading_start_offset), excluding fenced code."""
    records: list[tuple[str, int, int]] = []
    offset = 0
    fence_char: str | None = None
    fence_length = 0
    lines = text.splitlines(keepends=True)

    for line in lines:
        line_without_ending = line.rstrip("\r\n")
        fence = FENCE_OPEN.match(line_without_ending)
        if fence:
            marker = fence.group(1)
            if fence_char is None:
                fence_char, fence_length = marker[0], len(marker)
            elif (
                marker[0] == fence_char
                and len(marker) >= fence_length
                and not line_without_ending[fence.end(1):].strip()
            ):
                fence_char, fence_length = None, 0
            offset += len(line)
            continue

        if fence_char is None:
            heading_match = HEADING.match(line_without_ending)
            if heading_match:
                records.append((heading_match.group(1).strip(), offset + len(line), offset))
            elif allow_plain and line_without_ending.strip():
                candidate = PLAIN_PREFIX.match(line_without_ending.strip())
                if candidate:
                    label = candidate.group(1).strip().lower()
                    if label in PLAIN_HEADING_ALIASES:
                        records.append((candidate.group(1).strip(), offset + len(line), offset))
        offset += len(line)

    return records


def _split_sections(text: str, allow_plain: bool = False) -> tuple[dict[str, str], dict[str, int]]:
    matches = _heading_records(text, allow_plain=allow_plain)
    # Include contents of noncanonical nested Markdown subheadings in the
    # enclosing Results/Methods/etc. section instead of hiding evidence.
    # Standalone headings always start a new logical section.
    filtered = []
    current_root_level = None
    current_root_canonical = False
    for record in matches:
        heading, _, start = record
        line = text[start:text.find("\n", start) if "\n" in text[start:] else len(text)]
        markdown = HEADING.match(line.rstrip("\r"))
        level = len(markdown.group(0).lstrip().split(" ", 1)[0]) if markdown else 0
        normalized = PLAIN_PREFIX.match(heading)
        canonical = bool(normalized and normalized.group(1).lower().strip() in PLAIN_HEADING_ALIASES)
        if (level and current_root_level is not None and
                level > current_root_level and current_root_canonical and not canonical):
            continue
        filtered.append(record)
        current_root_level = level
        current_root_canonical = canonical
    matches = filtered
    if not matches:
        return {"full_text": without_fenced_code(text).strip()}, {"full_text": 1}

    sections: dict[str, str] = {}
    start_lines: dict[str, int] = {}
    occurrences: dict[str, int] = {}

    for index, (raw_name, content_start, heading_start) in enumerate(matches):
        occurrences[raw_name] = occurrences.get(raw_name, 0) + 1
        occurrence = occurrences[raw_name]
        name = raw_name if occurrence == 1 else f"{raw_name} ({occurrence})"
        while name in sections:
            occurrence += 1
            name = f"{raw_name} ({occurrence})"
        occurrences[raw_name] = occurrence
        end = matches[index + 1][2] if index + 1 < len(matches) else len(text)
        raw_section = without_fenced_code(text[content_start:end])
        leading = len(raw_section) - len(raw_section.lstrip())
        sections[name] = raw_section.strip()
        # Raw fenced-code contents were replaced with line breaks. Their
        # original character lengths do NOT correspond to sanitized offsets.
        # Count preserved line breaks rather than adding sanitized lengths to
        # original source byte/character offsets.
        start_lines[name] = (
            text.count("\n", 0, content_start)
            + raw_section[:leading].count("\n")
            + 1
        )

    preamble = without_fenced_code(text[:matches[0][2]]).strip()
    if preamble:
        sections["preamble"] = preamble
        start_lines["preamble"] = 1
    return sections, start_lines


def load_document(path: str | Path) -> ParsedDocument:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"Input file not found: {file_path}")
    raw = file_path.read_bytes()
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF support is optional. Install it with: pip install -e '.[pdf]'"
            ) from exc
        reader = PdfReader(str(file_path))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        parser_backend = "pypdf"
    elif suffix in {".md", ".markdown", ".txt"}:
        text = raw.decode("utf-8-sig")
        # Normalise line endings once, here. Every consumer of the extracted text
        # (the reasoning graph, the semantic-review template, the CLI's own
        # review paths) has to hash the same characters, and those paths read the
        # file through text mode, which already collapses CRLF to LF. Without
        # this, a manuscript saved with Windows line endings produced an
        # extracted-text digest that no other reader of the same file could
        # match: audit then review-template on one file disagreed on Windows.
        # The exact bytes are still covered by ``sha256`` below.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        parser_backend = "python-utf8"
    else:
        raise ValueError("Supported formats: .md, .markdown, .txt, .pdf")
    if not text.strip():
        raise ValueError("No extractable text found in the input document.")
    # Prefer explicit Markdown headings. If none exist, conservatively recognize
    # standalone conventional headings in text/PDF extraction.
    sections, start_lines = _split_sections(text, allow_plain=True)
    return ParsedDocument(
        source=file_path.name,
        text=text,
        sha256=hashlib.sha256(raw).hexdigest(),
        sections=sections,
        section_start_lines=start_lines,
        input_format=suffix.lstrip("."),
        source_size_bytes=len(raw),
        parser_backend=parser_backend,
    )


def parse_document_text(
    text: str,
    *,
    sha256: str,
    source: str = "provided-text",
    input_format: str = "text",
    parser_backend: str = "python-utf8",
) -> ParsedDocument:
    """Recreate the parser view from text already extracted from a manuscript."""
    if not isinstance(text, str):
        raise TypeError("Manuscript source text must be a string.")
    sections, section_start_lines = _split_sections(text, allow_plain=True)
    return ParsedDocument(
        source=source,
        text=text,
        sha256=sha256,
        sections=sections,
        section_start_lines=section_start_lines,
        input_format=input_format,
        source_size_bytes=len(text.encode("utf-8")),
        parser_backend=parser_backend,
    )
