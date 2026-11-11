"""Sentence-scoped consistency checks on reported statistics.

A number can be perfectly recomputed from its own summary statistics and still
contradict the interval printed next to it: a 95% CI that excludes zero paired
with p = 0.31, or a mean that sits outside its own confidence interval. The audit
recalculated what it was handed; it never compared the numbers to each other.

These checks stay deliberately small. They fire only inside one sentence, only
when both numbers are present, and they quote the sentence for adjudication.
"""

from __future__ import annotations

import re
from decimal import Decimal

from sra.document import without_fenced_code
from sra import multilingual as _multi
from sra.models import Finding

#: ``95% CI 1.2 to 3.4``, ``95% CI [1.2, 3.4]``, ``95% confidence interval 0.1–0.9``.
CONFIDENCE_INTERVAL = re.compile(
    r"95\s*%\s*(?:confidence\s+interval|CI)\s*[:=]?\s*[\[\(]?\s*"
    r"(?P<lower>[−\-]?\d+(?:[.·]\d+)?)\s*(?:,|;|to|—|–|-)\s*"
    r"(?P<upper>[−\-]?\d+(?:[.·]\d+)?)\s*[\]\)]?",
    re.IGNORECASE,
)

#: ``p = 0.03``, ``p < .001``, ``p ≤ 0.05``.
P_VALUE = re.compile(r"\bp\s*(?:-?\s*value\s*)?(?P<op>==|<=|>=|≤|≥|=|<|>)\s*(?P<p>0?[.·]\d+|\d[.·]\d+)", re.IGNORECASE)

#: ``mean 3.4``, ``M = 3.4``, ``average 3.4``.
#: The same lexicons in the other publishing languages. A mean word, a contrast
#: word, a ratio measure and a group count all have to be recognised whatever the
#: manuscript's language, or the checks quietly do nothing.

MEAN = re.compile(
    # "mean score was 4.1", "M = 4.1", "average of 4.1": at most a couple of words
    # may sit between the keyword and the value, and never a bracket or comma, so
    # the number still has to be the one the sentence reports as its mean.
    r"\b(?:mean|average|ortalamas?ı)\b[^.;:()]{0,24}?"
    r"(?P<mean>[−\-]?\d+(?:[.·]\d+)?)(?!\s*%)",
    re.IGNORECASE,
)


#: A statement whose null value is 1 rather than 0 (ratios, odds, hazards).
RATIO_STATEMENT = re.compile(
    r"\b(?:odds\s+ratio|risk\s+ratio|hazard\s+ratio|rate\s+ratio|relative\s+risk|"
    r"OR|RR|HR|risk\s+difference\s+ratio)\b",
    re.IGNORECASE,
)

#: Wording that makes a CI a statement about a contrast or an effect, whose
#: interval can be checked against a p-value. A descriptive mean with a CI (age,
#: score, weight) carries no implied test, so the pair is not compared.
CONTRAST_STATEMENT = re.compile(
    r"\b(?:difference|effect|increase|decrease|reduction|change|compared|versus|vs\.?|"
    r"higher|lower|greater|smaller|associated|association|estimate|coefficient|"
    r"odds\s+ratio|risk\s+ratio|hazard\s+ratio|rate\s+ratio|relative\s+risk|"
    r"fark|etki|artış|azalma|ilişki)\b",
    re.IGNORECASE,
)

#: How far apart a mean and a CI bound may be before the pair is called a conflict.
MEAN_TOLERANCE = Decimal("0.0005")


def _number(value: str) -> Decimal:
    return Decimal(value.replace("·", ".").replace("−", "-"))


