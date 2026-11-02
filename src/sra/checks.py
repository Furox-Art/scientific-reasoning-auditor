import re
from collections.abc import Iterable

from sra.document import ParsedDocument
from sra.models import ClaimEvidenceCandidate, Finding

METHODS = ("method", "methods", "methodology", "materials and methods", "methods and materials",
           "yöntem", "materyal ve metot", "gereç ve yöntem")
LIMITATIONS = ("limitation", "limitations", "study limitations", "sınırlılık",
               "kısıtlılık", "çalışmanın sınırlılıkları")
REFERENCES = ("references", "bibliography", "kaynakça", "literature cited")
RESULTS = ("result", "results", "findings", "results and discussion", "bulgular", "sonuçlar")
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
    r"\b(causes?|caused|causing|leads? to|resulted in|drives?|induces?|"
    r"causal effect|has an effect on|neden olur|sebep olur|yol açar|neden olduğu|"
    r"etkisine neden)\b", re.IGNORECASE
)
CLAIM_MARKERS = re.compile(
    r"\b(show|shows|demonstrate|demonstrates|indicate|indicates|suggest|suggests|"
    r"support|supports|increased|decreased|associated|correlated|causes?|"
    r"göstermektedir|ortaya koymaktadır|bulgular|artırdı|azalttı|ilişkilidir|"
    r"desteklemektedir|neden olur|yol açar)\b", re.IGNORECASE
)
OBSERVATIONAL_DESIGN = re.compile(
    r"\b(observational|cross.sectional|case.control|retrospective|"
    r"non.randomi[sz]ed|survey study|registry study|cohort study)\b|"
    r"gözlemsel|kesitsel|vaka kontrol|geriye dönük|randomize olmayan",
    re.IGNORECASE,
)
RANDOMIZED_DESIGN = re.compile(
    r"\b(randomi[sz]ed|random allocation|random assignment|randomized controlled)\b|"
    r"rastgele atama|randomize kontrollü|randomize edildi",
    re.IGNORECASE,
)
INCREASE = re.compile(
    r"\b(increas\w*|higher|greater|elevat\w*|improv\w*|raised|rise|"
    r"art\w*|yüksel\w*|daha yüksek)\b", re.IGNORECASE
)
DECREASE = re.compile(
    r"\b(decreas\w*|lower|reduc\w*|declin\w*|worsen\w*|fell|fall|"
    r"azal\w*|düş\w*|gerile\w*|daha düşük)\b", re.IGNORECASE
)
WORD = re.compile(r"[a-zA-Z0-9ğüşöçıİĞÜŞÖÇ]+", re.UNICODE)
STOP = set("""the and for with from that this these those were was are is be to of in on
at by as an a or we our it its their they them have has had after before between
over under into about than then also can may could should would study paper result
using used method data analysis which while where bir ve ile için bu şu olan olarak
göre daha çok az da de the study our results findings show showed demonstrates
demonstrated suggests suggested indicates indicated""".split())
DIRECTION_WORDS = {
    "increase", "increased", "increasing", "higher", "greater", "elevated", "improved",
    "raised", "rise", "decrease", "decreased", "decreasing", "lower", "reduced",
    "declined", "worsened", "fell", "fall", "arttı", "artırdı", "artırma", "azaldı",
    "azalttı", "düştü", "yükseldi", "geriledi",
}


def _norm_words(value: str, remove_direction: bool = False) -> set[str]:
    words = {w.lower() for w in WORD.findall(value)}
    return {
        w for w in words
        if len(w) > 2 and w not in STOP and not (remove_direction and w in DIRECTION_WORDS)
    }


def _sentences(value: str, start_line: int = 1) -> list[dict]:
    output: list[dict] = []
    for match in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", value):
        sentence = match.group().strip()
        if sentence:
            output.append({
                "text": sentence,
                "line": start_line + value.count("\n", 0, match.start()),
            })
    return output


def _section_entries(document: ParsedDocument, aliases: tuple[str, ...]) -> list[dict]:
    entries = []
    for name, value in document.sections.items():
        if _heading_matches(name, aliases):
            entries.extend(_sentences(value, document.section_start_lines.get(name, 1)))
    return entries


def _section_text(document: ParsedDocument, aliases: tuple[str, ...]) -> str:
    return "\n".join(
        value for name, value in document.sections.items()
        if _heading_matches(name, aliases)
    )


