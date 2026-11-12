"""Opt-in DOI registry metadata checks via Crossref (not claim verification)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from sra.document import ParsedDocument, load_document, without_fenced_code

_DOI_PATTERN = re.compile(r"10\.\d{4,9}/[^\s<>\"']+", re.IGNORECASE)
_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", re.IGNORECASE)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def normalize_doi(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = _PREFIX.sub("", value.strip())
    candidate = candidate.rstrip(".,;")
    # Keep balanced parentheses within valid DOIs.
    while candidate.endswith(")") and candidate.count(")") > candidate.count("("):
        candidate = candidate[:-1]
    if len(candidate) > 255 or not _DOI_PATTERN.fullmatch(candidate):
        return None
    if any(ord(char) < 33 or ord(char) > 126 for char in candidate):
        return None
    return candidate.lower()


def _extract_dois(text: str) -> list[tuple[str, int]]:
    seen: set[str] = set()
    matches: list[tuple[str, int]] = []
    for i, line in enumerate(without_fenced_code(text).splitlines(), 1):
        for match in _DOI_PATTERN.finditer(line):
            doi = normalize_doi(match.group(0))
            if doi and doi not in seen:
                seen.add(doi)
                matches.append((doi, i))
    return matches


def _lookup_crossref(doi: str, *, timeout: float = 8.0) -> dict:
    if not 0.5 <= timeout <= 30:
        raise ValueError("timeout must be between 0.5 and 30 seconds.")
    url = "https://api.crossref.org/works/" + quote(doi, safe="")
    request = Request(url, headers={
        "User-Agent": "scientific-reasoning-auditor/0.5 (metadata validation; https://github.com/Furox-Art/scientific-reasoning-auditor)",
        "Accept": "application/json",
    })
    opener = build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                return {"status": "UNVERIFIED", "reason": f"Crossref HTTP {response.status}"}
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return {"status": "UNVERIFIED", "reason": "Crossref response exceeds size limit."}
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("Crossref response must be an object.")
        message = data.get("message", {})
        if not isinstance(message, dict):
            raise ValueError("Invalid Crossref metadata shape.")
        registered = normalize_doi(message.get("DOI", ""))
        if registered != doi:
            return {"status": "UNVERIFIED", "reason": "Registry returned a different DOI."}
        titles = message.get("title", [])
        title = titles[0] if isinstance(titles, list) and titles and isinstance(titles[0], str) else None
        authors = message.get("author", [])
        first_author = None
        if isinstance(authors, list) and authors and isinstance(authors[0], dict):
            first_author = authors[0].get("family")
        published = message.get("published", {})
        if not isinstance(published, dict):
            raise ValueError("Crossref published metadata must be an object.")
        years = published.get("date-parts", [])
        if not isinstance(years, list):
            raise ValueError("Crossref date-parts must be a list.")
        year = years[0][0] if years and isinstance(years[0], list) and years[0] else None
        return {
            "status": "REGISTERED_IN_CROSSREF",
            "registry": "Crossref",
            "doi": registered, "title": title,
            "first_author": first_author, "publication_year": year,
            "type": message.get("type"),
            "metadata_url": url,
        }
    except HTTPError as exc:
        if exc.code == 404:
            return {
                "status": "NOT_FOUND_IN_CROSSREF",
                "reason": "Crossref lookup returned 404. DOI may belong to another agency.",
            }
        return {"status": "UNVERIFIED", "reason": f"Crossref HTTP {exc.code}"}
    except (URLError, TimeoutError, OSError, ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        return {"status": "UNVERIFIED", "reason": f"Registry lookup failed: {type(exc).__name__}"}


def _lookup_datacite(doi: str, *, timeout: float = 8.0) -> dict:
    """Fallback metadata lookup for DataCite-managed DOIs."""
    url = "https://api.datacite.org/dois/" + quote(doi, safe="")
    request = Request(url, headers={
        "User-Agent": "scientific-reasoning-auditor/0.5 (metadata validation; https://github.com/Furox-Art/scientific-reasoning-auditor)",
        "Accept": "application/json",
    })
    try:
        with build_opener(_NoRedirect).open(request, timeout=timeout) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return {"status": "UNVERIFIED", "reason": "DataCite response exceeds size limit."}
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("DataCite response must be an object.")
        data = payload.get("data", {})
        if not isinstance(data, dict):
            raise ValueError("DataCite data must be an object.")
        attributes = data.get("attributes", {})
        if not isinstance(attributes, dict):
            raise ValueError("DataCite attributes must be an object.")
        registered = normalize_doi(attributes.get("doi", ""))
        if registered != doi:
            return {"status": "UNVERIFIED", "reason": "DataCite returned a different DOI."}
        titles = attributes.get("titles", [])
        if not isinstance(titles, list):
            raise ValueError("DataCite titles must be a list.")
        title = titles[0].get("title") if titles and isinstance(titles[0], dict) else None
        creators = attributes.get("creators", [])
        if not isinstance(creators, list):
            raise ValueError("DataCite creators must be a list.")
        first_author = creators[0].get("familyName") if creators and isinstance(creators[0], dict) else None
        if attributes.get("types") is not None and not isinstance(attributes["types"], dict):
            raise ValueError("DataCite types must be an object.")
        return {
            "status": "REGISTERED_IN_DATACITE", "registry": "DataCite",
            "doi": registered, "title": title, "first_author": first_author,
            "publication_year": attributes.get("publicationYear"),
            "type": (attributes.get("types") or {}).get("resourceTypeGeneral"),
            "metadata_url": url,
        }
    except HTTPError as exc:
        if exc.code == 404:
            return {"status": "NOT_FOUND_IN_CROSSREF_OR_DATACITE",
                    "reason": "No public metadata found at either registry; this is not proof of DOI invalidity."}
        return {"status": "UNVERIFIED", "reason": f"DataCite HTTP {exc.code}"}
    except (URLError, TimeoutError, OSError, ValueError, TypeError, AttributeError) as exc:
        return {"status": "UNVERIFIED", "reason": f"DataCite lookup failed: {type(exc).__name__}"}


def _lookup_registry(doi: str, *, timeout: float) -> dict:
    result = _lookup_crossref(doi, timeout=timeout)
    if result["status"] == "NOT_FOUND_IN_CROSSREF":
        return _lookup_datacite(doi, timeout=timeout)
    return result


_REFERENCE_HEADER = re.compile(
    r"^\s*(?:#{1,6}\s+)?(?:references|bibliography|literature cited|works cited|kaynakça)\s*:?\s*$",
    re.IGNORECASE,
)


def _reference_context(text: str, doi: str) -> tuple[int, str] | None:
    """Prefer the bibliography occurrence of a DOI over its first in-text mention.

    A DOI on the line after a citation title can use the previous two lines.
    Stop at an earlier DOI to avoid merging two different references.
    """
    lines = text.splitlines()
    heading_index: int | None = None
    best: tuple[int, str] | None = None
    for index, line in enumerate(lines):
        if _REFERENCE_HEADER.fullmatch(line):
            heading_index = index
            continue
        if line.lstrip().startswith("#") and heading_index is not None:
            heading_index = None
        if heading_index is None:
            continue
        if not any(normalize_doi(match.group()) == doi for match in _DOI_PATTERN.finditer(line)):
            continue
        start = max(heading_index + 1, index - 2)
        for previous in range(start, index):
            if _DOI_PATTERN.search(lines[previous]):
                start = previous + 1
        context = " ".join(segment.strip() for segment in lines[start:index + 1] if segment.strip())
        best = (index + 1, context)
        break
    return best


def _title_context_overlap(title: str | None, reference_line: str, doi: str) -> dict:
    """Advisory overlap only; cannot establish reference correctness."""
    if not title:
        return {"status": "NOT_EVALUATED", "reason": "No registry title."}
    tokens = lambda value: set(re.findall(r"[a-zA-ZÀ-ÿ]{4,}", value.casefold()))
    title_terms = tokens(title)
    context = reference_line.casefold().replace(doi, "")
    context_terms = tokens(context)
    if len(title_terms) < 3 or len(context_terms) < 4:
        return {"status": "NOT_EVALUATED", "reason": "Insufficient reference text for a title comparison."}
    overlap = len(title_terms & context_terms) / len(title_terms)
    return {
        "status": "TITLE_WORDS_OVERLAP" if overlap >= 0.7 else "REVIEW_TITLE_MANUALLY",
        "registry_title_token_recall": round(overlap, 3),
        "note": "Token overlap is a weak cue, not bibliographic identity or semantic source verification.",
    }


def verify_dois(path: str | Path, *, online: bool = False,
                timeout: float = 8.0, limit: int = 50) -> dict:
    return verify_document_dois(load_document(path), online=online, timeout=timeout, limit=limit)


def verify_document_dois(document: ParsedDocument, *, online: bool = False,
                         timeout: float = 8.0, limit: int = 50) -> dict:
    """Check DOI metadata against the same parsed snapshot as other modules."""
    if type(online) is not bool:
        raise ValueError("online must be a boolean.")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("limit must be an integer from 1 to 200.")
    if type(timeout) not in (int, float) or not 0.5 <= timeout <= 30:
        raise ValueError("timeout must be between 0.5 and 30 seconds.")
    found = _extract_dois(document.text)
    records = []
    for doi, line in found[:limit]:
        item = {"doi": doi, "line": line}
        if online:
            item.update(_lookup_registry(doi, timeout=timeout))
            reference = _reference_context(document.text, doi)
            item["reference_line"] = reference[0] if reference else None
            item["title_comparison"] = (
                _title_context_overlap(item.get("title"), reference[1], doi)
                if reference else {"status": "NOT_EVALUATED",
                                   "reason": "No explicit bibliography occurrence of this DOI."}
            )
        else:
            item["status"] = "NOT_CHECKED_OFFLINE"
        records.append(item)
    return {
        "schema_version": "1.0",
        "source": document.source,
        "source_sha256": document.sha256,
        "online_lookup": online,
        "registry": "Crossref / DataCite" if online else None,
        "found_count": len(found),
        "checked_count": len(records),
        "truncated": len(found) > limit,
        "results": records,
        "limitations": [
            "Registry metadata establishes DOI presence, not scientific truth or claim support.",
            "Crossref and DataCite cover different DOI registrants; lack of public metadata is not proof of invalidity.",
            "This scan recognizes DOI patterns in document text; it does not determine which claim each DOI supports.",
            "Online mode sends extracted DOI identifiers to Crossref and, if necessary, DataCite; manuscript text is not uploaded.",
        ],
    }