def _sentences(text: str) -> list[tuple[str, int]]:
    """Split into sentences, keeping the line the sentence starts on."""
    sentences: list[tuple[str, int]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            if sentence.strip():
                sentences.append((sentence, line_number))
    return sentences


def _finding(
    check_id: str,
    title: str,
    message: str,
    sentence: str,
    line_number: int,
    kind: str,
) -> Finding:
    return Finding(
        check_id,
        title,
        "warning",
        "review_required",
        message,
        evidence=[" ".join(sentence.split())],
        evidence_locations=[{"line": line_number, "kind": kind}],
    )


#: ``p = 0.03`` (an equality claim) and ``p < .001`` (a bound), captured loosely
#: and validated numerically: regexes that try to encode "a probability" in the
P_EQUALS = re.compile(r"\bp\s*(?:-?\s*value\s*)?(?:==|=)\s*(?P<value>-?\s*\d+(?:\.\d+)?)", re.IGNORECASE)
P_INEQUALITY = re.compile(r"\bp\s*(?P<op><=|>=|<|>)\s*(?P<value>-?\s*\d+(?:\.\d+)?)", re.IGNORECASE)


def _ascii_math(text: str) -> str:
    return (
        text.replace(chr(0x2212), "-")
        .replace(chr(0x00B7), ".")
        .replace(chr(0x2264), "<=")
        .replace(chr(0x2265), ">=")
    )


def _impossible_p(sentence: str) -> bool:
    normalised = _ascii_math(sentence)
    for match in P_EQUALS.finditer(normalised):
        value = _number(match.group("value").replace(" ", ""))
        if value <= 0 or value > 1:
            return True
    for match in P_INEQUALITY.finditer(normalised):
        value = _number(match.group("value").replace(" ", ""))
        op = match.group("op")
        if (op == "<" and value <= 0) or (op == "<=" and value < 0):
            return True
        if (op == ">" and value >= 1) or (op == ">=" and value > 1):
            return True
    return False


def impossible_p_value(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for sentence, line_number in _sentences(without_fenced_code(text)):
        if not _impossible_p(sentence):
            continue
        findings.append(_finding(
            "statistics.impossible_p_value",
            "Reported p-value is not a usable probability",
            "The p-value in this sentence is rounded to zero, above one, or negative. "
            "Report the exact value (for example p < 0.001) so a reader can tell a very "
            "small p from a transcription error.",
            sentence, line_number, "impossible_p_value",
        ))
    return findings


IMPOSSIBLE_DISPERSION = re.compile(
    r"\b(?:SD|S\.D\.|standard\s+deviation|SE|S\.E\.|standard\s+error|SEM)\s*"
    r"(?:=|was|of|:)\s*(?P<negative>-\s*\d+(?:\.\d+)?)"
    r"|\b(?:n|N|sample\s+size)\s*(?:=|of|was|:)\s*(?P<zero>0)\b",
    re.IGNORECASE,
)
GROUP_COUNT = re.compile(
    r"\b(?P<count>three|four|five|six|seven|eight|3|4|5|6|7|8)\s+(?:study\s+)?"
    r"(?:groups?|arms?|cohorts?|conditions?|doses?|treatments?)\b",
    re.IGNORECASE,
)
_PHRASE = lambda terms: "|".join(re.escape(term) for term in terms)  # noqa: E731
MEAN = re.compile(
    r"(?:\b(?:mean|average|ortalamas?ı)\b|" + _PHRASE(_multi.MEAN_WORD)
    + r")[^.;:()]{0,24}?(?P<mean>[−\-]?\d+(?:[.·]\d+)?)(?!\s*%)",
    re.IGNORECASE,
)
CONTRAST_STATEMENT = re.compile(
    CONTRAST_STATEMENT.pattern + "|" + _PHRASE(_multi.CONTRAST), re.IGNORECASE
)
RATIO_STATEMENT = re.compile(
    RATIO_STATEMENT.pattern + "|" + _PHRASE(_multi.RATIO_STATEMENT), re.IGNORECASE
)
GROUP_COUNT_PHRASE = re.compile(_PHRASE(_multi.GROUP_COUNT), re.IGNORECASE)

PAIRWISE_TEST = re.compile(
    r"\b(?:t[\s-]?tests?|independent[\s-]samples?\s+t|paired\s+t|mann[\s-]whitney|"
    r"wilcoxon\s+rank[\s-]sum|chi[\s-]square\s+test)\b",
    re.IGNORECASE,
)
OMNIBUS_TEST = re.compile(
    r"\b(?:ANOVA|ANCOVA|MANOVA|Kruskal[\s-]Wallis|Friedman|mixed[\s-]effects?|"
    r"linear\s+model|multilevel|hierarchical\s+model|Tukey|Dunnett|Bonferroni|"
    r"Holm|Benjamini|false\s+discovery|FDR)\b",
    re.IGNORECASE,
)


def impossible_dispersion(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for sentence, line_number in _sentences(without_fenced_code(text)):
        if IMPOSSIBLE_DISPERSION.search(_ascii_math(sentence)) is None:
            continue
        findings.append(_finding(
            "statistics.impossible_dispersion",
            "Reported dispersion or sample size cannot exist",
            "The sentence reports a negative standard deviation or standard error, or a "
            "sample size of zero. Neither can come from a real analysis, so the text "
            "needs correcting before any inference is read from it.",
            sentence, line_number, "impossible_dispersion",
        ))
    return findings


def group_count_test_mismatch(text: str) -> list[Finding]:
    findings: list[Finding] = []
    for sentence, line_number in _sentences(without_fenced_code(text)):
        count = GROUP_COUNT.search(sentence)
        if count is None:
            # "tres grupos", "drei Gruppen", "三组": the phrase itself carries the
            # count, so it needs no separately parsed number.
            count = GROUP_COUNT_PHRASE.search(sentence)
        if count is None or PAIRWISE_TEST.search(sentence) is None:
            continue
        if OMNIBUS_TEST.search(sentence):
            continue
        findings.append(_finding(
            "statistics.group_count_test_mismatch",
            "Three or more groups compared with pairwise tests only",
            "The sentence describes three or more groups and names only a pairwise test. "
            "Repeated pairwise tests across many groups inflate the family-wise error "
            "rate and cannot show that the groups differ overall; an omnibus test, or an "
            "explicitly adjusted set of contrasts, is what the design calls for.",
            sentence, line_number, "pairwise_only",
        ))
    return findings


def confidence_interval_p_conflict(text: str) -> list[Finding]:
    """Flag a sentence whose 95% CI and p-value disagree about the null."""
    findings: list[Finding] = []
    for sentence, line_number in _sentences(without_fenced_code(text)):
        interval = CONFIDENCE_INTERVAL.search(sentence)
        p_value = P_VALUE.search(sentence)
        if interval is None or p_value is None:
            continue
        lower = _number(interval.group("lower"))
        upper = _number(interval.group("upper"))
        p = _number(p_value.group("p"))
        op = p_value.group("op")
        if op in {"≤", "≥"}:
            op = "<=" if op == "≤" else ">="
        alpha = Decimal("0.05")
        below_alpha = ((op in {"=", "=="} and p < alpha)
                       or (op == "<" and p <= alpha)
                       or (op == "<=" and p < alpha))
        at_or_above_alpha = ((op in {"=", "=="} and p >= alpha)
                             or (op in {">", ">="} and p >= alpha))
        is_ratio = bool(RATIO_STATEMENT.search(sentence))
        if not is_ratio and not CONTRAST_STATEMENT.search(sentence):
            # "mean age 45 (95% CI 30-60, p = 0.2)" describes a distribution, not a
            # tested contrast; the interval and the p-value answer different
            # questions and must not be compared.
            continue
        null = Decimal("1") if is_ratio else Decimal("0")
        excludes_null = lower > null or upper < null
        includes_null = lower <= null <= upper
        if below_alpha and includes_null:
            findings.append(_finding(
                "statistics.confidence_interval_p_conflict",
                "95% CI includes the null value while p is below 0.05",
                "The sentence reports a two-sided p below 0.05 and a 95% confidence "
                "interval that contains the null value. Both cannot describe the same "
                "test at the conventional threshold: confirm which numbers belong together.",
                sentence, line_number, "interval_includes_null",
            ))
        elif at_or_above_alpha and excludes_null:
            findings.append(_finding(
                "statistics.confidence_interval_p_conflict",
                "95% CI excludes the null value while p is at or above 0.05",
                "The sentence reports a p at or above 0.05 and a 95% confidence "
                "interval that excludes the null value. Recompute both from the same "
                "analysis, or state that the interval is adjusted differently.",
                sentence, line_number, "interval_excludes_null",
            ))
    return findings


def mean_outside_interval(text: str) -> list[Finding]:
    """Flag a sentence whose reported mean falls outside its own 95% CI."""
    findings: list[Finding] = []
    for sentence, line_number in _sentences(without_fenced_code(text)):
        interval = CONFIDENCE_INTERVAL.search(sentence)
        mean = MEAN.search(sentence)
        if interval is None or mean is None:
            continue
        lower = _number(interval.group("lower"))
        upper = _number(interval.group("upper"))
        centre = _number(mean.group("mean"))
        if lower - MEAN_TOLERANCE <= centre <= upper + MEAN_TOLERANCE:
            continue
        findings.append(_finding(
            "statistics.mean_outside_confidence_interval",
            "Reported mean falls outside its own 95% CI",
            "The mean in this sentence lies outside the 95% confidence interval in "
            "the same sentence. A two-sided interval for a mean contains the estimate "
            "by construction, so one of the two numbers is mislabelled or copied from "
            "another analysis.",
            sentence, line_number, "mean_outside_interval",
        ))
    return findings
