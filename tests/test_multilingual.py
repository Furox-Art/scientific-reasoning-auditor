"""Every listed term must actually reach the rule that lists it.

A multilingual table is worse than useless if a term is present but no rule ever
sees it: the report then looks clean on a Spanish or Japanese paper. These tests
walk the tables term by term and assert the matcher recognises each entry, then
build a manuscript out of one language's own listing to prove the pipeline runs
end to end without a hand-written sentence per language.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sra import multilingual as multi
from sra.audit import audit_file
from sra.checks import (
    CONCLUSION,
    CORRELATION,
    DECREASE,
    INCREASE,
    LIMITATIONS,
    METHODS,
    OVERCLAIM,
    REFERENCES,
    RESULTS,
    _heading_matches,
)
from sra.statistical_consistency import (
    CONTRAST_STATEMENT,
    GROUP_COUNT_PHRASE,
    MEAN,
    RATIO_STATEMENT,
)
from sra.statistics_review import (
    CORRECTION_VOCABULARY,
    INDEPENDENT_TEST,
    PAIRED_DESIGN,
    PAIRED_TEST,
    multiplicity_finding,
)

SECTIONS = (
    ("methods", METHODS),
    ("results", RESULTS),
    ("conclusion", CONCLUSION),
    ("limitations", LIMITATIONS),
    ("references", REFERENCES),
)

STRUCTURAL = (
    "structure.methods_missing",
    "structure.results_missing",
    "structure.conclusion_missing",
    "structure.limitations_missing",
    "structure.references_missing",
)


class SectionHeadingTests(unittest.TestCase):
    def test_every_listed_heading_matches_its_section(self):
        for category, aliases in SECTIONS:
            for heading in multi.SECTIONS[category]:
                with self.subTest(category=category, heading=heading):
                    self.assertTrue(
                        _heading_matches(heading, aliases),
                        f"{heading!r} is listed but does not match {category}",
                    )


class DirectionTests(unittest.TestCase):
    def test_every_listed_increase_term_is_in_the_pattern(self):
        for term in multi.INCREASE_LATIN + multi.INCREASE_CJK:
            with self.subTest(term=term):
                self.assertTrue(INCREASE.search(term))

    def test_every_listed_decrease_term_is_in_the_pattern(self):
        for term in multi.DECREASE_LATIN + multi.DECREASE_CJK:
            with self.subTest(term=term):
                self.assertTrue(DECREASE.search(term))


class WordLexiconTests(unittest.TestCase):
    def test_every_absolute_phrase_is_recognised(self):
        for term in multi.ABSOLUTE:
            with self.subTest(term=term):
                self.assertTrue(OVERCLAIM.search(term))

    def test_every_association_phrase_is_recognised(self):
        for term in multi.ASSOCIATION:
            with self.subTest(term=term):
                self.assertTrue(CORRELATION.search(term))

    def test_every_correction_phrase_clears_the_multiplicity_signal(self):
        without_correction = (
            "# Methods\nGroups were compared.\n"
            "# Results\nA differed (p = 0.01). B differed (p = 0.02). "
            "C differed (p = 0.03).\n"
        )
        self.assertIsNotNone(multiplicity_finding(without_correction))
        for term in multi.CORRECTION + multi.CORRECTION_PROPER_NOUNS:
            with self.subTest(term=term):
                self.assertTrue(CORRECTION_VOCABULARY.search(term))
                self.assertIsNone(multiplicity_finding(without_correction + f"{term}\n"))

    def test_every_paired_design_phrase_is_recognised(self):
        for term in multi.PAIRED_DESIGN:
            with self.subTest(term=term):
                self.assertTrue(PAIRED_DESIGN.search(term))

    def test_every_test_name_is_recognised(self):
        for term in multi.INDEPENDENT_TEST:
            with self.subTest(term=term):
                self.assertTrue(INDEPENDENT_TEST.search(term))
        for term in multi.PAIRED_TEST:
            with self.subTest(term=term):
                self.assertTrue(PAIRED_TEST.search(term))

    def test_every_mean_word_is_recognised(self):
        for term in multi.MEAN_WORD:
            with self.subTest(term=term):
                self.assertTrue(MEAN.search(f"{term} 4.1"))

    def test_every_contrast_and_ratio_phrase_is_recognised(self):
        for term in multi.CONTRAST:
            with self.subTest(term=term):
                self.assertTrue(CONTRAST_STATEMENT.search(term))
        for term in multi.RATIO_STATEMENT:
            with self.subTest(term=term):
                self.assertTrue(RATIO_STATEMENT.search(term))

    def test_every_group_count_phrase_is_recognised(self):
        for term in multi.GROUP_COUNT:
            with self.subTest(term=term):
                self.assertTrue(GROUP_COUNT_PHRASE.search(term))


class PipelineTests(unittest.TestCase):
    @staticmethod
    def _pick(terms: tuple[str, ...], index: int) -> str:
        return terms[index % len(terms)]

    def _manuscript(self, index: int) -> str:
        methods = self._pick(multi.SECTIONS["methods"], index)
        results = self._pick(multi.SECTIONS["results"], index)
        conclusion = self._pick(multi.SECTIONS["conclusion"], index)
        limitations = self._pick(multi.SECTIONS["limitations"], index)
        references = self._pick(multi.SECTIONS["references"], index)
        rising = self._pick(multi.INCREASE_LATIN + multi.INCREASE_CJK, index)
        falling = self._pick(multi.DECREASE_LATIN + multi.DECREASE_CJK, index)
        absolute = self._pick(multi.ABSOLUTE, index)
        return (
            f"# {methods}\nWe measured ten samples.\n"
            f"# {results}\nThe marker {rising} and then {falling} in the assay.\n"
            f"# {conclusion}\n{absolute}.\n"
            f"# {limitations}\nSmall sample.\n"
            f"# {references}\n1. Example et al. 2020.\n"
        )

    def test_ten_listings_produce_a_manuscript_without_structural_noise(self):
        for index in range(10):
            with self.subTest(index=index):
                with tempfile.TemporaryDirectory() as folder:
                    path = Path(folder) / "paper.md"
                    path.write_text(self._manuscript(index), encoding="utf-8", newline="")
                    findings = {finding.check_id for finding in audit_file(str(path)).findings}
                for structural in STRUCTURAL:
                    self.assertNotIn(
                        structural, findings, f"listing {index} lost a section heading"
                    )


if __name__ == "__main__":
    unittest.main()
