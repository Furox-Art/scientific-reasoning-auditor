from sra.checks import build_findings
from sra.document import load_document
from sra.models import AuditReport

SCOPE_NOTE = (
    "Version 0.1 performs deterministic, rule-based screening of document structure and selected wording. "
    "Claim-evidence links are lexical candidates, not semantic entailment checks. It does not verify "
    "external facts, reproduce analyses, validate equations, assess study design in depth, or establish "
    "whether a scientific conclusion is true. A missing signal does not imply correctness. Expert review is required."
)


def audit_file(path: str) -> AuditReport:
    document = load_document(path)
    findings, candidates = build_findings(document)
    return AuditReport(
        schema_version="1.0",
        source=document.source,
        sha256=document.sha256,
        section_names=list(document.sections),
        findings=findings,
        claim_evidence_candidates=candidates,
        scope_note=SCOPE_NOTE,
    )
