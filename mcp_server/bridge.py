"""Bounded, stateless MCP adapter. No tool accepts a path, URL or executable code."""
from __future__ import annotations

import base64
import binascii
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any, Iterator

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_JSON_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_B64_CHARS = ((MAX_DOCUMENT_BYTES + 2) // 3) * 4
_EXTENSIONS = {"md": ".md", "txt": ".txt", "pdf": ".pdf"}
_LIMITER = BoundedSemaphore(2)


def _document_bytes(content: str, file_format: str, encoding: str) -> bytes:
    if file_format not in _EXTENSIONS:
        raise ValueError("file_format must be md, txt or pdf.")
    if encoding not in ("text", "base64"):
        raise ValueError("encoding must be text or base64.")
    if not isinstance(content, str) or not content:
        raise ValueError("A nonempty manuscript is required.")
    if file_format == "pdf" and encoding != "base64":
        raise ValueError("PDF manuscripts require base64 encoding.")
    if encoding == "base64":
        if len(content) > MAX_B64_CHARS:
            raise ValueError("Encoded manuscript exceeds the 20 MiB limit.")
        try:
            data = base64.b64decode(content, validate=True)
        except (ValueError, binascii.Error, UnicodeError) as exc:
            raise ValueError("Invalid base64 manuscript.") from exc
    else:
        if len(content) > MAX_DOCUMENT_BYTES:
            raise ValueError("Manuscript exceeds the 20 MiB limit.")
        data = content.encode("utf-8")
    if not data or len(data) > MAX_DOCUMENT_BYTES:
        raise ValueError("Manuscript must be 1 byte to 20 MiB.")
    if file_format == "pdf" and not data.startswith(b"%PDF-"):
        raise ValueError("Uploaded PDF does not have a PDF header.")
    if file_format != "pdf":
        try:
            data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Text manuscript must be UTF-8.") from exc
    return data


def _json_bytes(spec_json: str) -> bytes:
    if not isinstance(spec_json, str) or not spec_json:
        raise ValueError("Nonempty structured JSON is required.")
    if len(spec_json) > MAX_JSON_BYTES:
        raise ValueError("Structured input exceeds 1 MiB.")
    data = spec_json.encode("utf-8")
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("Structured input exceeds 1 MiB.")
    return data


@contextmanager
def _uploaded(data: bytes, suffix: str) -> Iterator[tuple[Path, Path]]:
    # suffix comes only from fixed allowlists or from the literal ".json".
    with tempfile.TemporaryDirectory(prefix="sra-mcp-") as folder:
        root = Path(folder)
        path = root / ("uploaded" + suffix)
        with path.open("xb") as stream:
            stream.write(data)
        yield path, root


def _scrub(value: Any, root: Path) -> Any:
    if isinstance(value, dict):
        return {key: _scrub(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, root) for item in value]
    if isinstance(value, str):
        return value.replace(str(root), "[ephemeral-upload]").replace(root.as_posix(), "[ephemeral-upload]")
    return value


def _bounded(value: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Complete report exceeds the 2 MiB output bound; no partial report returned.")
    return value


def _invoke(task: Any) -> dict[str, Any]:
    if not _LIMITER.acquire(blocking=False):
        return {"ok": False, "error": "BUSY", "message": "Two analyses are running; retry later."}
    try:
        return _bounded({"ok": True, "result": task()})
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        return {"ok": False, "error": "INVALID_INPUT", "message": str(exc).splitlines()[0][:240]}
    except (OSError, RuntimeError, KeyError) as exc:
        return {"ok": False, "error": "PROCESSING_FAILED",
                "message": f"Analysis unavailable ({type(exc).__name__})."}
    finally:
        _LIMITER.release()


def audit_manuscript(content: str, file_format: str = "md", encoding: str = "text") -> dict[str, Any]:
    """Source-located scientific reasoning screening; not scientific truth certification."""
    def task() -> dict[str, Any]:
        from sra.audit import audit_parsed_document
        from sra.document import load_document
        data = _document_bytes(content, file_format, encoding)
        with _uploaded(data, _EXTENSIONS[file_format]) as (path, root):
            document = load_document(path)
            document.source = "uploaded" + _EXTENSIONS[file_format]
            return _scrub(audit_parsed_document(document).to_dict(), root)
    return _invoke(task)


def audit_academic_writing(content: str, file_format: str = "md", encoding: str = "text",
                           genre: str = "general", style_language: str = "en") -> dict[str, Any]:
    """Check academic structure, citations and cautious language, not manuscript correctness."""
    def task() -> dict[str, Any]:
        from sra.writing import audit_academic_writing as run
        if genre not in ("general", "original-research"):
            raise ValueError("genre must be general or original-research.")
        if style_language not in ("en", "tr", "none"):
            raise ValueError("style_language must be en, tr or none.")
        data = _document_bytes(content, file_format, encoding)
        with _uploaded(data, _EXTENSIONS[file_format]) as (path, root):
            return _scrub(run(path, genre=genre, style_language=style_language,
                              grammar_engine="rules"), root)
    return _invoke(task)


def check_citations(content: str, file_format: str = "md", encoding: str = "text",
                    online: bool = False) -> dict[str, Any]:
    """Extract DOIs; explicit opt-in registry lookups do not establish claim support."""
    def task() -> dict[str, Any]:
        from sra.doi import verify_dois
        if type(online) is not bool:
            raise ValueError("online must be boolean.")
        if online and os.getenv("SRA_MCP_ENABLE_NETWORK") != "1":
            raise ValueError("Online DOI lookup is disabled by server configuration.")
        data = _document_bytes(content, file_format, encoding)
        with _uploaded(data, _EXTENSIONS[file_format]) as (path, root):
            return _scrub(verify_dois(path, online=online, limit=20, timeout=6), root)
    return _invoke(task)


def verify_statistics(spec_json: str) -> dict[str, Any]:
    """Independently recalculate supported statistics from explicit structured inputs."""
    def task() -> dict[str, Any]:
        from sra.stats import verify_stats_file
        data = _json_bytes(spec_json)
        with _uploaded(data, ".json") as (path, root):
            return _scrub(verify_stats_file(path), root)
    return _invoke(task)


def verify_scientific_claims(spec_json: str) -> dict[str, Any]:
    """Check structured confidence intervals, SI dimensions and crude risk ratios."""
    def task() -> dict[str, Any]:
        from sra.scientific_validation import verify_scientific_file
        data = _json_bytes(spec_json)
        with _uploaded(data, ".json") as (path, root):
            return _scrub(verify_scientific_file(path), root)
    return _invoke(task)


def review_scientific_paper(content: str, file_format: str = "md", encoding: str = "text",
                            send_to_model: bool = False) -> dict[str, Any]:
    """Whole extracted-text model critique; requires explicit consent and server opt-in."""
    def task() -> dict[str, Any]:
        from sra.paper_review import review_paper
        if send_to_model is not True:
            raise ValueError("Obtain document-owner consent and set send_to_model=true.")
        if os.getenv("SRA_MCP_ENABLE_MODEL_REVIEW") != "1":
            raise ValueError("External model review is disabled by server configuration.")
        model = os.getenv("SRA_MCP_MODEL", "").strip()
        if not model or len(model) > 128 or not os.getenv("OPENAI_API_KEY"):
            raise ValueError("Server-side model identifier and API key are required.")
        data = _document_bytes(content, file_format, encoding)
        with _uploaded(data, _EXTENSIONS[file_format]) as (path, root):
            result = review_paper(path, model=model,
                                  base_url=os.getenv("SRA_MCP_MODEL_BASE_URL", "https://api.openai.com/v1"),
                                  api_key_env="OPENAI_API_KEY", pdf_ocr_mode="off",
                                  visual_pages=False, timeout=60)
            return _scrub(result, root)
    return _invoke(task)


def get_review_capabilities() -> dict[str, Any]:
    """Discover actual coverage without accepting content or transmitting data."""
    from sra.capabilities import capabilities
    return _invoke(capabilities)


def review_manuscript(
    content: str, file_format: str = "md", encoding: str = "text",
    study_type: str = "unknown", disciplines: list[str] | None = None,
    style_language: str = "en", online: bool = False,
    statistics_spec_json: str | None = None, scientific_spec_json: str | None = None,
    send_to_model: bool = False,
    logic_spec_json: str | None = None,
    toolkit_spec_json: str | None = None,
) -> dict[str, Any]:
    """Compose one source-bound review; transport ok is separate from execution status."""
    def task() -> dict[str, Any]:
        from sra.document import load_document
        from sra.review import review_document
        if type(online) is not bool or type(send_to_model) is not bool:
            raise ValueError("online and send_to_model must be booleans.")
        if online and os.getenv("SRA_MCP_ENABLE_NETWORK") != "1":
            raise ValueError("Online DOI lookup is disabled by server configuration.")
        model = None
        if send_to_model:
            if os.getenv("SRA_MCP_ENABLE_MODEL_REVIEW") != "1":
                raise ValueError("External model review is disabled by server configuration.")
            model = os.getenv("SRA_MCP_MODEL", "").strip()
            if not model or len(model) > 128 or not os.getenv("OPENAI_API_KEY"):
                raise ValueError("Server-side model identifier and API key are required.")
        for spec in (statistics_spec_json, scientific_spec_json, logic_spec_json, toolkit_spec_json):
            if spec is not None:
                _json_bytes(spec)
        data = _document_bytes(content, file_format, encoding)
        with _uploaded(data, _EXTENSIONS[file_format]) as (path, root):
            document = load_document(path, pdf_ocr_mode="off")
            document.source = "uploaded" + _EXTENSIONS[file_format]
            result = review_document(
                document, study_type=study_type, disciplines=[] if disciplines is None else disciplines,
                style_language=style_language, online=online,
                statistics_spec=statistics_spec_json, scientific_spec=scientific_spec_json,
                logic_spec=logic_spec_json,
                toolkit_spec=toolkit_spec_json,
                send_to_model=send_to_model, model=model,
                base_url=os.getenv("SRA_MCP_MODEL_BASE_URL", "https://api.openai.com/v1"),
                api_key_env="OPENAI_API_KEY", timeout=60, visual_pages=False,
            )
            return _scrub(result, root)
    return _invoke(task)


def verify_logic(spec_json: str, content: str | None = None,
                 file_format: str = "md", encoding: str = "text") -> dict[str, Any]:
    """Offline formal verification; optional manuscript is source data, never edited."""
    def task() -> dict[str, Any]:
        from sra.logic import verify_logic_spec
        from sra.document import load_document
        _json_bytes(spec_json)
        if content is None:
            return verify_logic_spec(spec_json)
        data = _document_bytes(content, file_format, encoding)
        with _uploaded(data, _EXTENSIONS[file_format]) as (path, root):
            return _scrub(verify_logic_spec(spec_json, document=load_document(path)), root)
    return _invoke(task)


def verify_toolkit(spec_json: str, content: str | None = None,
                   file_format: str = "md", encoding: str = "text") -> dict[str, Any]:
    """Run bounded local checks and return a separate report."""
    def task() -> dict[str, Any]:
        from sra.toolkit import verify_toolkit_spec
        from sra.document import load_document
        _json_bytes(spec_json)
        if content is None:
            return verify_toolkit_spec(spec_json)
        data = _document_bytes(content, file_format, encoding)
        with _uploaded(data, _EXTENSIONS[file_format]) as (path, root):
            return _scrub(verify_toolkit_spec(spec_json, load_document(path)), root)
    return _invoke(task)
