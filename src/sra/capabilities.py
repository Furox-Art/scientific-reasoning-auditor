"""Explicit review coverage. A supported interface is not scientific validation."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sra.domain_evidence import PROFILES
from sra.stats_extended import SUPPORTED_TESTS

STUDY_TYPES = (
    "unknown", "quantitative", "qualitative", "computational", "theoretical",
    "systematic-review", "narrative-review", "mixed",
)
REPORT_SCHEMA = "cross-disciplinary-review/1.0"
APPLICABILITY_VERSION = "explicit-study-type/1.0"
EMPIRICAL_STRUCTURE = ("structure.methods_missing", "structure.results_missing")


def capabilities() -> dict[str, Any]:
    """Return a fresh catalog; abbreviated field cues never imply expert coverage."""
    catalog = {
        "schema_version": REPORT_SCHEMA,
        "applicability_version": APPLICABILITY_VERSION,
        "study_types": list(STUDY_TYPES),
        "disciplines": {
            key: {"guidance": value["source"], "guidance_url": value["source_url"],
                  "rule_ids": [rule.key for rule in value["rules"]],
                  "assessment": "paragraph_cues_not_expert_validation"}
            for key, value in PROFILES.items()
        },
        "statistics_tests": list(SUPPORTED_TESTS),
        "deterministic_toolkit": {"schema_version":"deterministic-toolkit/1.0", "extra":"toolkit",
                                  "backends":["SymPy","Pint","SciPy","spaCy","RapidFuzz"],
                                  "checks":["polynomial_identity","derivative","antiderivative","unit_conversion",
                                            "statistical_replay","claim_candidates","citation_match"],
                                  "candidate_results_are_proofs":False,"manuscript_access":"read_only",
                                  "findings_destination":"separate_user_report"},
        "structured_science_checks": ["semantic_ci", "dimension_equation", "unadjusted_risk_ratio"],
        "formal_logic": {"backend": "Z3", "extra": "logic", "package": "z3-solver==5.4.1.0",
                         "language": "Boolean and quantifier-free linear integer/real arithmetic",
                         "input": "explicit structured formulas; not automatic prose interpretation",
                         "manuscript_access": "read_only", "findings_destination": "separate_user_report"},
        "module_statuses": ["completed", "not_requested", "not_applicable", "unavailable", "failed"],
        "excluded_empirical_structure": {
            key: list(EMPIRICAL_STRUCTURE) for key in ("theoretical", "narrative-review")
        },
        "interfaces": {
            "cli": {"ocr": True, "page_vision": True},
            "python": {"ocr": True, "page_vision": True},
            "node": {"ocr": True, "page_vision": True},
            "mcp": {"ocr": False, "page_vision": False, "decoded_document_limit_bytes": 20 * 1024 * 1024,
                    "structured_spec_limit_bytes": 1024 * 1024, "response_limit_bytes": 2 * 1024 * 1024},
        },
        "limitations": [
            "Study type is caller-declared, not independently classified.",
            "Other scientific fields can use common checks; specialist coverage is limited to the listed profiles.",
            "Profile cues, arithmetic agreement and model interpretations are not scientific certification.",
            "Only English and Turkish editorial style rules are available; multilingual scientific terminology has uneven coverage.",
            "No independent multi-field expert-labeled accuracy estimate has been established.",
        ],
    }
    catalog["contract_sha256"] = hashlib.sha256(
        json.dumps(catalog, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return catalog
