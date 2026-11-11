"""Raw ASGI bearer and size tests; no external server or credentials."""
import asyncio
import json
import unittest
from mcp_server.auth import BearerGuard, MAX_HTTP_BODY, make_app

TOKEN = "x" * 40


async def exchange(app, headers=(), path="/mcp", method="POST", data=b""):
    outgoing = []
    sent = False
    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": data, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(payload):
        outgoing.append(payload)
    scope = {"type": "http", "path": path, "method": method, "headers": list(headers)}
    await app(scope, receive, send)
    return outgoing


class AuthTests(unittest.TestCase):
    def test_fail_closed_without_secret(self):
        with self.assertRaises(RuntimeError):
            make_app(lambda *_: None, token="")
        with self.assertRaises(RuntimeError):
            make_app(lambda *_: None, token="short")
        with self.assertRaises(RuntimeError):
            make_app(lambda *_: None, token="a" * 40 + "\n")

    def test_401_does_not_call_underlying_app(self):
        async def forbidden(*args):
            raise AssertionError("Access was not authorized")
        gate = BearerGuard(forbidden, TOKEN)
        responses = asyncio.run(exchange(gate))
        self.assertEqual(responses[0]["status"], 401)
        self.assertNotIn(TOKEN.encode(), json.dumps(str(responses)).encode())
        bad = asyncio.run(exchange(gate, headers=[(b"authorization", b"Bearer bad")]))
        self.assertEqual(bad[0]["status"], 401)

    def test_valid_token_passes_through(self):
        async def echo(scope, receive, send):
            request = await receive()
            assert request["body"] == b"hello"
            await send({"type": "http.response.start", "status": 202, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
        gate = BearerGuard(echo, TOKEN)
        result = asyncio.run(exchange(gate, headers=[(b"authorization", b"Bearer " + TOKEN.encode()), (b"content-length", b"5")], data=b"hello"))
        self.assertEqual(result[0]["status"], 202)
        without_length = asyncio.run(exchange(gate, headers=[(b"authorization", b"Bearer " + TOKEN.encode())], data=b"hello"))
        self.assertEqual(without_length[0]["status"], 202)

    def test_size_guard_and_invalid_header(self):
        async def forbidden(*args):
            raise AssertionError("Large input reached server")
        gate = BearerGuard(forbidden, TOKEN)
        base = [(b"authorization", b"Bearer " + TOKEN.encode())]
        over = asyncio.run(exchange(gate, headers=base + [(b"content-length", str(MAX_HTTP_BODY+1).encode())]))
        self.assertEqual(over[0]["status"], 413)
        malformed = asyncio.run(exchange(gate, headers=base + [(b"content-length", b"1x")]))
        self.assertEqual(malformed[0]["status"], 400)

    def test_healthcheck_discloses_no_token(self):
        async def forbidden(*args):
            raise AssertionError("health must not reach backend")
        gate = BearerGuard(forbidden, TOKEN)
        out = asyncio.run(exchange(gate, path="/healthz", method="GET"))
        self.assertEqual(out[0]["status"], 200)
        self.assertEqual(json.loads(out[1]["body"])["status"], "ok")


if __name__ == "__main__":
    unittest.main()
