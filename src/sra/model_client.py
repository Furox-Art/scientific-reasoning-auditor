"""OpenAI-compatible chat-completions client for single-model semantic review."""
from __future__ import annotations
import ipaddress
import hashlib
import json
import math
import os
import re
from decimal import Decimal
from typing import Any
from sra.json_utils import reject_duplicate_keys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


MAX_MODEL_API_RESPONSE_BYTES = 10 * 1024 * 1024


def _read_bounded_response(response, maximum: int = MAX_MODEL_API_RESPONSE_BYTES) -> bytes:
    """Read a response body without allowing an endpoint to exhaust process memory."""
    if maximum <= 0:
        raise ValueError("The model API response size limit must be positive.")
    headers = getattr(response, "headers", None)
    content_length = headers.get("Content-Length") if headers is not None else None
    if content_length is not None:
        if not isinstance(content_length, str) or re.fullmatch(r"[0-9]+", content_length) is None:
            raise ValueError(
                "Model API response has an invalid Content-Length header; expected ASCII digits only."
            )
        declared_length = int(content_length)
        if declared_length > maximum:
            raise ValueError(
                f"Model API response exceeds the {maximum}-byte response size limit."
            )
    body = response.read(maximum + 1)
    if len(body) > maximum:
        raise ValueError(
            f"Model API response exceeds the {maximum}-byte response size limit."
        )
    return body


