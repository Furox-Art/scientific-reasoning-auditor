"""No-network boundary tests for DOI metadata and BioC retrieval handling."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from sra.doi import _lookup_crossref, _lookup_datacite, _title_context_overlap, verify_dois
from sra.benchmark import _get_article
from sra.writing import audit_academic_writing, writing_report_markdown


def simulated_response(payload, status=200):
    response = MagicMock()
    response.status = status
    response.read.return_value = payload
    response.__enter__.return_value = response
    return response


class RegistryFailureAndResponseTests(unittest.TestCase):
    def test_crossref_metadata_fields_are_derived_from_registry(self):
        doi = "10.1371/journal.pone.0000217"
        payload = json.dumps({"message": {
            "DOI": doi, "title": ["Independent title"],
            "author": [{"family": "Smith"}],
            "published": {"date-parts": [[2020, 1, 1]]},
            "type": "journal-article",
        }}).encode()
        opener = MagicMock()
        opener.open.return_value = simulated_response(payload)
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_crossref(doi)
        self.assertEqual(result["status"], "REGISTERED_IN_CROSSREF")
        self.assertEqual(result["title"], "Independent title")
        self.assertEqual(result["first_author"], "Smith")
        self.assertEqual(result["publication_year"], 2020)

    def test_crossref_response_size_limit(self):
        opener = MagicMock()
        opener.open.return_value = simulated_response(b"x" * 2_000_001)
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_crossref("10.1234/abc")
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIn("size limit", result["reason"])

    def test_crossref_network_error_does_not_claim_invalid(self):
        opener = MagicMock()
        opener.open.side_effect = URLError("temporarily unavailable")
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_crossref("10.1234/abc")
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIn("URLError", result["reason"])

    def test_datacite_metadata_fields_are_derived_from_registry(self):
        doi = "10.6084/m9.figshare.21545982"
        payload = json.dumps({"data": {"attributes": {
            "doi": doi, "titles": [{"title": "Research dataset"}],
            "creators": [{"familyName": "Jones"}],
            "publicationYear": 2022,
            "types": {"resourceTypeGeneral": "Dataset"},
        }}}).encode()
        opener = MagicMock()
        opener.open.return_value = simulated_response(payload)
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_datacite(doi)
        self.assertEqual(result["status"], "REGISTERED_IN_DATACITE")
        self.assertEqual(result["publication_year"], 2022)
        self.assertEqual(result["type"], "Dataset")
        self.assertEqual(result["first_author"], "Jones")

    def test_datacite_response_size_limit(self):
        opener = MagicMock()
        opener.open.return_value = simulated_response(b"x" * 2_000_001)
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_datacite("10.1234/abc")
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_datacite_mismatched_doi_rejected(self):
        payload = json.dumps({"data": {"attributes": {"doi": "10.1111/unexpected"}}}).encode()
        opener = MagicMock()
        opener.open.return_value = simulated_response(payload)
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_datacite("10.1234/abc")
        self.assertEqual(result["status"], "UNVERIFIED")
        self.assertIn("different DOI", result["reason"])

    def test_datacite_network_error(self):
        opener = MagicMock()
        opener.open.side_effect = URLError("down")
        with patch("sra.doi.build_opener", return_value=opener):
            result = _lookup_datacite("10.1234/abc")
        self.assertEqual(result["status"], "UNVERIFIED")

    def test_doi_scanner_ignores_code_and_limits_network(self):
        doc = (
            "# References\n"
            "~~~python\n"
            '"10.1234/hidden"\n'
            "~~~\n"
            "10.1371/journal.pone.0000217 and 10.6084/m9.figshare.21545982\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.md"
            path.write_text(doc)
            with patch("sra.doi._lookup_registry") as remote:
                result = verify_dois(path, online=False, limit=1)
                remote.assert_not_called()
        self.assertEqual(result["found_count"], 2)
        self.assertEqual(result["checked_count"], 1)
        self.assertTrue(result["truncated"])

    def test_weak_title_context_short_title_unassessed(self):
        result = _title_context_overlap("Experiment", "Experiment in a test", "10.1234/a")
        self.assertEqual(result["status"], "NOT_EVALUATED")

    def test_cli_prevents_doi_output_overwriting_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.md"
            path.write_text("# References\n10.1234/demo\n")
            result = subprocess.run(
                [sys.executable, "-m", "sra.cli", "doi-check", str(path),
                 "--out", str(path)],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("overwrite", result.stderr)
            self.assertIn("10.1234/demo", path.read_text())


class PMCBiocBoundaryTests(unittest.TestCase):
    def _feed(self, documents):
        payload = json.dumps([{"documents": documents}]).encode()
        opener = simulated_response(payload)
        return patch("sra.benchmark.urlopen", return_value=opener)

    def test_no_bioc_documents(self):
        with self._feed([]):
            with self.assertRaisesRegex(ValueError, "document is unavailable"):
                _get_article("PMC1790863")

    def test_empty_bioc_passages(self):
        with self._feed([{"id": "PMC1790863", "passages": []}]):
            with self.assertRaisesRegex(ValueError, "no passages"):
                _get_article("PMC1790863")

    def test_insufficient_body_passages(self):
        passages = [
            {"infons": {"article-id_pmc": "PMC1790863",
                        "article-id_doi": "10.1234/article", "section_type": "TITLE"},
             "text": "A test"},
            {"infons": {"section_type": "INTRO", "type": "paragraph"}, "text": "Introduction."},
        ]
        with self._feed([{"id": "PMC1790863", "passages": passages}]):
            with self.assertRaisesRegex(ValueError, "Too few"):
                _get_article("PMC1790863")

    def test_limited_metadata_missing_doi_rejected(self):
        passages = [
            {"infons": {"article-id_pmc": "PMC1790863", "section_type": "TITLE"},
             "text": "A study"},
        ]
        with self._feed([{"id": "PMC1790863", "passages": passages}]):
            with self.assertRaisesRegex(ValueError, "no registered source DOI"):
                _get_article("PMC1790863")

    def test_guideline_markdown_is_explicitly_non_certifying(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "trial.md"
            path.write_text("# Methods\nA randomized trial was run.\n")
            result = audit_academic_writing(path, design="clinical-trial")
        markdown = writing_report_markdown(result)
        self.assertIn("Cue detection is not guideline compliance", markdown)
        self.assertIn("CONSORT 2025", markdown)


if __name__ == "__main__":
    unittest.main()
