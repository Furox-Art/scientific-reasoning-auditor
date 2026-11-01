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


HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def _split_sections(text: str) -> dict[str, str]:
    matches = list(HEADING.finditer(text))
    if not matches:
        return {"full_text": text.strip()}
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1).strip()] = text[start:end].strip()
    preamble = text[:matches[0].start()].strip()
    if preamble:
        sections["preamble"] = preamble
    return sections


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
    elif suffix in {".md", ".markdown", ".txt"}:
        text = raw.decode("utf-8-sig")
    else:
        raise ValueError("Supported formats: .md, .markdown, .txt, .pdf")
    if not text.strip():
        raise ValueError("No extractable text found in the input document.")
    return ParsedDocument(
        source=file_path.name,
        text=text,
        sha256=hashlib.sha256(raw).hexdigest(),
        sections=_split_sections(text),
    )
