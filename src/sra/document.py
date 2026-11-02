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


HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def _split_sections(text: str) -> tuple[dict[str, str], dict[str, int]]:
    matches = list(HEADING.finditer(text))
    if not matches:
        return {"full_text": text.strip()}, {"full_text": 1}

    sections: dict[str, str] = {}
    start_lines: dict[str, int] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        raw_section = text[start:end]
        leading = len(raw_section) - len(raw_section.lstrip())
        sections[name] = raw_section.strip()
        start_lines[name] = text.count("\n", 0, start + leading) + 1
    preamble = text[:matches[0].start()].strip()
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
        parser_backend = "python-utf8"
    else:
        raise ValueError("Supported formats: .md, .markdown, .txt, .pdf")
    if not text.strip():
        raise ValueError("No extractable text found in the input document.")
    sections, start_lines = _split_sections(text)
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
