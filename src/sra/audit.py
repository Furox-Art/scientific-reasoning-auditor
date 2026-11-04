from sra.checks import build_findings
from sra.document import ParsedDocument, load_document
from sra.graph import build_reasoning_graph
from sra.models import AuditReport
from sra.provenance import build_manifest
from sra.semantic_review import load_semantic_review, validate_semantic_review

SCOPE_NOTE = (
    "Version 0.5.2 adds bounded model API response reads, strict semantic-review JSON parsing, typed reasoning-graph schema validation with versioned contract-aware fingerprints, source-reconstructed graph/node provenance, mandatory inference-to-claim links and empty-graph rejection, version-bound semantic-review 1.4 templates with legacy 1.0–1.3 fingerprint import support, separate raw-file and extracted-text SHA-256 provenance, exact source-hash file inventories with isolated pip-installed wheel and release-artifact verification, strict Content-Length grammar, and full-commit-SHA-pinned CI dependencies. Statistical output now states the common-variance assumptions and heteroskedasticity limitation of pooled-SD Cohen's d and classical Hedges' g. Version 0.5.1 hardened authenticated transport and strict model/statistics JSON, improved Welch numerical stability, and stabilized Hedges' g at very large degrees of freedom. Earlier releases added an OpenAI-compatible single-model review client and strengthened evidence provenance, semantic-review input validation, Markdown/plain-text "
    "section extraction, and negation-aware screening. Directional and causal language checks remain "
    "heuristics, not semantic proofs. It also retains the explicit claim-evidence-assumption-method-inference graph and an "
    "external semantic-review import/validation workflow. Graph relations are extracted with "
    "rules and lexical similarity; they are not proof of semantic support. Imported semantic reviews "
    "are structurally validated against source hashes, graph fingerprints, node IDs and source quotes, "
    "but the reviewer’s semantic judgment is not independently proven by this software. Existing "
    "direction, causality and claim-matching checks remain heuristics. Missing flags do not imply "
    "correctness; expert review and independent computational verification remain necessary."
)


def audit_parsed_document(
    document: ParsedDocument, semantic_review_path: str | None = None
) -> AuditReport:
    """Audit one immutable parsed-document snapshot and its source bytes."""
    findings, candidates, reasoning_map = build_findings(document)
    graph = build_reasoning_graph(document, candidates, reasoning_map)
    report = AuditReport(
        schema_version="1.5",
        source=document.source,
        sha256=document.sha256,
        section_names=list(document.sections),
        findings=findings,
        claim_evidence_candidates=candidates,
        scope_note=SCOPE_NOTE,
        reproducibility_manifest=build_manifest(document),
        reasoning_map=reasoning_map,
        reasoning_graph=graph,
    )
    if semantic_review_path:
        raw_review = load_semantic_review(semantic_review_path)
        report.semantic_review = validate_semantic_review(
            raw_review, report.to_dict(), document.text
        )
    return report


def audit_file(path: str, semantic_review_path: str | None = None) -> AuditReport:
    return audit_parsed_document(load_document(path), semantic_review_path)


def build_review_template(path: str, review_mode: str = "single") -> dict:
    from sra.semantic_review import build_semantic_review_template
    document = load_document(path)
    report = audit_parsed_document(document)
    return build_semantic_review_template(
        report.to_dict(),
        review_mode=review_mode,
        source_text=document.text,
    )
