"""Focused, source-grounded tests for the optional academic-writing reviewer."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sra.writing import audit_academic_writing, writing_report_markdown


def audit_text(text, **settings):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "article.md"
        path.write_text(text, encoding="utf-8")
        report = audit_academic_writing(path, **settings)
        assert report["source_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
        return report


def codes(result):
    return [entry["code"] for entry in result["findings"]]


class AcademicWritingTests(unittest.TestCase):
    def test_sample_flags_have_grounded_lines(self):
        path = Path(__file__).resolve().parents[1] / "examples/academic_writing_sample.md"
        report = audit_academic_writing(path, genre="original-research", abstract_max_words=5)
        self.assertEqual(report["tool"], "academic-writing-audit")
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertIn("abstract_above_limit", codes(report))
        self.assertIn("unmatched_numeric_citation", codes(report))
        self.assertIn("uncited_numbered_reference", codes(report))
        self.assertIn("editorial_placeholder", codes(report))
        self.assertIn("potential_overclaim", codes(report))
        self.assertNotIn("missing_section", codes(report))
        self.assertEqual(
            next(x["line"] for x in report["findings"] if x["code"] == "unmatched_numeric_citation"),
            5,
        )
        self.assertEqual(report["metrics"]["numbered_reference_entries"], 2)
        self.assertEqual(report["metrics"]["numeric_citation_keys"], 2)
        markdown = writing_report_markdown(report)
        self.assertIn("unmatched_numeric_citation (line 5)", markdown)

    def test_numbered_citations_range_and_matched_references(self):
        doc = (
            "# Introduction\nResults follow [1, 2-3] and [3].\n"
            "# References\n[1] First article.\n2. Second article.\n3) Third article.\n"
        )
        report = audit_text(doc)
        self.assertEqual(report["status"], "NO_AUTOMATED_FLAGS")
        self.assertEqual(report["metrics"]["numeric_citation_keys"], 3)
        self.assertEqual(report["metrics"]["numbered_reference_entries"], 3)

    def test_missing_numeric_and_uncited_reference(self):
        doc = (
            "# Methods\nCited [2] and also [1].\n"
            "# References\n[1] Present.\n[3] Uncited.\n"
        )
        report = audit_text(doc)
        self.assertEqual(codes(report), ["unmatched_numeric_citation", "uncited_numbered_reference"])
        self.assertEqual(report["findings"][0]["line"], 2)
        self.assertEqual(report["findings"][1]["line"], 5)

    def test_author_year_parenthetical_and_narrative(self):
        doc = (
            "# Introduction\n"
            "Smith (2020) observed a trend. (Jones, 2021; Adams et al., 2022) replicated it.\n"
            "# References\n"
            "Smith, J. (2020). Article.\n"
            "Jones, P. (2021). Article.\n"
            "Adams, M., & K. (2022). Article.\n"
        )
        report = audit_text(doc)
        self.assertEqual(report["status"], "NO_AUTOMATED_FLAGS")
        self.assertEqual(report["metrics"]["author_year_citation_keys"], 3)
        self.assertEqual(report["metrics"]["author_year_reference_entries"], 3)

    def test_author_year_missing_and_uncited(self):
        doc = (
            "# Introduction\n(Smith, 2020; Unknown, 2023)\n"
            "# References\nSmith, J. (2020). Present.\nOther, P. (2019). Uncited.\n"
        )
        report = audit_text(doc)
        self.assertEqual(codes(report), ["unmatched_author_year_citation", "uncited_author_year_reference"])

    def test_numeric_and_author_year_can_coexist(self):
        doc = (
            "# Introduction\nData [1] and (Smith, 2020) agree.\n"
            "# References\n[1] Dataset.\nSmith, J. (2020). Source.\n"
        )
        self.assertEqual(audit_text(doc)["status"], "NO_AUTOMATED_FLAGS")

    def test_duplicate_reference_identifiers(self):
        doc = (
            "# Introduction\nCites [1] and (Smith, 2020).\n"
            "# References\n[1] First.\n[1] Duplicate.\n"
            "Smith, J. (2020). A.\nSmith, M. (2020). B.\n"
        )
        report = audit_text(doc)
        self.assertIn("duplicate_reference_number", codes(report))
        self.assertIn("ambiguous_author_year_reference", codes(report))
        self.assertEqual(
            next(x["line"] for x in report["findings"] if x["code"] == "duplicate_reference_number"), 5
        )

    def test_citations_without_references_heading(self):
        report = audit_text("# Introduction\nCited [1] and (Smith, 2020).\n")
        self.assertIn("references_section_missing", codes(report))
        self.assertNotIn("unmatched_numeric_citation", codes(report))
        self.assertNotIn("unmatched_author_year_citation", codes(report))

    def test_unsupported_reference_style_is_marked_unverified(self):
        doc = "# Introduction\nCited [1].\n# References\nSmith Journal 2020 Article text.\n"
        report = audit_text(doc)
        self.assertIn("numeric_reference_format_unrecognized", codes(report))
        self.assertNotIn("unmatched_numeric_citation", codes(report))

    def test_original_research_sections_turkish(self):
        doc = (
            "# Özet\nÖrnek sonuç açıklaması.\n"
            "# Giriş\nAraştırmanın amacı.\n"
            "# Yöntemler\nÇalışma tasarımı.\n"
            "# Bulgular\nGözlem sonucu.\n"
            "# Tartışma\nSonuçların yorumu.\n"
            "# Kaynakça\n[1] Sample reference.\n"
        )
        report = audit_text(doc, genre="original-research")
        self.assertNotIn("missing_section", codes(report))
        self.assertIn("uncited_numbered_reference", codes(report))

    def test_general_genre_is_not_forced_to_imrad(self):
        doc = "# Notes\nA theoretical argument is presented here.\n"
        self.assertNotIn("missing_section", codes(audit_text(doc)))
        report = audit_text(doc, genre="original-research")
        self.assertEqual(codes(report).count("missing_section"), 6)
        markdown = writing_report_markdown(report)
        self.assertIn("missing_section (document)", markdown)

    def test_abstract_limits_configured_only(self):
        doc = "# Abstract\nFive countable scientific research writing tokens.\n"
        default = audit_text(doc)
        self.assertNotIn("abstract_below_limit", codes(default))
        self.assertNotIn("abstract_above_limit", codes(default))
        short = audit_text(doc, abstract_min_words=10)
        long = audit_text(doc, abstract_max_words=3)
        self.assertIn("abstract_below_limit", codes(short))
        self.assertIn("abstract_above_limit", codes(long))

    def test_invalid_user_settings_are_rejected(self):
        for value in (-1, True, 0.5, "200"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "non-negative integer"):
                    audit_text("# Abstract\nTest.\n", abstract_max_words=value)
        with self.assertRaisesRegex(ValueError, "cannot exceed"):
            audit_text("# Abstract\nTest.\n", abstract_min_words=250, abstract_max_words=150)
        with self.assertRaisesRegex(ValueError, "genre"):
            audit_text("# Abstract\nTest.\n", genre="guessed-journal")

    def test_fenced_code_is_not_considered_prose(self):
        doc = (
            "# Results\n"
            "  ~~~python\n"
            "# References\n"
            'TODO = "always [2]"\n'
            "  ~~~\n"
            "Actual measurements [1].\n"
            "# References\n[1] Valid reference.\n"
        )
        report = audit_text(doc)
        self.assertEqual(report["status"], "NO_AUTOMATED_FLAGS")

    def test_placeholder_and_overclaim_line_numbers(self):
        doc = (
            "# Introduction\nParagraph.\n"
            "# Results\nTODO: this proves everything always.\n"
        )
        report = audit_text(doc)
        codes_here = {x["code"]: x["line"] for x in report["findings"]}
        self.assertEqual(codes_here["editorial_placeholder"], 4)
        self.assertEqual(codes_here["potential_overclaim"], 4)

    def test_empty_unrecognized_or_irrelevant_citations_are_not_verified(self):
        report = audit_text("# Methods\nA mathematical vector [1, 2, 3] was recorded.\n")
        self.assertIn("references_section_missing", codes(report))
        self.assertNotIn("unmatched_numeric_citation", codes(report))

    def test_cli_writes_two_reports_and_no_source_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            manuscript = Path(tmp) / "input.md"
            manuscript.write_text("# Introduction\nCited [2].\n# References\n[1] Uncited.\n", encoding="utf-8")
            before = manuscript.read_bytes()
            output = Path(tmp) / "results" / "writing"
            run = subprocess.run(
                [
                    sys.executable, "-m", "sra.cli", "writing-audit", str(manuscript),
                    "--out", str(output), "--genre", "general",
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(manuscript.read_bytes(), before)
            result = json.loads(output.with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "REVIEW_REQUIRED")
            self.assertEqual(result["source_sha256"], hashlib.sha256(before).hexdigest())
            self.assertIn("Academic writing review", output.with_suffix(".md").read_text(encoding="utf-8"))

    def test_cli_rejects_input_overwrite_even_when_suffix_is_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            manuscript = Path(tmp) / "input.md"
            manuscript.write_text("# Results\nSafe original text.\n", encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable, "-m", "sra.cli", "writing-audit", str(manuscript),
                    "--out", str(Path(tmp) / "input"),
                ],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("must not overwrite", run.stderr)
            self.assertEqual(manuscript.read_text(encoding="utf-8"), "# Results\nSafe original text.\n")
            self.assertFalse((Path(tmp) / "input.json").exists())

    def test_invalid_citation_range_is_not_expanded(self):
        report = audit_text("# Introduction\nA bounded vector [10-40] was recorded.\n")
        self.assertEqual(report["metrics"]["numeric_citation_keys"], 0)
        self.assertEqual(report["status"], "NO_AUTOMATED_FLAGS")

    def test_zero_numeric_identifier_is_not_a_valid_citation(self):
        report = audit_text("# Introduction\nZero identifier [0] is not an accepted citation.\n")
        self.assertEqual(report["metrics"]["numeric_citation_keys"], 0)
        self.assertEqual(report["status"], "NO_AUTOMATED_FLAGS")

    def test_multiple_references_sections_are_detected(self):
        doc = (
            "# Introduction\nSupported [1] and [2].\n"
            "# References\n[1] First source.\n"
            "# References\n[2] Second source.\n"
        )
        report = audit_text(doc)
        self.assertIn("multiple_reference_sections", codes(report))
        self.assertNotIn("unmatched_numeric_citation", codes(report))

    def test_author_year_reference_format_unrecognized(self):
        report = audit_text(
            "# Introduction\n(Smith, 2020) suggested this.\n"
            "# References\nSmith et al. 2020. No parenthesized year.\n"
        )
        self.assertIn("author_year_reference_format_unrecognized", codes(report))
        self.assertNotIn("unmatched_author_year_citation", codes(report))

    def test_zero_flags_markdown_explains_scope(self):
        markdown = writing_report_markdown(audit_text("# Introduction\nNeutral sentence.\n"))
        self.assertIn("No automated flags in supported checks", markdown)
        self.assertIn("not a quality certification", markdown)

    def test_multiple_absolute_terms_on_one_line_yield_one_prompt(self):
        report = audit_text("# Discussion\nThis always proves and guarantees results.\n")
        self.assertEqual(codes(report).count("potential_overclaim"), 1)

    def test_markdown_report_escapes_untrusted_filename(self):
        result = audit_text("# Introduction\nSome text.\n")
        result["source"] = '<img src=x onerror=alert(1)>.md'
        markdown = writing_report_markdown(result)
        self.assertIn("&lt;img", markdown)
        self.assertNotIn("<img", markdown)


if __name__ == "__main__":
    unittest.main()
