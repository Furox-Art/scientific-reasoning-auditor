from sra.checks import build_findings
from sra.document import load_document
from sra.graph import build_reasoning_graph
from sra.models import AuditReport
from sra.provenance import build_manifest
from sra.semantic_review import load_semantic_review, validate_semantic_review

SCOPE_NOTE = (
    "Version 0.4.0 hardens evidence provenance, semantic-review input validation, Markdown/plain-text "
    "section extraction, and negation-aware screening. Directional and causal language checks remain "
    "heuristics, not semantic proofs. It also retains the explicit claim-evidence-assumption-method-inference graph and an "
    "external semantic-review import/validation workflow. Graph relations are extracted with "
    "rules and lexical similarity; they are not proof of semantic support. Imported semantic reviews "
    "are structurally validated against source hashes, graph fingerprints, node IDs and source quotes, "
    "but the reviewer’s semantic judgment is not independently proven by this software. Existing "
    "direction, causality and claim-matching checks remain heuristics. Missing flags do not imply "
    "correctness; expert review and independent computational verification remain necessary."
)


def audit_file(path: str, semantic_review_path: str | None = None) -> AuditReport:
    document = load_document(path)
    findings, candidates, reasoning_map = build_findings(document)
    graph = build_reasoning_graph(document, candidates, reasoning_map)
    report = AuditReport(
        schema_version="1.4",
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
        report.semantic_review = validate_semantic_review(raw_review, report.to_dict(), document.text)
    return report


def build_review_template(path: str, review_mode: str = "single") -> dict:
    from sra.semantic_review import build_semantic_review_template
    report = audit_file(path)
    return build_semantic_review_template(report.to_dict(), review_mode=review_mode)
