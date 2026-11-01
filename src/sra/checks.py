import re

from sra.document import ParsedDocument
from sra.models import ClaimEvidenceCandidate, Finding

METHODS = ("method", "methodology", "materials and methods", "methods and materials",
           "yöntem", "materyal ve metot", "gereç ve yöntem")
LIMITATIONS = ("limitation", "limitations", "study limitations", "sınırlılık",
               "kısıtlılık", "çalışmanın sınırlılıkları")
REFERENCES = ("references", "bibliography", "kaynakça", "literature cited")
RESULTS = ("results", "findings", "results and discussion", "bulgular", "sonuçlar")
CONCLUSION = ("conclusion", "conclusions", "discussion", "general discussion",
              "sonuç", "sonuç ve tartışma", "tartışma")
OVERCLAIM = re.compile(
    r"\b(proves? conclusively|definitively proves?|undoubtedly proves?|"
    r"proves that|kanıtlamaktadır|kesin olarak kanıtlar|tartışmasız biçimde)\b",
    re.IGNORECASE,
)
CORRELATION = re.compile(
    r"\b(associated with|correlated with|correlation|relationship between|"
    r"ilişkilidir|ilişki göstermiş|korelasyon)\b", re.IGNORECASE
)
CAUSAL = re.compile(
    r"\b(causes?|caused|leads? to|resulted in|drives?|induces?|"
    r"neden olur|sebep olur|yol açar|neden olduğu)\b", re.IGNORECASE
)
CLAIM_MARKERS = re.compile(
    r"\b(show|shows|demonstrate|demonstrates|indicate|indicates|suggest|suggests|"
    r"support|supports|increased|decreased|associated|correlated|"
    r"göstermektedir|ortaya koymaktadır|bulgular|artırdı|azalttı|ilişkilidir|"
    r"desteklemektedir)\b", re.IGNORECASE
)
WORD = re.compile(r"[a-zA-Z0-9ğüşöçıİĞÜŞÖÇ]+", re.UNICODE)
STOP = set("""the and for with from that this these those were was are is be to of in on
at by as an a or we our it its their they them have has had after before between
over under into about than then also can may could should would study paper result
using used method data analysis which while where bir ve ile için bu şu olan olarak
göre daha çok az da de""".split())


def _norm_words(value: str) -> set[str]:
    return {w.lower() for w in WORD.findall(value) if len(w) > 2 and w.lower() not in STOP}


def _sentences(value: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", value) if s.strip()]


def _has_section(names: list[str], aliases: tuple[str, ...]) -> bool:
    return any(any(alias in name.lower().strip() for alias in aliases) for name in names)


def build_findings(document: ParsedDocument) -> tuple[list[Finding], list[ClaimEvidenceCandidate]]:
    names = list(document.sections)
    findings: list[Finding] = []
    if not _has_section(names, METHODS):
        findings.append(Finding(
            "structure.methods_missing", "Methods section not detected", "warning", "review_required",
            "No recognizable methods heading was detected. It may be present under another name.",
        ))
    if not _has_section(names, LIMITATIONS):
        findings.append(Finding(
            "structure.limitations_missing", "Limitations section not detected", "warning", "review_required",
            "No recognizable limitations heading was detected. Check whether limitations are discussed elsewhere.",
        ))
    if not _has_section(names, REFERENCES):
        findings.append(Finding(
            "structure.references_missing", "References section not detected", "info", "review_required",
            "No recognizable references heading was detected; citation completeness cannot be assessed.",
        ))

    overclaims = [s for s in _sentences(document.text) if OVERCLAIM.search(s)]
    if overclaims:
        findings.append(Finding(
            "language.absolute_claim", "Absolute or conclusive wording detected", "warning", "review_required",
            "These phrases may overstate what the evidence establishes. Inspect each claim in context.",
            overclaims[:5],
        ))

    association = [s for s in _sentences(document.text) if CORRELATION.search(s)]
    causal = [s for s in _sentences(document.text) if CAUSAL.search(s)]
    if association and causal:
        findings.append(Finding(
            "reasoning.correlation_causation_review",
            "Correlation/causation language requires contextual review", "warning", "review_required",
            "Both association and causal wording occur. This is a review signal, not proof of an inference error.",
            association[:2] + causal[:2],
        ))

    result_sections = [v for k, v in document.sections.items()
                       if any(alias in k.lower() for alias in RESULTS)]
    conclusion_sections = [v for k, v in document.sections.items()
                           if any(alias in k.lower() for alias in CONCLUSION)]
    result_sentences = [s for value in result_sections for s in _sentences(value)]
    conclusion_sentences = [s for value in conclusion_sections for s in _sentences(value)]
    candidates: list[ClaimEvidenceCandidate] = []
    for claim in conclusion_sentences:
        if not CLAIM_MARKERS.search(claim):
            continue
        claim_words = _norm_words(claim)
        best_sentence, best_score = None, 0.0
        for support in result_sentences:
            support_words = _norm_words(support)
            union = claim_words | support_words
            score = len(claim_words & support_words) / len(union) if union else 0.0
            if score > best_score:
                best_score, best_sentence = score, support
        candidates.append(ClaimEvidenceCandidate(
            claim=claim,
            candidate_support=best_sentence if best_score >= 0.08 else None,
            lexical_overlap=round(best_score, 3),
            interpretation="Lexical candidate only; semantic support and scientific validity are not verified.",
        ))
    return findings, candidates
