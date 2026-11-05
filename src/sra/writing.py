"""Conservative, source-located academic-writing checks for supported manuscripts.

Checks are editorial prompts, never proof of citation validity or scientific truth.
No external requests, rewriting, language models, or manuscript modification.
"""
from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from sra.document import ParsedDocument, load_document
from sra.writing_style import style_review
from sra.discipline import reporting_cues, CHECKLISTS

_WORD = re.compile(r"\b[\w]+(?:['’\-][\w]+)*\b", re.UNICODE)
_NUMBERED_CITATION = re.compile(
    r"\[(\d{1,4}(?:\s*[-–]\s*\d{1,4})?(?:\s*[,;]\s*\d{1,4}(?:\s*[-–]\s*\d{1,4})?)*)\]"
)
_NUMBERED_REFERENCE = re.compile(r"^\s*(?:\[(\d{1,4})\]|(\d{1,4})[.)])\s+\S")
_AUTHOR_REFERENCE = re.compile(
    r"^\s*([A-ZÀ-ÖØ-Þ][\w'’\-]+)\s*,[^\n]{0,160}?\(\s*((?:19|20)\d{2}[a-z]?)\s*\)",
    re.IGNORECASE,
)
_PARENTHESES = re.compile(r"\(([^()\n]{1,180})\)")
_AUTHOR_PART = re.compile(
    r"^\s*([A-ZÀ-ÖØ-Þ][\w'’\-]+)(?:\s+et\s+al\.)?\s*,\s*((?:19|20)\d{2}[a-z]?)\s*$",
    re.IGNORECASE,
)
_NARRATIVE_AUTHOR = re.compile(
    r"\b([A-ZÀ-ÖØ-Þ][\w'’\-]+)(?:\s+et\s+al\.)?\s+\(\s*((?:19|20)\d{2}[a-z]?)\s*\)",
)
_PLACEHOLDER = re.compile(
    r"\b(?:TODO|TBD|FIXME)\b|\[(?:citation needed|reference needed|kaynak gerekli)\]",
    re.IGNORECASE,
)
_OVERCLAIM = re.compile(
    r"\b(?:proves?|guarantees?|always|never|undeniably|kesinlikle|daima|asla)\b",
    re.IGNORECASE,
)
_HEADING_GROUPS = {
    "abstract": {"abstract", "özet"},
    "introduction": {"introduction", "background", "giriş"},
    "methods": {"methods", "method", "methodology", "materials and methods", "methods and materials", "yöntem", "yöntemler", "materyal ve metot", "gereç ve yöntem"},
    "results": {"results", "findings", "results and discussion", "bulgular", "sonuçlar", "sonuç ve tartışma"},
    "discussion": {"discussion", "results and discussion", "general discussion", "tartışma", "sonuç ve tartışma"},
    "references": {"references", "bibliography", "literature cited", "kaynakça"},
}
_SUPPORTED_GENRES = {"general", "original-research"}


def _heading(name: str) -> str:
    # The document parser appends "(2)" to repeated headings.
    return re.sub(r"\s+\(\d+\)$", "", name.strip().casefold())


def _line_at(section_start: int, section_text: str, offset: int) -> int:
    return section_start + section_text.count("\n", 0, offset)


def _author_key(name: str, year: str) -> str:
    return f"{name.casefold()}:{year.casefold()}"


def _citation_numbers(text: str) -> list[int]:
    result: list[int] = []
    for part in re.split(r"\s*[,;]\s*", text):
        if "-" in part or "–" in part:
            start, end = re.split(r"\s*[-–]\s*", part)
            first, last = int(start), int(end)
            # Cap ranges to avoid turning arbitrary numeric arrays into huge citations.
            if first < 1 or last < first or last - first > 20:
                continue
            result.extend(range(first, last + 1))
        else:
            number = int(part)
            if number > 0:
                result.append(number)
    return result


def _add(findings: list[dict[str, Any]], code: str, message: str,
         line: int | None = None, severity: str = "review") -> None:
    findings.append({
        "code": code, "severity": severity, "line": line, "message": message,
    })