class _NoRedirectHandler(HTTPRedirectHandler):
    """Reject redirects so an authenticated request cannot leak its API key."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(
            req.full_url, code,
            "Redirects are disabled for authenticated model API requests.",
            headers, fp,
        )


def _open_api_request(request: Request, timeout: int):
    parsed_url = urlsplit(request.full_url)
    if parsed_url.scheme == "http":
        # Local clear-text inference endpoints must never be sent through an
        # environment-configured HTTP proxy with the Authorization header.
        opener = build_opener(ProxyHandler({}), _NoRedirectHandler)
    else:
        opener = build_opener(_NoRedirectHandler)
    return opener.open(request, timeout=timeout)


def _reject_nonstandard_json_constant(token: str) -> None:
    raise ValueError(f"Non-standard JSON numeric constant {token!r} is not permitted.")


def _parse_finite_json_float(token: str) -> float:
    try:
        decimal_value = Decimal(token)
        value = float(decimal_value)
    except (ArithmeticError, ValueError) as exc:
        raise ValueError("Model JSON contains a number outside the supported floating-point range.") from exc
    if not math.isfinite(value):
        raise ValueError("Model JSON contains a number outside the supported floating-point range.")
    if decimal_value != 0 and value == 0.0:
        raise ValueError("Model JSON contains a number too small for floating-point representation.")
    if Decimal(str(value)) != decimal_value:
        raise ValueError("Model JSON contains a number with precision beyond floating-point representation.")
    return value


def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    fence = chr(96) * 3
    if text.startswith(fence) and text.endswith(fence):
        text = re.sub(r"^" + re.escape(fence) + r"(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*" + re.escape(fence) + r"$", "", text).strip()
    try:
        value = json.loads(
            text,
            parse_float=_parse_finite_json_float,
            parse_constant=_reject_nonstandard_json_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model response is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Model response JSON root must be an object.")
    return value


def request_single_model_review(template: dict[str, Any], manuscript: str, *,
        model: str, base_url: str, api_key_env: str = "OPENAI_API_KEY",
        timeout: int = 120, provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    if template.get("review_mode") != "single":
        raise ValueError("Single-model API mode requires review_mode='single'.")
    if not model.strip():
        raise ValueError("A model name is required.")
    if not isinstance(base_url, str) or not base_url or base_url != base_url.strip():
        raise ValueError("base_url must be a non-empty URL without surrounding whitespace.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in base_url):
        raise ValueError("base_url contains prohibited control characters.")
    try:
        parsed_base_url = urlsplit(base_url)
        hostname = parsed_base_url.hostname
        # Accessing .port also validates malformed port syntax.
        _ = parsed_base_url.port
    except ValueError as exc:
        raise ValueError("base_url is not a valid HTTP(S) URL.") from exc
    if parsed_base_url.scheme not in {"https", "http"} or not hostname:
        raise ValueError("base_url must be a valid absolute HTTP(S) URL.")
    if parsed_base_url.username is not None or parsed_base_url.password is not None:
        raise ValueError("base_url must not contain embedded username or password credentials.")
    if "?" in base_url or "#" in base_url:
        raise ValueError("base_url must not contain query or fragment delimiters.")
    try:
        is_loopback = ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        is_loopback = hostname.casefold() == "localhost"
    if parsed_base_url.scheme == "http" and not is_loopback:
        raise ValueError(
            "Insecure HTTP is allowed only for localhost/loopback endpoints. "
            "Use HTTPS for remote model APIs so the API key is encrypted in transit."
        )
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        raise ValueError(f"API key environment variable {api_key_env!r} is not set.")
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    system_prompt = (
        "You are a careful scientific reasoning reviewer. Review every assessment against "
        "the complete manuscript. Return ONLY one complete JSON object preserving every "
        "template field and assessment identifier. Do not invent evidence IDs, quotations, "
        "data or citations. Use exact source quotations of at least 20 characters for "
        "entailed, partially_supported or contradicted decisions. Use evidence_catalog IDs "
        "for Results evidence. For contradicted decisions, provide separate counter_evidence "
        "IDs. Preserve source_sha256, graph_fingerprint, review_mode, evidence_catalog, "
        "instructions and relation_labels unchanged. Identify the model and provide current "
        "UTC time in ISO-8601 Z format. Confidence is confidence in the assessment, not truth."
    )
    payload = {
        "model": model, "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({
                "template": template, "manuscript": manuscript,
                "output_contract": "Return a JSON object only."
            }, ensure_ascii=False, allow_nan=False)},
        ],
    }
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"
    }, method="POST")
    try:
        with _open_api_request(request, timeout=timeout) as response:
            body = json.loads(
                _read_bounded_response(response).decode("utf-8"),
                parse_float=_parse_finite_json_float,
                parse_constant=_reject_nonstandard_json_constant,
                object_pairs_hook=reject_duplicate_keys,
            )
    except HTTPError as exc:
        try:
            _read_bounded_response(exc)
        except ValueError as limit_error:
            # Keep the bounded-reader error but never expose provider body text.
            raise RuntimeError(f"Model API HTTP {exc.code}: {limit_error}") from None
        finally:
            exc.close()
        raise RuntimeError(f"Model API returned HTTP {exc.code}; response body withheld.") from None
    except URLError as exc:
        raise RuntimeError("Could not reach model API.") from None
    except (TimeoutError, OSError) as exc:
        raise RuntimeError("Model API request failed.") from None
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Model API response lacks choices[0].message.content.") from exc
    if not isinstance(content, str):
        raise ValueError("Model API message content must be a string.")
    review = _extract_json_object(content)
    if provenance is not None:
        provenance.update({
            "schema_version": "1.0",
            "requested_model": model,
            "endpoint_base_url": f"{parsed_base_url.scheme}://{parsed_base_url.netloc}",
            "endpoint_path_sha256": hashlib.sha256(
                parsed_base_url.path.encode("utf-8")
            ).hexdigest(),
            "response_model": body.get("model") if isinstance(body.get("model"), str) else None,
            "provider_system_fingerprint": (
                body.get("system_fingerprint")
                if isinstance(body.get("system_fingerprint"), str) else None
            ),
            "temperature": 0,
            "request_body_sha256": hashlib.sha256(request.data).hexdigest(),
            "response_content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "note": "Hashes document this model interaction; temperature=0 does not guarantee deterministic repeatability.",
        })
    return review
