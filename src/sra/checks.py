import re
from collections.abc import Iterable
from decimal import Decimal

from sra.document import ParsedDocument, without_fenced_code
from sra.models import ClaimEvidenceCandidate, Finding
from sra.statistical_consistency import (
    confidence_interval_p_conflict,
    mean_outside_interval,
)
from sra.statistics_review import (
    design_test_mismatch_finding,
    multiplicity_finding,
)

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
    r"support|supports|increased|decreased|elevated|higher|greater|exceeds?|exceeded|"
    r"associated|correlated|causes?|caused|causing|"
    r"göstermektedir|ortaya koymaktadır|bulgular|artırdı|azalttı|ilişkilidir|"
    r"desteklemektedir|neden olur|yol açar)\b", re.IGNORECASE
)
OBSERVATIONAL_DESIGN = re.compile(
    r"\b(observational(?:ly)?|cross.sectional|case.control|retrospective|"
    r"non.randomi[sz]ed|survey study|registry study|cohort study)\b|"
    r"gözlemsel|kesitsel|vaka kontrol|geriye dönük|randomize olmayan",
    re.IGNORECASE,
)
# A review of published study designs must not automatically be treated as the
# review authors' *own* exposure/outcome cohort. This is deliberately narrow:
# absence of these markers does not prove a paper is primary observational work.
META_RESEARCH_DESIGN = re.compile(
    r"\b(?:meta[- ]research|research on research|methodological (?:study|review))\b",
    re.IGNORECASE,
)
OWN_OBSERVATIONAL_DESIGN = re.compile(
    r"\b(?:this|our|the present|the current)\s+(?:was\s+an?\s+|is\s+an?\s+)?"
    r"(?:cross[- ]sectional\s+)?(?:observational|retrospective|cohort|case[- ]control)"
    r"(?:\s+cohort)?\s+(?:study|design|analysis)\b"
    r"|\b(?:we|the investigators)\s+(?:conducted|performed|undertook|carried out)"
    r"\s+an?\s+(?:observational|retrospective|cohort|cross[- ]sectional)"
    r"(?:\s+cohort)?\s+(?:study|design|analysis)\b",
    re.IGNORECASE,
)
RANDOMIZED_DESIGN = re.compile(
    r"\b(?:we (?:used|conducted|performed) a randomi[sz]ed (?:design|trial|study|experiment)|"
    r"(?:this|our|the present|the current) randomi[sz]ed controlled (?:trial|study|experiment)|"
    r"(?:this|the present|the current) study was randomi[sz]ed|"
    r"the study used random allocation|participants in this study were randomly assigned|"
    r"(?:we|the investigators) randomly assigned (?:participants|patients|subjects|groups)|"
    r"random allocation to (?:treatment )?groups|random assignment to (?:treatment )?groups)\b|"
    r"bu çalışma randomize edildi|katılımcılar bu çalışmada rastgele atandı",
    re.IGNORECASE,
)
INCREASE = re.compile(
    r"\b(increas\w*|higher|greater|elevat\w*|improv\w*|raised|rise)\b|"
    r"\b(arttı|artırdı|artırma|artış|artıyor|artmıştır|yüksel\w*|daha yüksek)\b",
    re.IGNORECASE,
)
DECREASE = re.compile(
    r"\b(decreas\w*|lower|reduc\w*|declin\w*|worsen\w*|fell|fall|"
    r"azal\w*|düş\w*|gerile\w*|daha düşük)\b", re.IGNORECASE
)
WORD = re.compile(r"[a-zA-Z0-9ğüşöçıİĞÜŞÖÇ]+", re.UNICODE)
# This narrow, conservative check does not infer an outcome or scientific error:
# it compares repeated explicitly formatted rate ratios and intervals.
REPEATED_RATE_RATIO = re.compile(
    r"\brate\s+ratio(?:\s*\[\s*RR\s*\])?\s*[:=]?\s*"
    r"(?P<estimate>\d+(?:[.·]\d+)?)\s*;\s*"
    r"95\s*%\s*CI\s*"
    r"(?P<lower>\d+(?:[.·]\d+)?)\s*[-–—−]\s*"
    r"(?P<upper>\d+(?:[.·]\d+)?)\s*;\s*"
    r"p\s*=\s*(?P<p>\d+(?:[.·]\d+)?)",
    re.IGNORECASE,
)
DOSAGE_GROUP_MODIFIER = re.compile(r"\b(?:higher|lower)\s*[- ]?\s*(?:dose|dosage|dosing)\b", re.I)
STOP = set("""the and for with from that this these those were was are is be to of in on
at by as an a or we our it its their they them have has had after before between
over under into about than then also can may could should would study paper result
using used method data analysis which while where bir ve ile için bu şu olan olarak
göre daha çok az da de the study our results findings show showed demonstrates
demonstrated suggests suggested indicates indicated""".split())
NEGATION = re.compile(
    r"\b(?:not|never|no|without|didn't|doesn't|don't|cannot|can't|failed to|"
    r"değil|değildir|olmadı|olmamış|olamaz|yoktur|bulunmadı)\b",
    re.IGNORECASE,
)
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


