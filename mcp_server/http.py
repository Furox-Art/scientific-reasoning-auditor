"""Production-facing ASGI app: uvicorn mcp_server.http:app --host 127.0.0.1 --port 8000."""
from mcp_server.auth import make_app
from mcp_server.server import mcp

# Fail closed at import/startup when bearer token is not configured.
app = make_app(mcp.streamable_http_app())
