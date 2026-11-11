"""K1 independent findings F1/F2/F3: source-specific corrective regressions.

These tests intentionally verify difficult cases missed by the earlier green suite.
"""
from __future__ import annotations

import hashlib
import resource
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from sra.document import load_document
from sra.paper_review import SYNTHESIS_FIELDS, _chunks, _validated_chunk, paper_review_markdown
from sra.pdf_visual import _resource_limiter


class MixedPageOCRTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "test.pdf"
        self.path.write_bytes(b"%PDF-synthetic-unit")
        self.native = "Native clinical trial title with more than twenty characters."

    def fake_reader(self, image_count=1, inventory_fails=False):
        native = self.native

        class FakePage:
            @property
            def images(self):
                if inventory_fails:
                    raise ValueError("corrupt image XObject")
                return [object()] * image_count

            def extract_text(self, **_kwargs):
                return native

        pypdf = ModuleType("pypdf")
        pypdf.PdfReader = lambda stream: SimpleNamespace(pages=[FakePage()])
        return pypdf

    def test_native_heading_and_raster_text_are_both_preserved(self):
        with patch.dict(sys.modules, {"pypdf": self.fake_reader()}), patch(
            "sra.pdf_visual.ocr_pdf_page",
            return_value=self.native + "\nSCANNED_TOKEN_742",
        ) as ocr:
            report = load_document(self.path, pdf_ocr_mode="missing")
        ocr.assert_called_once()
        self.assertIn(self.native, report.text)
        self.assertIn("SCANNED_TOKEN_742", report.text)
        self.assertEqual(report.extraction_details["ocr_pages"], [1])
        rec = report.extraction_details["page_records"][0]
        self.assertEqual(rec["method"], "native+tesseract")
        self.assertEqual(rec["embedded_image_count"], 1)
        self.assertEqual(report.sha256, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_exact_native_duplicate_line_is_not_repeated(self):
        with patch.dict(sys.modules, {"pypdf": self.fake_reader()}), patch(
            "sra.pdf_visual.ocr_pdf_page", return_value=self.native,
        ):
            report = load_document(self.path, pdf_ocr_mode="missing")
        self.assertEqual(report.text, self.native)
        self.assertEqual(
            report.extraction_details["page_records"][0]["method"],
            "native+ocr_checked",
        )

    def test_mathematical_symbol_differences_in_ocr_are_not_silently_dropped(self):
        scientific_cases = [
            ("p < 0.05", "p > 0.05"),
            ("x = 0", "x ≠ 0"),
            ("15 ± 3", "15 − 3"),
            ("a × b", "a ÷ b"),
            ("risk = 0.5", "risk = −0.5"),
        ]
        for native_value, ocr_value in scientific_cases:
            with self.subTest(native=native_value, ocr=ocr_value):
                self.native = "This synthetic scientific manuscript states " + native_value + " clearly."
                visual = "This synthetic scientific manuscript states " + ocr_value + " clearly."
                with patch.dict(sys.modules, {"pypdf": self.fake_reader()}), patch(
                    "sra.pdf_visual.ocr_pdf_page", return_value=visual,
                ):
                    document = load_document(self.path, pdf_ocr_mode="missing")
                self.assertIn(self.native, document.text)
                self.assertIn(visual, document.text)
                self.assertEqual(document.extraction_details["page_records"][0]["method"],
                                 "native+tesseract")

    def test_no_images_and_good_native_text_avoids_ocr(self):
        with patch.dict(sys.modules, {"pypdf": self.fake_reader(image_count=0)}), patch(
            "sra.pdf_visual.ocr_pdf_page"
        ) as ocr:
            report = load_document(self.path, pdf_ocr_mode="missing")
        ocr.assert_not_called()
        self.assertEqual(report.extraction_details["ocr_pages"], [])
        self.assertEqual(report.extraction_details["page_records"][0]["embedded_image_count"], 0)

    def test_corrupt_image_inventory_fails_closed_in_default_mode(self):
        with patch.dict(sys.modules, {"pypdf": self.fake_reader(inventory_fails=True)}):
            with self.assertRaisesRegex(ValueError, "image inventory"):
                load_document(self.path, pdf_ocr_mode="missing")
            doc = load_document(self.path, pdf_ocr_mode="off")
        self.assertEqual(doc.extraction_details["page_records"][0]["embedded_image_count"], 0)


class PhysicalPageQuoteTests(unittest.TestCase):
    @staticmethod
    def review(quote, part):
        response = {
            "explanation": "Evidence needs scientific interpretation.",
            "main_points": [],
            "critiques": [{
                "issue": "Evidence spans multiple pages.",
                "reason": "Attribution must cover the whole quoted range.",
                "recommendation": "Inspect the source pages.",
                "quote": quote, "severity": "medium",
            }],
        }
        return _validated_chunk(response, part)["critiques"][0]

    @staticmethod
    def markdown(critique):
        result = {
            "source": "paper.pdf", "source_sha256": "a"*64, "model": "test",
            "covered_characters": 60, "extracted_characters": 60,
            "chunks_reviewed": 1, "chunk_count": 1,
            "synthesis": {field: "Scientific interpretation remains uncertain." for field in SYNTHESIS_FIELDS},
            "chunk_analyses": [{
                "chunk_id": 1, "start_line": 1, "end_line": 3,
                "explanation": "Review", "main_points": [], "critiques": [critique],
            }],
            "rule_based_findings": [], "limitations": ["Model interpretations unverified"],
        }
        return paper_review_markdown(result)

    def test_quote_crossing_two_pages_reports_both(self):
        first = "about control."
        second = "The second page begins"
        quote = first + "\n\n" + second
        manuscript = quote + " and continues with the methods."
        part = _chunks(manuscript, 2000)[0]
        part["page_records"] = [
            {"page": 1, "start_char": 0, "end_char": len(first)},
            {"page": 2, "start_char": len(first)+2, "end_char": len(manuscript)},
        ]
        evidence = self.review(quote, part)
        self.assertEqual(evidence["source_pages"], [1, 2])
        self.assertIsNone(evidence["source_page"])
        self.assertEqual(evidence["source_end_char_offset"], len(quote))
        self.assertIn("pages 1, 2", self.markdown(evidence))

    def test_repeated_quote_does_not_claim_specific_line(self):
        quote = "A repeated scientific observation was made."
        part = _chunks(quote + "\n" + quote, 2000)[0]
        critique = self.review(quote, part)
        self.assertEqual(critique["quote_ambiguity_count"], 2)
        self.assertIsNone(critique["line"])
        markdown = self.markdown(critique)
        self.assertIn("line ambiguous", markdown)
        self.assertNotIn("line 1:", markdown)

    def test_repeated_quote_is_not_misidentified_as_unique(self):
        quote = "A repeated scientific observation was made."
        manuscript = quote + "\n\n" + quote
        part = _chunks(manuscript, 2000)[0]
        part["page_records"] = [
            {"page": 1, "start_char": 0, "end_char": len(quote)},
            {"page": 2, "start_char": len(quote)+2, "end_char": len(manuscript)},
        ]
        evidence = self.review(quote, part)
        self.assertEqual(evidence["quote_ambiguity_count"], 2)
        self.assertEqual(evidence["source_pages"], [1, 2])
        self.assertIsNone(evidence["source_page"])
        self.assertIsNone(evidence["source_char_offset"])
        part.pop("page_records")
        self.assertIn("location ambiguous", self.markdown(self.review(quote, part)))


class ChildProcessResourceTests(unittest.TestCase):
    def test_limits_on_posix_child(self):
        child = _resource_limiter(4096, 1024*1024, 8)
        with patch("resource.setrlimit") as set_limit:
            child()
        set_limit.assert_any_call(resource.RLIMIT_AS, (1024*1024, 1024*1024))
        set_limit.assert_any_call(resource.RLIMIT_CPU, (8, 8))
        set_limit.assert_any_call(resource.RLIMIT_FSIZE, (4096, 4096))
        set_limit.assert_any_call(resource.RLIMIT_CORE, (0, 0))
        self.assertEqual(set_limit.call_count, 4)

    def test_refuses_claiming_child_limits_on_non_posix(self):
        with patch("sra.pdf_visual.os.name", "nt"):
            with self.assertRaisesRegex(RuntimeError, "POSIX"):
                _resource_limiter(4096, 1024*1024, 8)


if __name__ == "__main__":
    unittest.main()