_ABBREVIATIONS = {
    "dr.", "mr.", "mrs.", "ms.", "prof.", "fig.", "eq.", "ref.",
    "vol.", "no.", "vs.", "etc.", "e.g.", "i.e.", "et al.",
}


def _sentences(value: str, start_line: int = 1, section: str | None = None) -> list[dict]:
    """Keep source lines while protecting decimals and common abbreviations.

    This is a conservative rule-based segmenter, not a language-complete parser.
    """
    output: list[dict] = []
    for line_match in re.finditer(r"[^\r\n]+", value):
        line = line_match.group()
        # Nested Markdown headings are section metadata, not evidence text.
        if re.match(r"^\s{0,3}#{1,6}\s+", line):
            continue
        line_number = start_line + value.count("\n", 0, line_match.start())
        cursor = 0

        def append_until(end: int) -> None:
            nonlocal cursor
            sentence = line[cursor:end].strip()
            if sentence:
                output.append({"text": sentence, "line": line_number, "section": section})
            cursor = end

        for mark in re.finditer(r"[.!?]+(?=\s|$)", line):
            if mark.group().endswith("."):
                preceding = line[cursor:mark.end()].rstrip().casefold()
                if any(preceding.endswith(token) for token in _ABBREVIATIONS):
                    continue
                if re.search(r"(?:\b[a-z]\.){2,}$", preceding):
                    continue
            append_until(mark.end())
        append_until(len(line))
    return output


def _section_entries(document: ParsedDocument, aliases: tuple[str, ...]) -> list[dict]:
    entries = []
    for name, value in document.sections.items():
        if _heading_matches(name, aliases):
            entries.extend(_sentences(value, document.section_start_lines.get(name, 1), name))
    return entries


def _section_text(document: ParsedDocument, aliases: tuple[str, ...]) -> str:
    return "\n".join(
        value for name, value in document.sections.items()
        if _heading_matches(name, aliases)
    )


def _heading_matches(name: str, aliases: tuple[str, ...]) -> bool:
    normalized = re.sub(r"\s+", " ", name.lower().strip())
    normalized = re.sub(r"^(?:(?:\d+(?:\.\d+)*|[ivxlc]+)[.)]?\s+)", "", normalized)
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
        matched = best_sentence is not None and best_score >= 0.15
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
            claim_section=claim.get("section"),
            support_section=best_sentence.get("section") if matched and best_sentence else None,
            match_status="heuristic_candidate" if matched else "unmatched_review_required",
        ))
        if not matched:
            unmatched.append(claim)
    return candidates, unmatched


def _negation_in_scope(prefix: str) -> bool:
    # Do not carry negation across a new clause such as "but", "however" or ";"
    scoped_prefix = re.split(
        r"[;,]|\b(?:but|however|whereas|although|while)\b",
        prefix,
        flags=re.IGNORECASE,
    )[-1]
    return bool(NEGATION.search(scoped_prefix))


