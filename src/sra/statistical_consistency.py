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
from sra.models import Finding

#: ``95% CI 1.2 to 3.4``, ``95% CI [1.2, 3.4]``, ``95% confidence interval 0.1–0.9``.
CONFIDENCE_INTERVAL = re.compile(
    r"95\s*%\s*(?:confidence\s+interval|CI)\s*[:=]?\s*[\[\(]?\s*"
    r"(?P<lower>[−\-]?\d+(?:[.·]\d+)?)\s*(?:,|;|to|—|–|-)\s*"
    r"(?P<upper>[−\-]?\d+(?:[.·]\d+)?)\s*[\]\)]?",
    re.IGNORECASE,
)

#: ``p = 0.03``, ``p < .001``, ``p ≤ 0.05``.
P_VALUE = re.compile(r"\bp\s*(?:-?\s*value\s*)?(?:=|==|<|>|≤|>=)\s*(?P<p>0?[.·]\d+|\d[.·]\d+)", re.IGNORECASE)

#: ``mean 3.4``, ``M = 3.4``, ``average 3.4``.
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
        is_ratio = bool(RATIO_STATEMENT.search(sentence))
        if not is_ratio and not CONTRAST_STATEMENT.search(sentence):
            # "mean age 45 (95% CI 30-60, p = 0.2)" describes a distribution, not a
            # tested contrast; the interval and the p-value answer different
            # questions and must not be compared.
            continue
        null = Decimal("1") if is_ratio else Decimal("0")
        excludes_null = lower > null or upper < null
        includes_null = lower <= null <= upper
        if p < Decimal("0.05") and includes_null:
            findings.append(_finding(
                "statistics.confidence_interval_p_conflict",
                "95% CI includes the null value while p is below 0.05",
                "The sentence reports a two-sided p below 0.05 and a 95% confidence "
                "interval that contains the null value. Both cannot describe the same "
                "test at the conventional threshold: confirm which numbers belong together.",
                sentence, line_number, "interval_includes_null",
            ))
        elif p >= Decimal("0.05") and excludes_null:
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
