from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Finding:
    check_id: str
    title: str
    severity: str
    status: str
    message: str
    evidence: list[str] = field(default_factory=list)
    evidence_locations: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimEvidenceCandidate:
    claim: str
    candidate_support: str | None
    lexical_overlap: float
    interpretation: str
    claim_line: int | None = None
    support_line: int | None = None
    claim_section: str | None = None
    support_section: str | None = None
    match_status: str = "heuristic_candidate"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditReport:
    schema_version: str
    source: str
    sha256: str
    section_names: list[str]
    findings: list[Finding]
    claim_evidence_candidates: list[ClaimEvidenceCandidate]
    scope_note: str
    reproducibility_manifest: dict[str, Any] = field(default_factory=dict)
    reasoning_map: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "sha256": self.sha256,
            "section_names": self.section_names,
            "findings": [item.to_dict() for item in self.findings],
            "claim_evidence_candidates": [
                item.to_dict() for item in self.claim_evidence_candidates
            ],
            "scope_note": self.scope_note,
            "reproducibility_manifest": self.reproducibility_manifest,
            "reasoning_map": self.reasoning_map,
        }