def _heading_matches(name: str, aliases: tuple[str, ...]) -> bool:
    normalized = re.sub(r"\s+", " ", name.lower().strip())
    return any(
        normalized == alias or normalized.startswith(alias + " ")
        or normalized.startswith(alias + ":") or normalized.startswith(alias + "(")
        for alias in aliases
    )


def _has_section(names: Iterable[str], aliases: tuple[str, ...]) -> bool:
    return any(_heading_matches(name, aliases) for name in names)


def _candidate_links(
    result_sentences: list[dict], conclusion_sentences: list[dict]
) -> tuple[list[ClaimEvidenceCandidate], list[dict]]:
    candidates: list[ClaimEvidenceCandidate] = []
    unmatched: list[dict] = []
    for claim in conclusion_sentences:
        if not CLAIM_MARKERS.search(claim["text"]):
            continue
        claim_words = _norm_words(claim["text"])
        best_sentence: dict | None = None
        best_score = 0.0
        for support in result_sentences:
            support_words = _norm_words(support["text"])
            union = claim_words | support_words
            score = len(claim_words & support_words) / len(union) if union else 0.0
            if score > best_score:
                best_score, best_sentence = score, support
        matched = best_sentence is not None and best_score >= 0.08
        candidates.append(ClaimEvidenceCandidate(
            claim=claim["text"],
            candidate_support=best_sentence["text"] if matched and best_sentence else None,
            lexical_overlap=round(best_score, 3),
            interpretation=(
                "Lexical candidate only; semantic entailment and scientific validity are not verified."
                if matched else
                "No lexical candidate was found; paraphrase, omitted results, or absent support require human review."
            ),
            claim_line=claim["line"],
            support_line=best_sentence["line"] if matched and best_sentence else None,
            match_status="heuristic_candidate" if matched else "unmatched_review_required",
        ))
        if not matched:
            unmatched.append(claim)
    return candidates, unmatched


def _direction(sentence: str) -> int:
    up = bool(INCREASE.search(sentence))
    down = bool(DECREASE.search(sentence))
    if up == down:
        return 0
    return 1 if up else -1


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _direction_conflicts(
    result_sentences: list[dict], conclusion_sentences: list[dict]
) -> list[dict]:
    conflicts: list[dict] = []
    for result in result_sentences:
        result_direction = _direction(result["text"])
        if result_direction == 0:
            continue
        result_topic = _norm_words(result["text"], remove_direction=True)
        if len(result_topic) < 2:
            continue
        for conclusion in conclusion_sentences:
            conclusion_direction = _direction(conclusion["text"])
            if conclusion_direction == 0 or conclusion_direction == result_direction:
                continue
            conclusion_topic = _norm_words(conclusion["text"], remove_direction=True)
            overlap = _jaccard(result_topic, conclusion_topic)
            if overlap >= 0.25 and len(result_topic & conclusion_topic) >= 2:
                conflicts.append({
                    "result": result,
                    "conclusion": conclusion,
                    "topic_overlap": round(overlap, 3),
                })
    return conflicts[:5]


