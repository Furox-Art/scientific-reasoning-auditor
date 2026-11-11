"""MCP tools wrapping the independently installable SRA Python engine."""
from __future__ import annotations

from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from mcp_server import bridge

MCP_MAX_BODY = 29 * 1024 * 1024
mcp = FastMCP(
    "Scientific Reasoning Auditor",
    instructions=(
        "Scientific screening is advisory: never label a manuscript scientifically true or "
        "false from these tools alone. Interpret source-located findings and limitations. "
        "Call model review only after the user explicitly consents to sending the complete "
        "extracted manuscript to the server-configured external model provider."
    ),
    json_response=True,
    stateless_http=True,
    max_request_body_size=MCP_MAX_BODY,
)

_LOCAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False)
_EXTERNAL = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)


@mcp.tool(title="Audit scientific reasoning", annotations=_LOCAL)
def audit_manuscript(content: str, file_format: str = "md",
                     encoding: str = "text") -> dict[str, Any]:
    """Screen hypothesis, methods, results, claims and evidence; report source-located risk signals. Manuscript text goes in content. For PDF supply base64 content with file_format='pdf' and encoding='base64'. Never send paths or URLs."""
    return bridge.audit_manuscript(content, file_format, encoding)


@mcp.tool(title="Audit academic writing", annotations=_LOCAL)
def audit_academic_writing(content: str, file_format: str = "md",
                           encoding: str = "text", genre: str = "general",
                           style_language: str = "en") -> dict[str, Any]:
    """Check editorial structure and language signals without rewriting. genre: general or original-research. style_language: en, tr or none."""
    return bridge.audit_academic_writing(content, file_format, encoding, genre, style_language)


@mcp.tool(title="Check DOI citations", annotations=_EXTERNAL)
def check_citations(content: str, file_format: str = "md",
                    encoding: str = "text", online: bool = False) -> dict[str, Any]:
    """Extract DOIs and optionally query Crossref/DataCite. Online requests need explicit online=true and server opt-in; registry metadata is not claim verification."""
    return bridge.check_citations(content, file_format, encoding, online)


@mcp.tool(title="Verify statistical results", annotations=_LOCAL)
def verify_statistics(spec_json: str) -> dict[str, Any]:
    """Recalculate supported statistical tests from structured JSON. Checks arithmetic conditional on supplied data, not scientific study validity."""
    return bridge.verify_statistics(spec_json)


@mcp.tool(title="Verify structured scientific claims", annotations=_LOCAL)
def verify_scientific_claims(spec_json: str) -> dict[str, Any]:
    """Check 95% CI interpretation, safe SI dimensional equations and crude risk ratios using SRA verify-science JSON schema."""
    return bridge.verify_scientific_claims(spec_json)


@mcp.tool(title="Review entire extracted manuscript with a model", annotations=_EXTERNAL)
def review_scientific_paper(content: str, file_format: str = "md",
                            encoding: str = "text", send_to_model: bool = False) -> dict[str, Any]:
    """Send all extractable manuscript text to the configured external model for critical review. Requires explicit user consent (send_to_model=true) AND server opt-in. Not a proof of scientific correctness."""
    return bridge.review_scientific_paper(content, file_format, encoding, send_to_model)


def main() -> None:
    """Local desktop MCP transport; does not require a network auth token."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
