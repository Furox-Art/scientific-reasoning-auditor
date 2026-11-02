from sra.checks import build_findings
from sra.document import load_document
from sra.models import AuditReport
from sra.provenance import build_manifest

SCOPE_NOTE = (
    "Version 0.2.2 adds line- and section-aware evidence references, heuristic result/conclusion direction-conflict "
    "signals, observational-design/causal-language review, unmatched conclusion-claim signals, and a "
    "reproducibility manifest. These are deterministic screening heuristics, not semantic entailment, "
    "proof checking, causal identification, statistical re-analysis, or verification that a conclusion "
    "is true. They may produce false positives and false negatives. Missing flags do not imply correctness; "
    "human expert review and independent computational checks remain necessary."
)


def audit_file(path: str) -> AuditReport:
    document = load_document(path)
    findings, candidates, reasoning_map = build_findings(document)
    return AuditReport(
        schema_version="1.2",
        source=document.source,
        sha256=document.sha256,
        section_names=list(document.sections),
        findings=findings,
        claim_evidence_candidates=candidates,
        scope_note=SCOPE_NOTE,
        reproducibility_manifest=build_manifest(document),
        reasoning_map=reasoning_map,
    )
