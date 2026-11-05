"""Conservative, non-destructive academic language suggestions.

These patterns intentionally cover a small set of mechanically reviewable
constructions. This is not a grammar checker or automatic scientific editor.
"""
from __future__ import annotations

import re

from sra.document import ParsedDocument

_REPETITION = re.compile(r"\b(?P<word>[a-zA-ZÀ-ÿ]{2,})\s+(?P=word)\b", re.IGNORECASE)
_ENGLISH_PATTERNS = (
    (re.compile(r"\ba\s+(analysis|experiment|evaluation|approach|effect)\b", re.IGNORECASE),
     "article_agreement", lambda m: "an " + m.group(1)),
    (re.compile(r"\ban\s+(study|method|result|sample|trial|test|model)\b", re.IGNORECASE),
     "article_agreement", lambda m: "a " + m.group(1)),
    (re.compile(r"\bdue to the fact that\b", re.IGNORECASE),
     "concision", lambda m: "because"),
    (re.compile(r"\bin order to\b", re.IGNORECASE),
     "concision", lambda m: "to"),
    (re.compile(r"\b(?:should|could|would)\s+of\b", re.IGNORECASE),
     "grammar_construction", lambda m: m.group(0).split()[0] + " have"),
    (re.compile(r"\balot\b", re.IGNORECASE),
     "spelling", lambda m: "a lot"),
    (re.compile(r"\bcomprises\s+of\b", re.IGNORECASE),
     "grammar_construction", lambda m: "comprises"),
    (re.compile(r"\ba\s+(observational|unusual|uncertain)\b", re.IGNORECASE),
     "article_agreement", lambda m: "an " + m.group(1)),
    (re.compile(r"\ban\s+(unique|statistical|university)\b", re.IGNORECASE),
     "article_agreement", lambda m: "a " + m.group(1)),
    (re.compile(r"\bthe\s+results\s+indicates\b", re.IGNORECASE),
     "subject_verb_agreement", lambda m: "the results indicate"),
    (re.compile(r"\bthese\s+data\s+suggests\b", re.IGNORECASE),
     "subject_verb_agreement", lambda m: "these data suggest"),
    (re.compile(r"\bless\s+(participants|subjects|samples|experiments)\b", re.IGNORECASE),
     "countable_quantity", lambda m: "fewer " + m.group(1)),
    (re.compile(r"\bwith\s+regard\s+to\b", re.IGNORECASE),
     "concision", lambda m: "regarding"),
    (re.compile(r"\bit\s+is\s+important\s+to\s+note\s+that\b", re.IGNORECASE),
     "concision", lambda m: "note that"),
    (re.compile(r"\bbased\s+off\s+of\b", re.IGNORECASE),
     "grammar_construction", lambda m: "based on"),
    (re.compile(r"\bnovel\s+new\b", re.IGNORECASE),
     "redundancy", lambda m: "novel"),
    (re.compile(r"\b(?:very|extremely)\s+significant\b", re.IGNORECASE),
     "statistical_language", lambda m: "specify effect size and statistical evidence"),
)
_TURKISH_PATTERNS = (
    (re.compile(r"\bbir\s+çok\b", re.IGNORECASE), "turkish_spelling", lambda m: "birçok"),
    (re.compile(r"\bher\s+hangi\b", re.IGNORECASE), "turkish_spelling", lambda m: "herhangi"),
    (re.compile(r"\byanlız\b", re.IGNORECASE), "turkish_spelling", lambda m: "yalnız"),
    (re.compile(r"\bhiç\s+bir\b", re.IGNORECASE), "turkish_spelling", lambda m: "hiçbir"),
    (re.compile(r"\byada\b", re.IGNORECASE), "turkish_spelling", lambda m: "ya da"),
    (re.compile(r"\bşuan\b", re.IGNORECASE), "turkish_spelling", lambda m: "şu an"),
    (re.compile(r"\bbirşey\b", re.IGNORECASE), "turkish_spelling", lambda m: "bir şey"),
    (re.compile(r"\bherşey\b", re.IGNORECASE), "turkish_spelling", lambda m: "her şey"),
    (re.compile(r"\bpekçok\b", re.IGNORECASE), "turkish_spelling", lambda m: "pek çok"),
    (re.compile(r"\bfarketm(?:ek|iş|esi)\b", re.IGNORECASE),
     "turkish_spelling", lambda m: m.group(0).replace("farket", "fark et")),
    (re.compile(r"\bşöyleki\b", re.IGNORECASE), "turkish_spelling", lambda m: "şöyle ki"),
)
_LANGUAGES = {"en", "tr", "none"}


def style_review(document: ParsedDocument, *, language: str = "en",
                 excluded_sections: set[str] | None = None,
                 long_sentence_words: int = 40) -> list[dict]:
    if language not in _LANGUAGES:
        raise ValueError("style language must be en, tr or none.")
    if type(long_sentence_words) is not int or long_sentence_words < 10:
        raise ValueError("long_sentence_words must be an integer >= 10.")
    if language == "none":
        return []
    results = []
    excluded_sections = excluded_sections or set()
    seen: set[tuple[str, int]] = set()
    for section, text in document.sections.items():
        if section in excluded_sections:
            continue
        start_line = document.section_start_lines[section]
        for i, line in enumerate(text.splitlines()):
            number = start_line + i
            for match in _REPETITION.finditer(line):
                key = ("repeated_word", number)
                if key not in seen:
                    seen.add(key)
                    results.append({
                        "code": "repeated_word", "line": number,
                        "excerpt": match.group(0),
                        "suggestion": match.group("word"),
                        "message": "Possible accidental word repetition; verify in context.",
                        "severity": "review",
                    })
            if language in ("en", "tr"):
                for pattern, code, suggestion in (_ENGLISH_PATTERNS if language == "en" else _TURKISH_PATTERNS):
                    for match in pattern.finditer(line):
                        key = (code, number, match.start())
                        if key not in seen:
                            seen.add(key)
                            results.append({
                                "code": code, "line": number,
                                "excerpt": match.group(0),
                                "suggestion": suggestion(match),
                                "message": "Optional academic editing suggestion; check meaning before applying.",
                                "severity": "review",
                            })
            # Deliberately avoid splitting on periods in numbers, abbreviations,
            # titles and citation formats; a line-level limit is only a cue.
            words = re.findall(r"\b[\w]+\b", line)
            if len(words) > long_sentence_words:
                results.append({
                    "code": "long_line", "line": number,
                    "excerpt": line[:120].strip(),
                    "suggestion": "Review readability; split sentences only if meaning is preserved.",
                    "message": "Line exceeds configured word threshold; not necessarily one sentence.",
                    "severity": "review",
                })
    return results
