import hashlib
import re
import tempfile
from io import BytesIO
from dataclasses import dataclass, field
from pathlib import Path

MAX_DOCUMENT_BYTES = 32 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_EXTRACTED_TEXT_CHARS = 4_000_000


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
    extraction_details: dict = field(default_factory=dict)


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


def load_document(
    path: str | Path, *, pdf_ocr_mode: str = "off", ocr_languages: str = "eng",
) -> ParsedDocument:
    from sra.pdf_visual import validate_ocr_settings

    validate_ocr_settings(pdf_ocr_mode, ocr_languages)
    extraction_details: dict = {}
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"Input file not found: {file_path}")
    # Bounded read avoids loading a hostile or accidental multi-gigabyte file
    # before the size check (stat-only preflights are vulnerable to file races).
    with file_path.open("rb") as stream:
        raw = stream.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("Document exceeds the 32 MiB input limit.")
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF support is optional. Install it with: pip install -e '[pdf]'"
            ) from exc
        from sra.pdf_visual import MAX_OCR_PAGES, ocr_pdf_page

        # Use the exact bounded bytes whose digest is recorded. Do not open the
        # user-controlled PDF path a second time when extracting the text layer.
        reader = PdfReader(BytesIO(raw))
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            raise ValueError("PDF exceeds the 500-page processing limit.")
        if pdf_ocr_mode == "all" and page_count > MAX_OCR_PAGES:
            raise ValueError("PDF exceeds the 100-page OCR limit; no pages were silently skipped.")
        pages: list[str] = []
        page_information: list[dict] = []
        no_text_pages: list[int] = []
        ocr_pages: list[int] = []
        extracted_characters = 0
        layout_used = False
        with tempfile.TemporaryDirectory(prefix="sra-pdf-snapshot-") as folder:
            # OCR operates on a private, immutable-copy snapshot rather than the
            # original path, whose bytes could change after the source hash.
            snapshot = Path(folder) / "source.pdf"
            if pdf_ocr_mode != "off":
                snapshot.write_bytes(raw)
            for number, page in enumerate(reader.pages, 1):
                try:
                    native = page.extract_text(extraction_mode="layout") or ""
                    layout_used = True
                except (TypeError, ValueError):
                    native = page.extract_text() or ""
                text_for_page = native
                ocr_chars = 0
                method = "native"
                # Pages can contain raster text even when a digital heading is available.
                # Enumerate embedded images, and do not equate native text with full page coverage.
                try:
                    embedded_image_count = len(getattr(page, "images", ()))
                except (AttributeError, TypeError, ValueError) as exc:
                    if pdf_ocr_mode == "missing":
                        raise ValueError("PDF page image inventory could not be inspected.") from exc
                    embedded_image_count = 0
                should_ocr = pdf_ocr_mode == "all" or (
                    pdf_ocr_mode == "missing" and (
                        len("".join(native.split())) < 20 or embedded_image_count > 0
                    )
                )
                if should_ocr:
                    if len(ocr_pages) >= MAX_OCR_PAGES:
                        raise ValueError("PDF exceeds the 100-page OCR limit; no pages were silently skipped.")
                    scanned = ocr_pdf_page(snapshot, number, languages=ocr_languages)
                    ocr_pages.append(number)
                    ocr_chars = len(scanned)
                    if scanned:
                        if native.strip() and embedded_image_count:
                            # Keep the original digital text and add only OCR lines absent
                            # from the native layer; this remains heuristic, not proof of
                            # complete graphical semantics.
                            def normalized(line: str) -> str:
                                # Preserve scientific operators, signs and units.
                                # Deduplicate only changes in case and whitespace,
                                # never differences such as p<0.05 vs p>0.05.
                                return " ".join(line.casefold().split())

                            known = {normalized(line) for line in native.splitlines()}
                            additional = [
                                line for line in scanned.splitlines()
                                if normalized(line) and normalized(line) not in known
                            ]
                            if additional:
                                text_for_page = native + "\n\n[OCR image text]\n" + "\n".join(additional)
                                method = "native+tesseract"
                            else:
                                method = "native+ocr_checked"
                        else:
                            text_for_page, method = scanned, "tesseract"
                if not text_for_page.strip():
                    no_text_pages.append(number)
                    method = "no_text"
                pages.append(text_for_page)
                page_information.append({
                    "page": number,
                    "method": method,
                    "native_characters": len(native),
                    "ocr_characters": ocr_chars,
                    "embedded_image_count": embedded_image_count,
                    "ocr_attempted": number in ocr_pages,
                    "text_sha256": hashlib.sha256(text_for_page.encode("utf-8")).hexdigest(),
                    "needs_visual_review": True,
                })
                extracted_characters += len(text_for_page)
                if extracted_characters > MAX_EXTRACTED_TEXT_CHARS:
                    raise ValueError("PDF extracted text exceeds the 4,000,000-character limit.")
        offset = 0
        for index, page_text in enumerate(pages):
            page_information[index]["start_char"] = offset
            offset += len(page_text)
            page_information[index]["end_char"] = offset
            if index + 1 < len(pages):
                offset += 2  # separator inserted by the join below
        text = "\n\n".join(pages)
        parser_backend = "pypdf-layout" if layout_used else "pypdf"
        if ocr_pages:
            parser_backend += "+tesseract"
        extraction_details = {
            "pdf_page_count": page_count,
            "ocr_mode": pdf_ocr_mode,
            "ocr_languages": ocr_languages if ocr_pages else None,
            "ocr_pages": ocr_pages,
            "pages_without_extractable_text": no_text_pages,
            "physical_page_text_coverage": (
                "all_pages_with_text" if not no_text_pages else "incomplete"
            ),
            "page_records": page_information,
            "image_and_chart_semantics_verified": False,
        }
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
    if len(text) > MAX_EXTRACTED_TEXT_CHARS:
        raise ValueError("Document extracted text exceeds the 4,000,000-character limit.")
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
        extraction_details=extraction_details,
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