def _has_affirmed_direction(sentence: str, pattern: re.Pattern) -> bool:
    for match in pattern.finditer(sentence):
        prefix = sentence[max(0, match.start() - 50):match.start()]
        if re.search(r"\bnot\s+only\s*$", prefix, re.IGNORECASE):
            return True
        if not _negation_in_scope(prefix):
            return True
    return False


def _has_affirmed_match(sentence: str, pattern: re.Pattern) -> bool:
    for match in pattern.finditer(sentence):
        prefix = sentence[max(0, match.start() - 60):match.start()]
        if re.search(r"\bnot\s+only\s*$", prefix, re.IGNORECASE):
            return True
        if not _negation_in_scope(prefix):
            return True
    return False


def _has_affirmed_causal_language(sentence: str) -> bool:
    return _has_affirmed_match(sentence, CAUSAL)


def _direction(sentence: str) -> int:
    # Higher/lower *dose* is a treatment-arm description, not necessarily an
    # outcome direction. Preserve genuine verbs such as "increased mortality".
    outcome_text = DOSAGE_GROUP_MODIFIER.sub("dose", sentence)
    up = _has_affirmed_direction(outcome_text, INCREASE)
    down = _has_affirmed_direction(outcome_text, DECREASE)
    if up == down:
        return 0
    return 1 if up else -1


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _direction_conflicts(
    result_sentences: list[dict], conclusion_sentences: list[dict],
    limit: int = 5,
) -> list[dict]:
    """Flag opposite endpoint-level directions in contrastive clauses.

    Sharing only a generic intervention term never suffices for a conflict.
    """
    generic = {"treatment", "intervention", "exposure", "group", "patients"}

    def clauses(entry: dict) -> list[tuple[int, set[str]]]:
        parts = re.split(
            r";|\b(?:but|whereas|while)\b|"
            r"\band\b(?=\s+(?:increas\w*|decreas\w*|reduc\w*|higher|lower|improv\w*|worsen\w*))",
            entry["text"], flags=re.I,
        )
        result = []
        for part in parts:
            direction = _direction(part)
            terms = _norm_words(part, remove_direction=True) - generic
            if direction and terms:
                result.append((direction, terms))
        return result

    # Distinct named subgroups or measurement times are not same-scope
    # contradictions. Missing context on either side is ambiguous: do not
    # manufacture a conflict without a matching scope.
    def scope(text: str) -> tuple[str | None, str | None]:
        subgroup = re.search(r"\b(?:among|in|for)\s+(women|men|females?|males?)\b", text, re.I)
        timepoint = re.search(
            r"\b(?:on|at|after|by)\s+(day|week|month|year)\s+([a-z0-9]+)\b",
            text, re.I,
        )
        return (
            subgroup.group(1).lower() if subgroup else None,
            (timepoint.group(1) + ":" + timepoint.group(2)).lower() if timepoint else None,
        )

    conflicts: list[dict] = []
    seen: set[tuple[str, str, int | None, int | None]] = set()
    for result in result_sentences:
        for conclusion in conclusion_sentences:
            result_scope, conclusion_scope = scope(result["text"]), scope(conclusion["text"])
            if any((a or b) and a != b for a, b in zip(result_scope, conclusion_scope)):
                continue
            key = (
                result["text"], conclusion["text"],
                result.get("line"), conclusion.get("line"),
            )
            if key in seen:
                continue
            for result_direction, result_terms in clauses(result):
                for conclusion_direction, conclusion_terms in clauses(conclusion):
                    if result_direction == conclusion_direction:
                        continue
                    overlap = _jaccard(result_terms, conclusion_terms)
                    if result_terms & conclusion_terms and overlap >= 0.25:
                        seen.add(key)
                        conflicts.append({
                            "result": result,
                            "conclusion": conclusion,
                            "topic_overlap": round(overlap, 3),
                        })
                        if len(conflicts) >= limit:
                            return conflicts
                        break
                if key in seen:
                    break
    return conflicts


