FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

# Only the Python engine and MCP adapter are required at runtime.
COPY pyproject.toml README.md LICENSE MANIFEST.in ./
COPY src/ ./src/
COPY mcp_server/ ./mcp_server/
RUN python -m pip install --no-cache-dir ".[pdf,statistics,logic,toolkit]" -r mcp_server/requirements.txt \
    && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin sra

USER 10001
EXPOSE 8000
# Use a read-only container and a tmpfs /tmp with resource quotas when deploying.
# Require SRA_MCP_BEARER_TOKEN; the app refuses to boot without it.
CMD ["uvicorn", "mcp_server.http:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
