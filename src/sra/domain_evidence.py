"""Discipline-specific, paragraph-grounded evidence candidate screening.

No keyword match, including a multi-signal paragraph match, establishes
scientific adequacy or checklist compliance. Human adjudication is mandatory.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sra.document import ParsedDocument, load_document

_METHODS = ("methods", "methodology", "materials and methods", "method", "yöntem",
            "yöntemler", "gereç ve yöntem", "materyal ve metot")
_RESULTS = ("results", "findings", "bulgular", "sonuçlar")
_DISCUSSION = ("discussion", "tartışma", "conclusion", "sonuç", "limitations")


@dataclass(frozen=True)
class EvidenceRule:
    key: str
    question: str
    sections: tuple[str, ...]
    signals: tuple[tuple[str, str], ...]


def _rule(key: str, question: str, sections: tuple[str, ...],
          **signals: str) -> EvidenceRule:
    return EvidenceRule(key, question, sections, tuple(signals.items()))


PROFILES: dict[str, dict[str, Any]] = {
    "clinical": {
        "source": "CONSORT 2025; SRA original, abbreviated screening questions",
        "source_url": "https://www.bmj.com/content/389/bmj-2024-081123",
        "rules": (
            _rule("ethics_identifier", "Is ethics approval identifiable by an approval identifier?",
                  _METHODS, approval=r"\b(?:ethics|IRB|ethical approval|etik kurul)\b",
                  identifier=r"\b(?:approval|protocol|IRB|reference|no\.?|number|sayı)\s*[:#\-]?\s*[A-Z0-9/-]*\d+[A-Z0-9/-]*\b"),
            _rule("allocation_method", "Is a random allocation method described?",
                  _METHODS, allocation=r"\b(?:randomi[sz]|rastgele atam)\w*",
                  method=r"\b(?:computer.generated|sequence|block random|stratif|opaque envelope|allocation concealment|blok random)\w*"),
            _rule("adverse_event_counts", "Are adverse-event data quantified?",
                  _RESULTS, events=r"\b(?:adverse events?|side effects?|serious harms?|yan etkiler?)\b",
                  count=r"\b(?:n\s*=\s*\d+|\d+\s*(?:patients?|cases?|participants?|olgu|hasta)|\d+(?:\.\d+)?\s*%)"),
            _rule("primary_outcome_timing", "Is a primary outcome linked to an assessment time?",
                  _METHODS + _RESULTS, endpoint=r"\b(?:primary outcome|primary endpoint|birincil sonlanım)\b",
                  time=r"\b(?:at\s+\d+\s*(?:days?|weeks?|months?)|day\s*\d+|week\s*\d+|follow.up at|hafta\s*\d+)"),
        ),
    },
    "animal": {
        "source": "ARRIVE 2.0 Essential 10; SRA original, abbreviated screening questions",
        "source_url": "https://arriveguidelines.org/arrive-guidelines",
        "rules": (
            _rule("experimental_unit", "Is the experimental unit specified?",
                  _METHODS, unit=r"\b(?:experimental unit|deney birimi)\b",
                  example=r"\b(?:animal|mouse|mice|rat|litter|cage|hayvan|kafes)\b"),
            _rule("group_sample_size", "Are experimental groups quantified?",
                  _METHODS + _RESULTS, group=r"\b(?:control|treatment|group|sham|vehicle|kontrol|grup)\b",
                  sample=r"\b(?:n\s*=\s*\d+|\d+\s*(?:mice|rats|animals|hayvan))\b"),
            _rule("blinding_role", "Is who was blinded identifiable?",
                  _METHODS, blind=r"\b(?:blind(?:ed|ing)?|mask(?:ed|ing)?|körleme)\b",
                  role=r"\b(?:assessor|analyst|experimenter|investigator|observer|değerlendirici)\b"),
            _rule("randomization_details", "Is allocation randomization method described?",
                  _METHODS, random=r"\b(?:randomi[sz]|rastgele)\w*",
                  method=r"\b(?:sequence|computer|number generator|block|allocation|atama)\b"),
        ),
    },
    "physics": {
        "source": "NIST uncertainty guidance; SRA original, abbreviated screening questions",
        "source_url": "https://www.nist.gov/itl/sed/topic-areas/measurement-uncertainty",
        "rules": (
            _rule("quantified_uncertainty", "Is a measurement reported with a quantitative uncertainty?",
                  _METHODS + _RESULTS, uncertainty=r"(?:±|\buncertainty\b|\bbelirsizlik\b)",
                  numeric=r"(?:±\s*\d+(?:\.\d+)?|\b\d+(?:\.\d+)?\s*(?:%|percent)\b)"),
            _rule("instrument_calibration", "Is instrument calibration documented with a reference?",
                  _METHODS, calibration=r"\b(?:calibrat\w*|kalibras\w*)",
                  reference=r"\b(?:reference|standard|traceab|NIST|ISO|sertifikalı|referans)\b"),
            _rule("repeated_measurements", "Are repeated measurements quantified?",
                  _METHODS + _RESULTS, repeats=r"\b(?:repeated|replicate|measurement|ölçüm|tekrar)\w*",
                  count=r"\b(?:n\s*=\s*\d+|\d+\s*(?:times|runs|measurements|repetitions|ölçüm))\b"),
        ),
    },
    "chemistry": {
        "source": "SRA original chemical analytical reproducibility questions",
        "source_url": None,
        "rules": (
            _rule("analytical_purity", "Is analytical purity reported quantitatively with a technique?",
                  _METHODS + _RESULTS, assay=r"\b(?:HPLC|GC-MS|GCMS|NMR|chromatograph\w*|kromatograf\w*)",
                  purity=r"\b(?:purity|saflık)\b",
                  value=r"\b\d+(?:\.\d+)?\s*%"),
            _rule("calibration_concentrations", "Is calibration tied to a quantitative concentration?",
                  _METHODS, calibration=r"\b(?:calibration|calibrated|kalibrasyon)\b",
                  concentration=r"\b\d+(?:\.\d+)?\s*(?:mg/?mL|µg/?mL|ug/?mL|mmol/?L|mol/?L|ppm)\b"),
            _rule("quantified_yield", "Is reaction or extraction yield reported with a value?",
                  _RESULTS, yield_term=r"\b(?:yield|recovery|verim|geri kazanım)\b",
                  fraction=r"\b\d+(?:\.\d+)?\s*%"),
        ),
    },
    "computing": {
        "source": "SRA original machine-learning and reproducibility review questions",
        "source_url": None,
        "rules": (
            _rule("split_and_leakage", "Is data splitting discussed alongside leakage prevention?",
                  _METHODS, split=r"\b(?:train(?:ing)?[- ]test|train(?:ing)?[- ]validation|held[- ]out|data split|veri böl)\w*",
                  leakage=r"\b(?:leakage|overlap|patient.level|subject.level|sızıntı|veri kaçağı)\b"),
            _rule("baseline_and_metric", "Is a baseline compared using a named evaluation metric?",
                  _METHODS + _RESULTS, baseline=r"\b(?:baseline|benchmark|karşılaştırma modeli)\b",
                  metric=r"\b(?:accuracy|precision|recall|F1|AUROC|AUC|RMSE|MAE|BLEU|doğruluk)\b"),
            _rule("seed_and_environment", "Is randomness specified alongside the software environment?",
                  _METHODS, seed=r"(?:\bseed\s*[:=]\s*\d+\b|\brandom seed\b|\brastgele tohum\b)",
                  environment=r"\b(?:Python\s*\d|PyTorch|TensorFlow|CUDA|version|sürüm|Docker|conda)\b"),
            _rule("data_and_code_access", "Are both code and data access paths described?",
                  _METHODS + _DISCUSSION + ("data availability",), code=r"\b(?:source code|code repository|github\.com|kod deposu)\b",
                  data=r"\b(?:dataset|data availability|data repository|veri seti|veri deposu)\b"),
        ),
    },
    "social-science": {
        "source": "STROBE and SRA original social-science transparency questions",
        "source_url": "https://www.strobe-statement.org/",
        "rules": (
            _rule("sampling_and_n", "Is sampling described with an explicit sample size?",
                  _METHODS, sampling=r"\b(?:sampling|recruitment|participants|sampled|örneklem|katılımcı)\b",
                  count=r"\b(?:n\s*=\s*\d+|\d+\s*(?:participants|respondents|subjects|katılımcı))\b"),
            _rule("confounding_strategy", "Is a confounding strategy linked to named variables?",
                  _METHODS, confounding=r"\b(?:confound|adjusted for|covariates|control variables|karıştırıcı)\b",
                  variables=r"\b(?:age|sex|income|education|baseline|yaş|gelir|eğitim)\b"),
            _rule("consent_and_approval", "Is consent discussed alongside research ethics review?",
                  _METHODS, consent=r"\b(?:informed consent|participant consent|aydınlatılmış onam)\b",
                  ethics=r"\b(?:ethics|IRB|ethical approval|etik kurul)\b"),
        ),
    },
}


# Additional multi-signal field prompts. Every item still requires human
# assessment; the software does not reproduce full professional checklists.
_EXTRAS: dict[str, tuple[EvidenceRule, ...]] = {
    "clinical": (
        _rule("sample_size_rationale", "Is sample-size planning linked to a numerical target?",
              _METHODS, rationale=r"\b(?:power calculation|power analysis|sample size estimation|güç analizi)\b",
              target=r"\b(?:n\s*=\s*\d+|\d+\s+(?:participants|patients|subjects|hasta))\b"),
        _rule("missing_data_strategy", "Is a strategy for missing data described?",
              _METHODS, missing=r"\b(?:missing data|missing values|eksik veri)\b",
              strategy=r"\b(?:imputation|complete.case|multiple imputation|duyarlılık analizi)\b"),
        _rule("effect_confidence_interval", "Are effect estimates accompanied by uncertainty?",
              _RESULTS, effect=r"\b(?:risk ratio|odds ratio|hazard ratio|mean difference|effect size|etki büyüklüğü)\b",
              interval=r"\b(?:95\s*%?\s*CI|confidence interval|güven aralığı)\b"),
    ),
    "animal": (
        _rule("species_sex_age", "Are animal species, sex and age disclosed together?",
              _METHODS, species=r"\b(?:mouse|mice|rat|rabbit|zebrafish|fare|sıçan)\b",
              sex=r"\b(?:male|female|sex|erkek|dişi)\b",
              age=r"\b(?:age|aged|weeks old|months old|yaş|haftalık)\b"),
        _rule("animal_ethics_approval", "Is animal ethics approval linked to an identifier?",
              _METHODS, ethics=r"\b(?:animal ethics|animal care|IACUC|etik kurul)\b",
              identifier=r"\b(?:approval|protocol|number|no\.?|sayı)\s*[:#-]?\s*[A-Z0-9/-]*\d+"),
        _rule("outcome_dispersion", "Is variation quantified for reported experimental outcomes?",
              _RESULTS, center=r"\b(?:mean|median|ortalama|medyan)\b",
              variability=r"\b(?:SD|SEM|IQR|standard deviation|confidence interval|standart sapma)\b"),
    ),
    "physics": (
        _rule("uncertainty_propagation", "Is an uncertainty propagation approach linked to component sources?",
              _METHODS, propagation=r"\b(?:error propagation|uncertainty propagation|belirsizlik yayılımı)\b",
              components=r"\b(?:correlation|covariance|Monte Carlo|type A|type B|kovaryans)\b"),
        _rule("instrument_resolution", "Is instrument resolution specified quantitatively?",
              _METHODS, resolution=r"\b(?:resolution|precision|çözünürlük)\b",
              value=r"\b\d+(?:\.\d+)?\s*(?:nm|µm|mm|ms|Hz|mV|V|T|mT|K)\b"),
        _rule("boundary_conditions", "Are boundary conditions identified with their constraints?",
              _METHODS, boundary=r"\b(?:boundary condition|initial condition|sınır koşulu|başlangıç koşulu)\b",
              constraint=r"(?:\b(?:fixed|periodic|Dirichlet|Neumann|zero flux|sabit)\b|=\s*\d+)"),
    ),
    "chemistry": (
        _rule("nmr_characterization", "Does NMR characterization identify acquisition conditions?",
              _METHODS, method=r"\b(?:NMR|nuclear magnetic resonance)\b",
              setting=r"(?:\b\d+\s*MHz\b|\b(?:CDCl3|DMSO-d6|solvent)\b)"),
        _rule("detection_limit", "Is an analytical detection limit quantified?",
              _METHODS + _RESULTS, limit=r"\b(?:LOD|limit of detection|tespit sınırı)\b",
              amount=r"\b\d+(?:\.\d+)?\s*(?:ng/?mL|µg/?mL|mg/?L|ppm|ppb)\b"),
        _rule("replicate_precision", "Are analytical replicates linked to a variability measure?",
              _METHODS + _RESULTS, replicate=r"\b(?:triplicate|replicates|duplicate|tekrar ölçüm)\b",
              variation=r"\b(?:RSD|relative standard deviation|CV|coefficient of variation)\b"),
    ),
    "computing": (
        _rule("hyperparameter_reporting", "Is a hyperparameter specified with its value?",
              _METHODS, parameter=r"\b(?:learning rate|dropout rate|weight decay|batch size|öğrenme oranı)\b",
              value=r"(?:\b\d+(?:\.\d+)?(?:e-?\d+)?\b|\b\d+\s*(?:epochs|iterations)\b)"),
        _rule("heldout_external_evaluation", "Are external evaluation results quantified?",
              _RESULTS, external=r"\b(?:external validation|held.out test|out.of.distribution|harici doğrulama)\b",
              metric=r"\b(?:AUROC|F1|accuracy|precision|recall|RMSE|MAE|doğruluk)\b"),
        _rule("reproducible_software_version", "Are software/runtime versions tied to a named framework?",
              _METHODS, framework=r"\b(?:PyTorch|TensorFlow|scikit.learn|Python|CUDA|R version)\b",
              version=r"\b(?:v?\d+\.\d+(?:\.\d+)?|version|sürüm)\b"),
    ),
    "social-science": (
        _rule("scale_reliability", "Is a named instrument linked to a reliability coefficient?",
              _METHODS + _RESULTS, reliability=r"\b(?:Cronbach|McDonald|omega|internal consistency|iç tutarlılık)\b",
              numeric=r"\b(?:alpha|α|ω|omega)\s*[:=]?\s*0?\.\d+\b"),
        _rule("missing_responses", "Are missing responses linked to a handling strategy?",
              _METHODS, missing=r"\b(?:missing responses|missing data|non.response|eksik veri)\b",
              handling=r"\b(?:imputation|complete.case|weighted|sensitivity analysis|çoklu atama)\b"),
        _rule("robustness_check", "Is a sensitivity analysis linked to an adjusted result?",
              _RESULTS + _DISCUSSION, sensitivity=r"\b(?:sensitivity analysis|robustness check|duyarlılık analizi)\b",
              result=r"\b(?:adjusted|estimate|effect|OR|RR|estimate|tahmin|etki)\b"),
    ),
}
for _field, _additional in _EXTRAS.items():
    PROFILES[_field]["rules"] = (*PROFILES[_field]["rules"], *_additional)


def _normalize_heading(value: str) -> str:
    return re.sub(r"\s+\(\d+\)$", "", value.strip().casefold())


def _paragraphs(document: ParsedDocument, sections: tuple[str, ...]):
    from sra.writing import _HEADING_GROUPS
    exclude = _HEADING_GROUPS["references"]
    for heading, body in document.sections.items():
        normalized = _normalize_heading(heading)
        if normalized in exclude:
            continue
        if sections and normalized not in sections:
            continue
        start_line = document.section_start_lines[heading]
        # Existing parser already strips fenced code and only returns prose.
        for paragraph in re.finditer(r"[^\n]+(?:\n(?!\n)[^\n]+)*", body):
            source = paragraph.group(0).strip()
            if source:
                yield {
                    "section": heading,
                    "line": start_line + body.count("\n", 0, paragraph.start()),
                    "text": source,
                }


def review_domain(document: ParsedDocument, discipline: str) -> dict[str, Any]:
    if discipline not in PROFILES:
        raise ValueError("Unknown discipline. Choose one of: " + ", ".join(PROFILES))
    profile = PROFILES[discipline]
    entries: list[dict[str, Any]] = []
    for rule in profile["rules"]:
        paragraphs = list(_paragraphs(document, rule.sections))
        signal_hits = {name: 0 for name, _ in rule.signals}
        candidates = []
        for paragraph in paragraphs:
            matches = {}
            for name, expression in rule.signals:
                match = re.search(expression, paragraph["text"], flags=re.IGNORECASE)
                if match:
                    signal_hits[name] += 1
                    matches[name] = match.group(0)
            if len(matches) == len(rule.signals) and len(candidates) < 3:
                candidates.append({
                    "section": paragraph["section"],
                    "line": paragraph["line"],
                    "excerpt": paragraph["text"][:280],
                    "matched_signals": matches,
                })
        if candidates:
            status = "TEXTUAL_EVIDENCE_CANDIDATE"
        elif any(signal_hits.values()):
            status = "PARTIAL_CUES_REVIEW_MANUALLY"
        else:
            status = "NOT_DETECTED_REVIEW_MANUALLY"
        entries.append({
            "rule_id": rule.key,
            "review_question": rule.question,
            "status": status,
            "searched_sections": list(rule.sections) or ["all prose sections"],
            "signal_hit_counts": signal_hits,
            "evidence": candidates,
            "expert_assessment": "REQUIRED",
        })
    ruleset = [
        {"key": rule.key, "sections": rule.sections, "signals": rule.signals}
        for rule in profile["rules"]
    ]
    return {
        "schema_version": "1.0",
        "discipline": discipline,
        "guidance": profile["source"],
        "guidance_url": profile["source_url"],
        "source_sha256": document.sha256,
        "ruleset_sha256": hashlib.sha256(
            json.dumps(ruleset, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
        "items": entries,
        "summary": {
            "textual_candidates": sum(x["status"] == "TEXTUAL_EVIDENCE_CANDIDATE" for x in entries),
            "partial_cues": sum(x["status"] == "PARTIAL_CUES_REVIEW_MANUALLY" for x in entries),
            "no_detected_cues": sum(x["status"] == "NOT_DETECTED_REVIEW_MANUALLY" for x in entries),
            "expert_verified_items": 0,
        },
        "limitations": [
            "Evidence candidates are literal paragraph co-occurrences, not validated scientific reasoning.",
            "A missing candidate does not establish a reporting omission or research deficiency.",
            "Expert reviewers must check adequacy, applicability, contradictions, measurements, and original standards.",
            "Rules are abbreviated original heuristics, not complete official reporting guideline checklists.",
        ],
    }


def audit_domain_file(path: str, discipline: str) -> dict[str, Any]:
    document = load_document(path)
    return review_domain(document, discipline)
