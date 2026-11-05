"""Opt-in local-only LanguageTool connector for manuscript grammar suggestions.

No manuscript text leaves the user's machine. There is no external
grammar endpoint, automatic edit application or implicit dependency install.
"""
from __future__ import annotations

import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import (
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

from sra.document import ParsedDocument


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_MAX_INPUT_CHARS = 120_000
_MAX_RESPONSE_BYTES = 3_000_000


def _prepare_prose(document: ParsedDocument, excluded_sections: set[str]):
    text_parts = []
    spans = []
    position = 0
    for section, body in document.sections.items():
        if section in excluded_sections or not body.strip():
            continue
        if text_parts:
            text_parts.append("\n\n")
            position += 2
        start = position
        text_parts.append(body)
        position += len(body)
        spans.append((start, position, section, document.section_start_lines[section], body))
    text = "".join(text_parts)
    if len(text) > _MAX_INPUT_CHARS:
        raise ValueError(
            f"Manuscript prose is longer than {_MAX_INPUT_CHARS} characters for a single "
            "local grammar request. No content was sent."
        )
    return text, spans


def _utf16_positions(text: str) -> dict[int, int]:
    """Map valid UTF-16 code-unit boundaries to Python character indices."""
    mapping = {0: 0}
    pos = 0
    for index, char in enumerate(text, 1):
        pos += 2 if ord(char) > 0xFFFF else 1
        mapping[pos] = index
    return mapping


def check_local_languagetool(
    document: ParsedDocument, *,
    language: str = "en",
    excluded_sections: set[str] | None = None,
    port: int = 8081,
    timeout: float = 8.0,
) -> list[dict]:
    """Call only 127.0.0.1 with a bounded request and parse source-located matches."""
    if language not in ("en", "tr"):
        raise ValueError("Local grammar checking supports language en or tr.")
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Local grammar port must be an integer from 1024 to 65535.")
    if type(timeout) not in (int, float) or not 0.5 <= timeout <= 30:
        raise ValueError("Local grammar timeout must be between 0.5 and 30 seconds.")
    text, spans = _prepare_prose(document, excluded_sections or set())
    if not text.strip():
        return []
    request = Request(
        f"http://127.0.0.1:{port}/v2/check",
        data=urlencode({
            "text": text,
            "language": "en-US" if language == "en" else "tr",
            "level": "default",
        }).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"},
        method="POST",
    )
    try:
        # Suppress inherited HTTP(S)_PROXY for loopback requests.
        with build_opener(ProxyHandler({}), _NoRedirect()).open(
            request, timeout=timeout
        ) as response:
            raw = response.read(_MAX_RESPONSE_BYTES + 1)
    except (URLError, OSError, TimeoutError) as exc:
        raise RuntimeError(
            "Local LanguageTool service unavailable; start a trusted local "
            f"LanguageTool HTTP server on 127.0.0.1:{port}."
        ) from exc
    if len(raw) > _MAX_RESPONSE_BYTES:
        raise ValueError("Local grammar response exceeds the 3 MB limit.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Local grammar response is not valid JSON.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
        raise ValueError("Local grammar response has an unexpected structure.")
    if len(payload["matches"]) > 1500:
        raise ValueError("Local grammar response contains too many matches.")

    positions = _utf16_positions(text)
    suggestions = []
    seen = set()
    for hit in payload["matches"]:
        if not isinstance(hit, dict):
            raise ValueError("Local grammar response has a malformed match.")
        start_units, length_units = hit.get("offset"), hit.get("length")
        if (type(start_units) is not int or type(length_units) is not int
                or start_units < 0 or length_units <= 0
                or start_units not in positions
                or start_units + length_units not in positions):
            raise ValueError("Local grammar match offset is invalid (UTF-16 boundary).")
        start = positions[start_units]
        length = positions[start_units + length_units] - start
        span = next(
            (part for part in spans if part[0] <= start and start + length <= part[1]),
            None,
        )
        if span is None:
            # Ignore matches crossing generated section separators.
            continue
        _begin, _end, section, line_start, body = span
        offset = start - _begin
        line = line_start + body.count("\n", 0, offset)
        replacements = hit.get("replacements", [])
        if not isinstance(replacements, list):
            raise ValueError("Local grammar replacements must be a list.")
        choices = [
            item["value"] for item in replacements[:5]
            if isinstance(item, dict) and isinstance(item.get("value"), str)
            and len(item["value"]) <= 250
        ]
        rule = hit.get("rule") or {}
        if not isinstance(rule, dict):
            raise ValueError("Local grammar rule information is malformed.")
        rule_id = rule.get("id", "unknown")
        if not isinstance(rule_id, str):
            raise ValueError("Local grammar rule ID is invalid.")
        key = (section, start, length, rule_id)
        if key in seen:
            continue
        seen.add(key)
        message = hit.get("message", "Local grammar suggestion")
        if not isinstance(message, str):
            message = "Local grammar suggestion"
        suggestions.append({
            "code": "local_grammar",
            "engine": "languagetool_local",
            "rule_id": rule_id[:120],
            "section": section,
            "line": line,
            "excerpt": text[start:start + length],
            "suggestion": choices[0] if choices else "",
            "replacements": choices,
            "message": message[:500],
            "severity": "review",
            "confidence": "not_calibrated",
        })
    return sorted(suggestions, key=lambda x: (x["line"], x["rule_id"]))
