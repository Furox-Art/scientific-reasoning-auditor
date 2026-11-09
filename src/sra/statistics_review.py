"""Statistics-review rules: multiplicity and design/test adequacy.

Two gaps the auditor used to leave entirely to a human reviewer:

1. A manuscript that reports several p-values and never says how multiplicity
   was handled. Nothing in the tool recalculated that, so a Results section with
   eleven unadjusted p-values read exactly like one with a single pre-specified
   test.
2. A design described as paired/repeated/within-subject paired with an
   independent-samples test name. The tool already recalculates Welch t-tests, so
   it can at least notice that the quoted test does not match the stated design.

Both are screening signals, not verdicts: they point at a sentence and ask for
adjudication.
"""

from __future__ import annotations

import re

from sra.document import without_fenced_code
from sra.models import Finding
from sra import multilingual as _multi

#: A reported p-value: ``p = 0.03``, ``p < .001``, ``p ≤ 0.05``, ``P-value 0.04``.
P_VALUE = re.compile(
    r"\bp\s*(?:-?\s*value\s*)?(?:=|==|<|>|≤|<=|>=)\s*0?\.\d+",
    re.IGNORECASE,
)

#: Any statement that multiplicity was addressed, including the test names that
#: adjust as part of their own procedure.
CORRECTION_VOCABULARY = re.compile(
    r"\b(?:bonferroni|holm(?:[-\s]bonferroni)?|šidák|sidak|tukey|scheffé|scheffe|"
    r"dunnett|benjamini[-\s]hochberg|benjamini|hochberg|false\s+discovery|fdr|"
    r"family[-\s]?wise|multiplicity|multiple[-\s]comparisons?|"
    r"adjust(?:ed|ment)?\s+(?:p|alpha)|corrected\s+(?:p|alpha)|"
    r"çoklu\s+karşılaştırma|düzeltilmiş\s+p)\b",
    re.IGNORECASE,
)

#: A design that makes an independent two-sample test the wrong default.
PAIRED_DESIGN = re.compile(
    r"\b(?:paired|pair[-\s]wise\s+(?:design|data)|repeated[-\s]measures?|"
    r"within[-\s]subjects?|pre[-\s]?(?:test|post)|before[-\s]and[-\s]after|"
    r"matched[-\s]pairs?|same\s+(?:participants|subjects|patients))\b|"
    r"eşleştirilmiş|tekrarlı ölçüm|aynı (?:hastalar|katılımcılar)",
    re.IGNORECASE,
)

#: Test names that assume independent groups.
INDEPENDENT_TEST = re.compile(
    r"\b(?:independent[-\s]samples?\s+t[-\s]?test|unpaired\s+t[-\s]?test|"
    r"two[-\s]sample\s+t[-\s]?test|student'?s?\s+t[-\s]?test|"
    r"mann[-\s]whitney(?:\s+u)?|wilcoxon[-\s]rank[-\s]sum)\b|"
    r"bağımsız örneklem t|bağımsız gruplar t",
    re.IGNORECASE,
)

#: The paired alternatives, whose presence means the manuscript did use one.
PAIRED_TEST = re.compile(
    r"\b(?:paired\s+t[-\s]?test|dependent\s+t[-\s]?test|wilcoxon\s+signed[-\s]rank|"
    r"repeated[-\s]measures\s+(?:anova|test))\b|"
    r"eşleştirilmiş t|bağımlı örneklem t",
    re.IGNORECASE,
)

#: Below this many reported p-values, an unmentioned correction is unremarkable.
_PHRASE_REVIEW = lambda terms: "|".join(re.escape(term) for term in terms)  # noqa: E731
CORRECTION_VOCABULARY = re.compile(
    CORRECTION_VOCABULARY.pattern
    + "|"
    + _PHRASE_REVIEW(_multi.CORRECTION)
    + "|"
    + _PHRASE_REVIEW(_multi.CORRECTION_PROPER_NOUNS),
    re.IGNORECASE,
)
PAIRED_DESIGN = re.compile(
    PAIRED_DESIGN.pattern + "|" + _PHRASE_REVIEW(_multi.PAIRED_DESIGN), re.IGNORECASE
)
INDEPENDENT_TEST = re.compile(
    INDEPENDENT_TEST.pattern + "|" + _PHRASE_REVIEW(_multi.INDEPENDENT_TEST), re.IGNORECASE
)
PAIRED_TEST = re.compile(
    PAIRED_TEST.pattern + "|" + _PHRASE_REVIEW(_multi.PAIRED_TEST), re.IGNORECASE
)

MINIMUM_UNCORRECTED_P_VALUES = 3


def _excerpt(text: str, position: int) -> str:
    return " ".join(text[max(0, position - 110):position + 90].split())


def _line(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def multiplicity_finding(text: str) -> Finding | None:
    """Report several reported p-values without any correction statement."""
    body = without_fenced_code(text)
    matches = list(P_VALUE.finditer(body))
    if len(matches) < MINIMUM_UNCORRECTED_P_VALUES:
        return None
    if CORRECTION_VOCABULARY.search(body):
        return None
    return Finding(
        "statistics.multiplicity_unaddressed",
        f"{len(matches)} reported p-values and no multiplicity statement",
        "warning",
        "review_required",
        "The manuscript reports "
        f"{len(matches)} p-values and never mentions an adjustment, a family of "
        "tests, or a test whose own procedure corrects for multiplicity. If these "
        "tests come from one family of hypotheses, the unadjusted thresholds "
        "overstate significance. Text screening cannot tell a pre-specified single "
        "test from eleven exploratory ones: confirm whether multiplicity applies.",
        evidence=[_excerpt(body, match.start()) for match in matches[:3]],
        evidence_locations=[
            {"line": _line(body, match.start()), "kind": "reported_p_value"}
            for match in matches[:3]
        ],
    )


def design_test_mismatch_finding(text: str) -> Finding | None:
    """Report an independent-samples test quoted for a paired design."""
    body = without_fenced_code(text)
    design = PAIRED_DESIGN.search(body)
    if design is None:
        return None
    independent = INDEPENDENT_TEST.search(body)
    if independent is None:
        return None
    if PAIRED_TEST.search(body):
        return None
    return Finding(
        "statistics.design_test_mismatch",
        "Independent-samples test quoted for a paired design",
        "warning",
        "review_required",
        "The Methods describe a paired, matched or repeated-measures design, and "
        "the reported test is an independent-samples test. If observations are "
        "paired, the independent test discards the pairing and its standard error "
        "is wrong for this design. Confirm which analysis was actually run.",
        evidence=[_excerpt(body, design.start()), _excerpt(body, independent.start())],
        evidence_locations=[
            {"line": _line(body, design.start()), "kind": "paired_design_wording"},
            {"line": _line(body, independent.start()), "kind": "independent_test_name"},
        ],
    )
