"""OpenAI-compatible chat-completions client for single-model semantic review."""
from __future__ import annotations
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from typing import Any

def _extract_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    fence = chr(96) * 3
    if text.startswith(fence) and text.endswith(fence):
        text = re.sub(r"^" + re.escape(fence) + r"(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*" + re.escape(fence) + r"$", "", text).strip()
    try:
        value = json.loads(text)
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
    if not base_url.startswith(("https://", "http://")):
        raise ValueError("base_url must be an HTTP(S) URL.")
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
            }, ensure_ascii=False)},
        ],
    }
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"
    }, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
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