def audit_academic_writing(
    path: str | Path, *,
    genre: str = "general",
    abstract_min_words: int | None = None,
    abstract_max_words: int | None = None,
    style_language: str = "en",
    design: str | None = None,
) -> dict[str, Any]:
    """Check section structure, placeholders, cautious phrasing and citation candidates.

    Numeric citations: [1], [2, 3] or [2-4], matched to [1]/1./1) references.
    Author-year citations: (Smith, 2020) or Smith (2020), matched using the first
    surname and year of a simple Smith, J. (2020). reference entry.
    Unsupported styles are explicitly not verified; DOI resolution is not attempted.
    """
    if genre not in _SUPPORTED_GENRES:
        raise ValueError("genre must be 'general' or 'original-research'.")
    for name, limit in (("abstract_min_words", abstract_min_words),
                        ("abstract_max_words", abstract_max_words)):
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ValueError(f"{name} must be a non-negative integer.")
    if (abstract_min_words is not None and abstract_max_words is not None
            and abstract_min_words > abstract_max_words):
        raise ValueError("abstract_min_words cannot exceed abstract_max_words.")

    if design is not None and design not in CHECKLISTS:
        raise ValueError("Unsupported study design. Choose from: " + ", ".join(CHECKLISTS))
    document: ParsedDocument = load_document(path)
    sections = list(document.sections.items())
    groups: dict[str, list[str]] = {
        group: [name for name, _ in sections if _heading(name) in aliases]
        for group, aliases in _HEADING_GROUPS.items()
    }
    findings: list[dict[str, Any]] = []

    if genre == "original-research":
        for group in ("abstract", "introduction", "methods", "results", "discussion", "references"):
            if not groups[group]:
                _add(findings, "missing_section",
                     f"No recognizable {group} heading found; check journal requirements.")
    abstract_words = sum(
        len(_WORD.findall(document.sections[name])) for name in groups["abstract"]
    )
    if groups["abstract"] and abstract_min_words is not None and abstract_words < abstract_min_words:
        _add(findings, "abstract_below_limit",
             f"Abstract has {abstract_words} words; configured minimum is {abstract_min_words}.",
             document.section_start_lines[groups["abstract"][0]])
    if groups["abstract"] and abstract_max_words is not None and abstract_words > abstract_max_words:
        _add(findings, "abstract_above_limit",
             f"Abstract has {abstract_words} words; configured maximum is {abstract_max_words}.",
             document.section_start_lines[groups["abstract"][0]])

    reference_names = set(groups["references"])
    if len(reference_names) > 1:
        _add(findings, "multiple_reference_sections",
             "Multiple reference headings detected; reference parsing may be incomplete.")
    body_sections = [(name, text) for name, text in sections if name not in reference_names]

    for name, text in body_sections:
        start_line = document.section_start_lines[name]
        for pattern, code, message in (
            (_PLACEHOLDER, "editorial_placeholder", "Editorial placeholder requires review."),
            (_OVERCLAIM, "potential_overclaim", "Potentially absolute wording; assess scientific justification."),
        ):
            flagged_lines: set[int] = set()
            for match in pattern.finditer(text):
                line = _line_at(start_line, text, match.start())
                if line not in flagged_lines:
                    flagged_lines.add(line)
                    _add(findings, code, message, line)

    numbered_references: dict[int, list[int]] = {}
    author_references: dict[str, list[int]] = {}
    for name in groups['references']:
        text = document.sections[name]
        start = document.section_start_lines[name]
        for idx, line in enumerate(text.splitlines()):
            number = _NUMBERED_REFERENCE.match(line)
            if number:
                n = int(number.group(1) or number.group(2))
                numbered_references.setdefault(n, []).append(start + idx)
            author = _AUTHOR_REFERENCE.match(line)
            if author:
                key = _author_key(author.group(1), author.group(2))
                author_references.setdefault(key, []).append(start + idx)
    for n, lines in numbered_references.items():
        if len(lines) > 1:
            _add(findings, "duplicate_reference_number",
                 f"Reference number [{n}] appears more than once.", lines[1])
    for key, lines in author_references.items():
        if len(lines) > 1:
            _add(findings, "ambiguous_author_year_reference",
                 f"Multiple references share first-author/year key {key!r}; manual disambiguation needed.",
                 lines[1])

    numeric_citations: dict[int, int] = {}
    author_citations: dict[str, int] = {}
    for name, text in body_sections:
        start = document.section_start_lines[name]
        for match in _NUMBERED_CITATION.finditer(text):
            for number in _citation_numbers(match.group(1)):
                numeric_citations.setdefault(number, _line_at(start, text, match.start()))
        for match in _PARENTHESES.finditer(text):
            for segment in match.group(1).split(";"):
                author = _AUTHOR_PART.match(segment)
                if author:
                    key = _author_key(author.group(1), author.group(2))
                    author_citations.setdefault(key, _line_at(start, text, match.start()))
        for match in _NARRATIVE_AUTHOR.finditer(text):
            key = _author_key(match.group(1), match.group(2))
            author_citations.setdefault(key, _line_at(start, text, match.start()))

    if (numeric_citations or author_citations) and not reference_names:
        _add(findings, "references_section_missing",
             "Recognizable citations found, but no recognizable references heading exists.")
    if reference_names and numeric_citations and not numbered_references:
        _add(findings, "numeric_reference_format_unrecognized",
             "Numeric citation candidates exist, but no supported numbered reference entries were parsed.")
    if reference_names and author_citations and not author_references:
        _add(findings, "author_year_reference_format_unrecognized",
             "Author-year citation candidates exist, but no supported author-year reference entries were parsed.")

    if numbered_references:
        for number, line in numeric_citations.items():
            if number not in numbered_references:
                _add(findings, "unmatched_numeric_citation",
                     f"Numeric citation [{number}] has no matching numbered reference.", line)
        for number, lines in numbered_references.items():
            if number not in numeric_citations:
                _add(findings, "uncited_numbered_reference",
                     f"Numbered reference [{number}] has no recognized in-text citation.", lines[0])
    if author_references:
        for key, line in author_citations.items():
            if key not in author_references:
                _add(findings, "unmatched_author_year_citation",
                     f"Author-year citation {key!r} has no matching parsed reference.", line)
        for key, lines in author_references.items():
            if key not in author_citations:
                _add(findings, "uncited_author_year_reference",
                     f"Reference {key!r} has no recognized in-text citation.", lines[0])

    style_suggestions = style_review(
        document, language=style_language, excluded_sections=reference_names,
    )
    checklist = reporting_cues(document, design) if design is not None else None
    findings.sort(key=lambda finding: (finding["line"] is None, finding["line"] or 0, finding["code"]))
    return {
        "schema_version": "1.0",
        "tool": "academic-writing-audit",
        "source": document.source,
        "source_sha256": document.sha256,
        "genre": genre,
        "status": "REVIEW_REQUIRED" if (findings or style_suggestions) else "NO_AUTOMATED_FLAGS",
        "metrics": {
            "document_word_count": sum(len(_WORD.findall(text)) for _, text in body_sections),
            "abstract_word_count": abstract_words if groups["abstract"] else None,
            "section_count": len(sections),
            "numeric_citation_keys": len(numeric_citations),
            "author_year_citation_keys": len(author_citations),
            "numbered_reference_entries": sum(map(len, numbered_references.values())),
            "author_year_reference_entries": sum(map(len, author_references.values())),
        },
        "settings": {
            "abstract_min_words": abstract_min_words,
            "abstract_max_words": abstract_max_words,
        },
        "findings": findings,
        "style_language": style_language,
        "style_suggestions": style_suggestions,
        "reporting_checklist": checklist,
        "limitations": [
            "Heuristic checks are editorial review prompts, not proof of correctness or scientific validity.",
            "Only explicit bracket-number and simple first-author/year citation formats are checked; others are unverified.",
            "First-author/year matching cannot establish source identity or whether a reference supports a claim.",
            "Word counts are token estimates; journal-specific style, full grammar, plagiarism and external bibliographic accuracy are not assessed.",
        ],
    }