def build_findings(
    document: ParsedDocument,
) -> tuple[list[Finding], list[ClaimEvidenceCandidate], list[dict]]:
    names = list(document.sections)
    findings: list[Finding] = []
    reasoning_map: list[dict] = []

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

    all_sentences = _sentences(document.text)
    overclaims = [s for s in all_sentences if OVERCLAIM.search(s["text"])]
    if overclaims:
        findings.append(Finding(
            "language.absolute_claim", "Absolute or conclusive wording detected", "warning", "review_required",
            "These phrases may overstate what the evidence establishes. Inspect each claim in context.",
            [s["text"] for s in overclaims[:5]],
            [{"line": s["line"]} for s in overclaims[:5]],
        ))

    result_sentences = _section_entries(document, RESULTS)
    conclusion_sentences = _section_entries(document, CONCLUSION)
    candidates, unmatched = _candidate_links(result_sentences, conclusion_sentences)

    if unmatched:
        findings.append(Finding(
            "reasoning.conclusion_without_lexical_candidate",
            "Conclusion claims lack a lexical result candidate",
            "warning", "review_required",
            "No result sentence passed the lexical-overlap threshold for these conclusion claims. "
            "This is not proof of unsupported reasoning: paraphrase, cross-section evidence, or extraction "
            "failure may explain the mismatch.",
            [item["text"] for item in unmatched[:5]],
            [{"line": item["line"], "section": "conclusion"} for item in unmatched[:5]],
        ))

    association_claims = [s for s in conclusion_sentences if CORRELATION.search(s["text"])]
    association_anywhere = [s for s in all_sentences if CORRELATION.search(s["text"])]
    causal_claims = [s for s in conclusion_sentences if CAUSAL.search(s["text"])]
    if association_anywhere and causal_claims:
        findings.append(Finding(
            "reasoning.correlation_causation_review",
            "Association and causal language both occur in the manuscript",
            "warning", "review_required",
            "Association wording appears somewhere in the manuscript while the conclusion uses causal "
            "language. Verify that the study design and identification strategy support the causal claim.",
            [association_anywhere[0]["text"], causal_claims[0]["text"]],
            [{"line": association_anywhere[0]["line"]}, {"line": causal_claims[0]["line"], "section": "conclusion"}],
        ))
    if association_claims and causal_claims:
        findings.append(Finding(
            "reasoning.association_and_causal_claims",
            "Association and causal wording both occur in the conclusion",
            "warning", "review_required",
            "Association language and causal language appear in the conclusion. Check whether the design "
            "and identification assumptions justify the causal interpretation.",
            [s["text"] for s in association_claims[:2] + causal_claims[:2]],
            [{"line": s["line"], "section": "conclusion"} for s in association_claims[:2] + causal_claims[:2]],
        ))

    methods_text = _section_text(document, METHODS)
    if causal_claims and OBSERVATIONAL_DESIGN.search(methods_text) and not RANDOMIZED_DESIGN.search(methods_text):
        findings.append(Finding(
            "reasoning.causal_claim_observational_design",
            "Causal conclusion in a non-randomized observational design",
            "warning", "review_required",
            "The methods text contains observational/non-randomized design wording while the conclusion "
            "contains causal language. This is a high-priority review signal, not an automatic proof of "
            "invalidity; causal identification may rely on design features or assumptions not detected here.",
            [causal_claims[0]["text"], methods_text[:500]],
            [
                {"line": causal_claims[0]["line"], "section": "conclusion"},
                {"section": "methods", "excerpt": methods_text[:500]},
            ],
        ))

    conflicts = _direction_conflicts(result_sentences, conclusion_sentences)
    if conflicts:
        evidence = []
        locations = []
        for conflict in conflicts:
            evidence.extend([
                "Results: " + conflict["result"]["text"],
                "Conclusion: " + conflict["conclusion"]["text"],
            ])
            locations.extend([
                {"line": conflict["result"]["line"], "section": "results"},
                {"line": conflict["conclusion"]["line"], "section": "conclusion"},
            ])
            reasoning_map.append({
                "relation": "possible_directional_contradiction",
                "results_line": conflict["result"]["line"],
                "results_sentence": conflict["result"]["text"],
                "conclusion_line": conflict["conclusion"]["line"],
                "conclusion_sentence": conflict["conclusion"]["text"],
                "topic_overlap": conflict["topic_overlap"],
                "status": "heuristic_review_required",
            })
        findings.append(Finding(
            "reasoning.directional_contradiction",
            "Possible result–conclusion direction conflict",
            "warning", "review_required",
            "A result sentence and a conclusion sentence share topic terms but use opposite direction "
            "language. Check metric definitions, subgroup scope, coding direction, and context manually.",
            evidence[:10], locations[:10],
        ))

    for candidate in candidates:
        reasoning_map.append({
            "relation": "lexical_support_candidate" if candidate.candidate_support else "no_lexical_candidate",
            "claim_line": candidate.claim_line,
            "claim": candidate.claim,
            "candidate_support_line": candidate.support_line,
            "candidate_support": candidate.candidate_support,
            "overlap": candidate.lexical_overlap,
            "status": candidate.match_status,
        })

    if not candidates:
        reasoning_map.append({
            "relation": "conclusion_claim_extraction",
            "status": "no_claims_extracted",
            "note": "No conclusion sentences matched the current claim-marker lexicon.",
        })
    return findings, candidates, reasoning_map
