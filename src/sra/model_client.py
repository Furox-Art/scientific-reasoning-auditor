"""OpenAI-compatible chat-completions client for single-model semantic review."""
from __future__ import annotations
import ipaddress
import json
import math
import os
import re
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


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
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model response is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Model response JSON root must be an object.")
    return value


def request_single_model_review(template: dict[str, Any], manuscript: str, *,
        model: str, base_url: str, api_key_env: str = "OPENAI_API_KEY",
        timeout: int = 120) -> dict[str, Any]:
    if template.get("review_mode") != "single":
        raise ValueError("Single-model API mode requires review_mode='single'.")
    if not model.strip():
        raise ValueError("A model name is required.")
    if not isinstance(base_url, str) or not base_url or base_url != base_url.strip():
        raise ValueError("base_url must be a non-empty URL without surrounding whitespace.")
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
                response.read().decode("utf-8"),
                parse_float=_parse_finite_json_float,
                parse_constant=_reject_nonstandard_json_constant,
            )
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"Model API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach model API: {exc.reason}") from exc
    except (TimeoutError, OSError) as exc:
        raise RuntimeError(f"Model API request failed: {exc}") from exc
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Model API response lacks choices[0].message.content.") from exc
    if not isinstance(content, str):
        raise ValueError("Model API message content must be a string.")
    return _extract_json_object(content)
