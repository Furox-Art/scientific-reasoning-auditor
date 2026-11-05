"""Small study-design-specific reporting cues, not reporting guideline certification.

Guideline texts are linked instead of reproduced. Presence of a keyword can
never establish that an item was adequately reported.
"""
from __future__ import annotations

import re
from typing import Any

from sra.document import ParsedDocument, without_fenced_code

# Original, deliberately abbreviated review cues. Do not present as official checklists.
CHECKLISTS: dict[str, dict[str, Any]] = {
    "clinical-trial": {
        "guideline": "CONSORT 2025",
        "url": "https://www.consort-spirit.org/",
        "items": [
            ("randomization", r"\brandomi[sz](?:ed|ation)|rastgele(?:\s+atama)?\b"),
            ("allocation", r"\ballocation|concealment|atama(?:\s+gizliliği)?\b"),
            ("trial_registration", r"\b(?:NCT\d{8}|ISRCTN\d+|trial registration|clinicaltrials\.gov|kayıt numarası)\b"),
            ("sample_size", r"\b(?:sample size|power analysis|örneklem büyüklüğü)\b"),
            ("harms", r"\b(?:adverse events?|harms?|safety|yan etki|advers olay)\b"),
        ],
    },
    "observational": {
        "guideline": "STROBE",
        "url": "https://www.strobe-statement.org/",
        "items": [
            ("design", r"\b(?:cohort|case.control|cross.sectional|observational|kohort|kesitsel)\b"),
            ("confounders", r"\b(?:confound(?:ing|ers?)|adjusted for|karıştırıcı)\b"),
            ("missing_data", r"\b(?:missing data|complete.case|imputation|eksik veri)\b"),
            ("eligibility", r"\b(?:eligib(?:le|ility)|inclusion criteria|exclusion criteria|dahil edilme)\b"),
            ("limitations", r"\b(?:limitations?|bias|sınırlılıklar|yanlılık)\b"),
        ],
    },
    "systematic-review": {
        "guideline": "PRISMA 2020",
        "url": "https://www.prisma-statement.org/prisma-2020",
        "items": [
            ("search_strategy", r"\b(?:search strategy|search terms|database search|arama stratejisi)\b"),
            ("eligibility", r"\b(?:eligib(?:le|ility)|inclusion criteria|exclusion criteria|dahil edilme)\b"),
            ("screening", r"\b(?:screen(?:ed|ing)|screening process|tarama süreci)\b"),
            ("risk_of_bias", r"\b(?:risk of bias|quality appraisal|yanlılık riski)\b"),
            ("registration", r"\b(?:PROSPERO|protocol registration|registered protocol|protokol kaydı)\b"),
        ],
    },
    "computational": {
        "guideline": "SRA reproducibility cues (not a formal standard)",
        "url": None,
        "items": [
            ("code_access", r"\b(?:code availability|source code|github\.com|kod erişimi)\b"),
            ("data_access", r"\b(?:data availability|dataset|data repository|veri seti)\b"),
            ("environment", r"\b(?:requirements\.txt|environment\.yml|conda|docker|dependencies|bağımlılıklar)\b"),
            ("evaluation", r"\b(?:benchmark|baseline|cross.validation|held.out|karşılaştırma)\b"),
            ("random_seed", r"\b(?:random seed|seed\s*=\s*\d+|deterministic|rastgele tohum)\b"),
        ],
    },
}


def reporting_cues(document: ParsedDocument, design: str) -> dict[str, Any]:
    if design not in CHECKLISTS:
        raise ValueError("design must be one of: " + ", ".join(CHECKLISTS))
    config = CHECKLISTS[design]
    text = without_fenced_code(document.text)
    findings = []
    for item_id, expression in config["items"]:
        pattern = re.compile(expression, re.IGNORECASE)
        match = pattern.search(text)
        # Presence indicates only a word/string was found; it cannot establish
        # adherence, completeness, appropriateness, or study quality.
        findings.append({
            "item": item_id,
            "status": "TEXT_CUE_FOUND" if match else "NOT_DETECTED_REVIEW_MANUALLY",
            "line": text.count("\n", 0, match.start()) + 1 if match else None,
            "excerpt": match.group(0) if match else None,
        })
    return {
        "design": design,
        "guideline": config["guideline"],
        "guideline_url": config["url"],
        "items": findings,
        "limitations": [
            "Not a reproduction or validation of the official guideline checklist.",
            "Keyword presence does not prove reporting quality or guideline compliance.",
            "Missing cues are not evidence that an item is actually absent.",
            "Human reviewers must examine study design, scientific content and original checklist.",
        ],
    }
