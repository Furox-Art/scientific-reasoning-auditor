"""ASGI HTTP gateway with fixed bearer access, request-size guard and no content logging.

For public directory submission use OAuth 2.1 at a verified gateway instead:
the current portal does NOT accept static API-key connection setup.
"""
from __future__ import annotations

import hmac
import json
import os
from typing import Any, Callable

MAX_HTTP_BODY = 29 * 1024 * 1024


def _headers(scope: dict[str, Any]) -> dict[bytes, bytes]:
    return {key.lower(): value for key, value in scope.get("headers", ())}


async def _answer(send: Callable[..., Any], status: int, payload: dict[str, str],
                  extra: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if extra:
        headers.extend(extra)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class BearerGuard:
    """A single-owner API-key guard; never exposes credentials in logs or tool results."""

    def __init__(self, app: Any, token: str) -> None:
        if not isinstance(token, str) or len(token) < 32 or any(ord(x) < 33 or ord(x) > 126 for x in token):
            raise RuntimeError("Configure SRA_MCP_BEARER_TOKEN with >=32 printable ASCII characters.")
        self.app = app
        self._token = token.encode("ascii")

    async def __call__(self, scope: dict[str, Any], receive: Callable[..., Any],
                       send: Callable[..., Any]) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope.get("path") == "/healthz":
            await _answer(send, 200, {"status": "ok"})
            return

        headers = _headers(scope)
        bearer = headers.get(b"authorization", b"")
        if not (bearer.startswith(b"Bearer ") and
                hmac.compare_digest(bearer[len(b"Bearer "):], self._token)):
            await _answer(send, 401, {"error": "unauthorized"},
                          [(b"www-authenticate", b"Bearer")])
            return

        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                if not raw_length.isascii() or not raw_length.isdigit():
                    raise ValueError("invalid")
                declared = int(raw_length)
            except ValueError:
                await _answer(send, 400, {"error": "invalid_content_length"})
                return
            if declared > MAX_HTTP_BODY:
                await _answer(send, 413, {"error": "request_too_large"})
                return

        # MCP SDK >=1.29.1 limits streamed HTTP bodies (including chunked requests)
        # to MCP_MAX_BODY and responds 413 without parsing an oversized payload.
        await self.app(scope, receive, send)


def make_app(mcp_app: Any, token: str | None = None) -> BearerGuard:
    return BearerGuard(mcp_app, os.environ.get("SRA_MCP_BEARER_TOKEN", "") if token is None else token)