def writing_report_markdown(result: dict[str, Any]) -> str:
    """Render a human-readable report without interpreting input as HTML."""
    lines = [
        "# Academic writing review",
        "",
        f"**Source:** {html.escape(result['source'])}",
        f"**SHA-256:** {result['source_sha256']}",
        f"**Status:** {result['status']}",
        f"**Genre:** {result['genre']}",
        "",
        "## Measurements",
    ]
    for key, value in result["metrics"].items():
        lines.append(f"- {key.replace('_', ' ')}: {value if value is not None else 'not detected'}")
    lines += ["", "## Review prompts"]
    if not result["findings"]:
        lines.append("No automated flags in supported checks. This is not a quality certification.")
    for finding in result["findings"]:
        label = f"line {finding['line']}" if finding["line"] is not None else "document"
        lines.append(f"- **{finding['code']} ({label}):** {html.escape(finding['message'])}")
    lines += ["", "## Academic language suggestions"]
    if not result.get("style_suggestions"):
        lines.append("No supported language patterns flagged.")
    for item in result.get("style_suggestions", []):
        lines.append(
            f"- **{item['code']} (line {item['line']}):** "
            f"{html.escape(item['excerpt'])} — "
            f"{html.escape(item['suggestion'])}"
        )
    checklist = result.get("reporting_checklist")
    if checklist is not None:
        lines += ["", "## Study-design reporting cues"]
        lines.append(f"Advisory framework: {html.escape(checklist['guideline'])}")
        for item in checklist["items"]:
            lines.append(f"- {item['item']}: {item['status']}"
                         + (f" (line {item['line']})" if item['line'] else ""))
        lines.append("Cue detection is not guideline compliance.")
    lines += ["", "## Limits"]
    lines.extend(f"- {html.escape(item)}" for item in result["limitations"])
    return "\n".join(lines) + "\n"
