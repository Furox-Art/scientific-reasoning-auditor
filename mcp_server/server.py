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


@mcp.tool(title="Discover scientific review coverage", annotations=_LOCAL)
def get_review_capabilities() -> dict[str, Any]:
    """List available study types, specialist profiles, arithmetic checks and interface limits. Coverage is not scientific validation."""
    return bridge.get_review_capabilities()


@mcp.tool(title="Review a manuscript across scientific disciplines", annotations=_EXTERNAL)
def review_manuscript(
    content: str, file_format: str = "md", encoding: str = "text",
    study_type: str = "unknown", disciplines: list[str] | None = None,
    style_language: str = "en", online: bool = False,
    statistics_spec_json: str | None = None, scientific_spec_json: str | None = None,
    send_to_model: bool = False,
) -> dict[str, Any]:
    """Compose reasoning, writing, selected field cues, DOI metadata and explicit arithmetic checks in one source-bound report. Discover profiles with get_review_capabilities. Offline by default. Only set send_to_model=true after explicit document-owner consent; online/model requests also require host opt-in. Inspect result.execution_status and each module, even when ok=true. PDF OCR and vision are unavailable here. No paths or URLs."""
    return bridge.review_manuscript(
        content, file_format, encoding, study_type, disciplines, style_language,
        online, statistics_spec_json, scientific_spec_json, send_to_model,
    )


def main() -> None:
    """Local desktop MCP transport; does not require a network auth token."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