def _repeated_rate_ratio_ci_conflict(text: str) -> list[dict]:
    """First discordant 95% CI pair for a repeated rate ratio and p-value.

    This is a same-number screening signal. It cannot establish that the
    comparison, outcome or statistical method was the same.
    """
    first_by_estimate: dict[tuple[Decimal, Decimal], dict] = {}
    for match in REPEATED_RATE_RATIO.finditer(without_fenced_code(text)):
        number = lambda key: Decimal(match.group(key).replace("·", "."))
        key = number("estimate"), number("p")
        interval = number("lower"), number("upper")
        # Include nearby endpoint/population context for human adjudication.
        excerpt = " ".join(
            text[max(0, match.start() - 110):match.end() + 50].split()
        )
        entry = {
            "text": excerpt,
            "line": text.count("\n", 0, match.start()) + 1,
            "interval": interval,
        }
        earlier = first_by_estimate.get(key)
        if earlier is None:
            first_by_estimate[key] = entry
        elif earlier["interval"] != interval:
            return [earlier, entry]
    return []


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
    if not _has_section(names, RESULTS):
        findings.append(Finding(
            "structure.results_missing", "Results section not detected", "warning", "review_required",
            "No recognizable Results heading was detected; result-to-conclusion checks may be incomplete.",
        ))
    if not _has_section(names, CONCLUSION):
        findings.append(Finding(
            "structure.conclusion_missing", "Discussion/Conclusion section not detected", "warning", "review_required",
            "No recognizable Discussion or Conclusion heading was detected; claim extraction may be incomplete.",
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

    rate_ratio_discrepancy = _repeated_rate_ratio_ci_conflict(document.text)
    if rate_ratio_discrepancy:
        findings.append(Finding(
            "statistics.repeated_rate_ratio_ci_conflict",
            "Repeated rate ratio has inconsistent confidence intervals",
            "warning", "review_required",
            "The same displayed rate ratio and p-value occur with different "
            "95% confidence intervals. Confirm that both refer to the same "
            "endpoint, population, model and analysis before treating this "
            "as a reporting inconsistency.",
            [item["text"] for item in rate_ratio_discrepancy],
            [{"line": item["line"]} for item in rate_ratio_discrepancy],
        ))

    all_sentences = _sentences(without_fenced_code(document.text))
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
            "Discussion/Conclusion claims lack a lexical result candidate",
            "warning", "review_required",
            "No result sentence passed the lexical-overlap threshold for these Discussion/Conclusion claims. "
            "This is not proof of unsupported reasoning: paraphrase, cross-section evidence, or extraction "
            "failure may explain the mismatch.",
            [item["text"] for item in unmatched[:5]],
            [{"line": item["line"], "section": item.get("section")} for item in unmatched[:5]],
        ))

    association_claims = [s for s in conclusion_sentences if CORRELATION.search(s["text"])]
    association_anywhere = [s for s in all_sentences if CORRELATION.search(s["text"])]
    causal_claims = [
        s for s in conclusion_sentences
        if _has_affirmed_causal_language(s["text"])
    ]
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
            [{"line": s["line"], "section": s.get("section")} for s in association_claims[:2] + causal_claims[:2]],
        ))

    methods_text = _section_text(document, METHODS)
    method_entries = _section_entries(document, METHODS)
    method_evidence = next(
        (item for item in method_entries if OBSERVATIONAL_DESIGN.search(item["text"])),
        None,
    )
    # Exclude explicit negations and previous/unrelated trials from current-study
    # design claims. Ambiguous mixed designs require expert interpretation.
    def affirmed_current_randomization(text: str) -> bool:
        for match in RANDOMIZED_DESIGN.finditer(text):
            before = re.split(r"[.;:!?]", text[max(0, match.start() - 100):match.start()])[-1]
            after = text[match.end():match.end() + 120]
            if re.search(r"\b(?:no|not|never|without|denied|lacks?|lacking)\s*$",
                         before, flags=re.IGNORECASE):
                continue
            if re.match(r"\s*\?\s*(?:no|false|not)\b", after, flags=re.IGNORECASE):
                continue
            if re.match(r"\s+(?:years? earlier|previously|in (?:a|the) prior study)\b",
                        after, flags=re.IGNORECASE):
                continue
            if re.search(r"\bunrelated to (?:the|our) (?:current|present)\b",
                         after, flags=re.IGNORECASE):
                continue
            if (re.search(r"\b(?:unrelated|previous|prior|earlier|historical|separate)\b",
                          before, flags=re.IGNORECASE)
                    and re.search(r"\b(?:study|trial|dataset|experiment)\b",
                                  before, flags=re.IGNORECASE)):
                continue
            return True
        return False

    randomized_evidence = affirmed_current_randomization(methods_text)
    # "Reviewers screened observational studies" is not necessarily this
    # manuscript's own observational exposure design. Retain the warning when
    # the current manuscript explicitly identifies its own empirical design.
    observational_evidence = bool(OBSERVATIONAL_DESIGN.search(methods_text))
    observational_applicable = observational_evidence and (
        not META_RESEARCH_DESIGN.search(methods_text)
        or bool(OWN_OBSERVATIONAL_DESIGN.search(methods_text))
    )
    if causal_claims and observational_applicable and randomized_evidence:
        findings.append(Finding(
            "reasoning.mixed_design_causal_review",
            "Causal claim in a manuscript mentioning randomized and observational methods",
            "warning", "review_required",
            "Both randomized and observational design wording appear in Methods. "
            "Check which population, period, endpoint and identification assumptions "
            "apply to this causal claim; text screening cannot resolve mixed designs.",
            [causal_claims[0]["text"]],
            [{"line": causal_claims[0]["line"], "section": causal_claims[0].get("section")}],
        ))
    if causal_claims and observational_applicable and not randomized_evidence:
        method_excerpt = method_evidence["text"] if method_evidence else methods_text[:500]
        findings.append(Finding(
            "reasoning.causal_claim_observational_design",
            "Causal wording under a non-randomized observational design",
            "warning", "review_required",
            "The methods text contains observational/non-randomized design wording while the Discussion/Conclusion "
            "contains causal language. This is a high-priority review signal, not an automatic proof of "
            "invalidity; causal identification may rely on design features or assumptions not detected here.",
            [causal_claims[0]["text"], method_excerpt],
            [
                {"line": causal_claims[0]["line"], "section": causal_claims[0].get("section")},
                ({"line": method_evidence["line"], "section": method_evidence.get("section")}
                 if method_evidence else {"section": "Methods"}),
            ],
        ))

    # Request one extra candidate to detect and report truncation without
    # unbounded storage or exhaustive Cartesian output.
    conflict_probe = _direction_conflicts(result_sentences, conclusion_sentences, limit=6)
    conflicts = conflict_probe[:5]
    if len(conflict_probe) > 5:
        findings.append(Finding(
            "reasoning.directional_conflicts_truncated",
            "Additional possible directional conflicts omitted",
            "warning", "review_required",
            "At least six candidate result-conclusion conflicts were detected; "
            "only the first five are included in the evidence map. "
            "Further comparisons require separate review.",
        ))
    if conflicts:
        evidence = []
        locations = []
        for conflict in conflicts:
            evidence.extend([
                conflict["result"]["text"],
                conflict["conclusion"]["text"],
            ])
            locations.extend([
                {"line": conflict["result"]["line"], "section": conflict["result"].get("section")},
                {"line": conflict["conclusion"]["line"], "section": conflict["conclusion"].get("section")},
            ])
            reasoning_map.append({
                "relation": "possible_directional_contradiction",
                "results_line": conflict["result"]["line"],
                "results_sentence": conflict["result"]["text"],
                "conclusion_line": conflict["conclusion"]["line"],
                "conclusion_section": conflict["conclusion"].get("section"),
                "conclusion_sentence": conflict["conclusion"]["text"],
                "results_section": conflict["result"].get("section"),
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
            "claim_section": candidate.claim_section,
            "claim": candidate.claim,
            "candidate_support_line": candidate.support_line,
            "candidate_support_section": candidate.support_section,
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
    for statistics_signal in (multiplicity_finding(document.text),
                              design_test_mismatch_finding(document.text)):
        if statistics_signal is not None:
            findings.append(statistics_signal)
    for signal in (confidence_interval_p_conflict(document.text)
                   + mean_outside_interval(document.text)):
        findings.append(signal)
    return findings, candidates, reasoning_map
