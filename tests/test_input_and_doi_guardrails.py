"""Regression checks for bounded manuscript input and DOI citation context."""
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from sra.document import load_document
from sra.doi import _lookup_crossref, _reference_context, verify_dois


class DocumentBoundsTests(unittest.TestCase):
    def test_bounded_read_rejects_oversized_text_file(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/"paper.txt"
            p.write_bytes(b"X"*50)
            with patch("sra.document.MAX_DOCUMENT_BYTES", 49):
                with self.assertRaisesRegex(ValueError, "input limit"):
                    load_document(p)
            with patch("sra.document.MAX_DOCUMENT_BYTES", 50):
                self.assertEqual(load_document(p).text, "X"*50)

    def test_extracted_text_limit_rejects_excessive_utf8_text(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/"paper.md"
            p.write_text("Methods\nThe text is present.", encoding="utf-8")
            with patch("sra.document.MAX_EXTRACTED_TEXT_CHARS", 9):
                with self.assertRaisesRegex(ValueError, "extracted text"):
                    load_document(p)

    def test_pdf_page_limit_prevents_any_extraction(self):
        class Page:
            def extract_text(self, **kwargs):
                raise AssertionError("No page must be extracted over the page limit.")
        class Reader:
            def __init__(self, filename):
                self.pages = [Page(), Page()]
        pdf = ModuleType("pypdf")
        pdf.PdfReader = Reader
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"paper.pdf"
            path.write_bytes(b"%PDF-mocked")
            with patch.dict(sys.modules, {"pypdf": pdf}), patch(
                "sra.document.MAX_PDF_PAGES", 1
            ):
                with self.assertRaisesRegex(ValueError, "page processing limit"):
                    load_document(path)

    def test_pdf_extracted_text_limit_detected_after_first_page(self):
        class Page:
            def extract_text(self, **kwargs):
                return "X"*60
        class Reader:
            def __init__(self, filename):
                self.pages = [Page()]
        pdf = ModuleType("pypdf")
        pdf.PdfReader = Reader
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"paper.pdf"
            path.write_bytes(b"%PDF-mocked")
            with patch.dict(sys.modules, {"pypdf": pdf}), patch(
                "sra.document.MAX_EXTRACTED_TEXT_CHARS", 59
            ):
                with self.assertRaisesRegex(ValueError, "4,000,000-character"):
                    load_document(path)


class DOIBibliographicContextTests(unittest.TestCase):
    def test_repeated_doi_prefers_reference_citation(self):
        doc = ("# Introduction\n"
               "The unrelated discussion mentions 10.1234/trial.\n"
               "# References\n"
               "Smith and Doe. Important Clinical Study Title.\n"
               "doi: 10.1234/trial\n")
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/"paper.md"
            p.write_text(doc, encoding="utf-8")
            with patch("sra.doi._lookup_registry", return_value={
                "status": "REGISTERED_IN_CROSSREF",
                "doi": "10.1234/trial",
                "title": "Important Clinical Study Title",
            }):
                result = verify_dois(p, online=True)
        self.assertEqual(result["found_count"], 1)
        item = result["results"][0]
        self.assertEqual(item["line"], 2)
        self.assertEqual(item["reference_line"], 5)
        self.assertEqual(item["title_comparison"]["status"], "TITLE_WORDS_OVERLAP")

    def test_without_bibliography_does_not_assess_title_from_body(self):
        text = ("# Introduction\n"
                "Title words could appear here but no bibliography. 10.1234/trial\n")
        self.assertIsNone(_reference_context(text, "10.1234/trial"))
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"paper.md"
            path.write_text(text,encoding="utf-8")
            with patch("sra.doi._lookup_registry", return_value={
                "status": "REGISTERED_IN_CROSSREF",
                "title": "Title words could appear here",
            }):
                result=verify_dois(path, online=True)
        self.assertEqual(result["results"][0]["title_comparison"]["status"], "NOT_EVALUATED")
        self.assertIsNone(result["results"][0]["reference_line"])

    def test_reference_section_stops_at_next_heading(self):
        text = "# References\n10.1234/other\n# Discussion\n10.1234/trial\n"
        self.assertIsNone(_reference_context(text, "10.1234/trial"))

    def test_reference_doi_on_newline_does_not_mix_other_citation(self):
        text = ("# References\n"
                "Previous paper. 10.1234/other\n"
                "New and Important Clinical Study Title\n"
                "doi: 10.1234/trial\n")
        line, context = _reference_context(text, "10.1234/trial")
        self.assertEqual(line, 4)
        self.assertIn("New and Important", context)
        self.assertNotIn("Previous paper", context)


class CrossrefMalformedResponseTests(unittest.TestCase):
    def test_registry_malformed_metadata_is_unverified(self):
        class Response(io.BytesIO):
            status = 200
        class Opener:
            def __init__(self, payload):
                self.payload = payload
            def open(self, *_args, **_kwargs):
                return Response(json.dumps(self.payload).encode("utf-8"))

        base = {"DOI":"10.1234/trial", "published":{"date-parts":[[2022]]},
                "title":["Important Clinical Study Title"]}
        bad = [
            [], {"message": None},
            {"message": {**base, "published": []}},
            {"message": {**base, "published": None}},
            {"message": {**base, "published": {"date-parts": {}}}},
        ]
        for case in bad:
            with self.subTest(payload=repr(case)[:100]), patch(
                "sra.doi.build_opener", return_value=Opener(case)
            ):
                self.assertEqual(_lookup_crossref("10.1234/trial")["status"], "UNVERIFIED")
        with patch("sra.doi.build_opener", return_value=Opener({"message": base})):
            result = _lookup_crossref("10.1234/trial")
        self.assertEqual(result["status"], "REGISTERED_IN_CROSSREF")
        self.assertEqual(result["publication_year"], 2022)


if __name__=="__main__":
    unittest.main()
