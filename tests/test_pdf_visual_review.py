"""PDF OCR/page provenance and multimodal model transport adversarial regressions."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from sra.document import load_document
from sra.model_client import request_single_model_review
from sra.paper_review import SYNTHESIS_FIELDS, _validated_visual, paper_review_markdown, review_paper
from sra.pdf_visual import (
    ocr_pdf_page, pdf_page_image_url, render_pdf_page,
    validate_ocr_settings,
)


def fake_pdf_reader(texts):
    module = ModuleType("pypdf")

    class Page:
        def __init__(self, value):
            self.value = value

        def extract_text(self, **kwargs):
            return self.value

    class Reader:
        def __init__(self, handle):
            if not isinstance(handle, io.BytesIO):
                raise AssertionError("The loader must parse immutable bytes.")
            self.pages = [Page(x) for x in texts]

    module.PdfReader = Reader
    return module


class OCRDocumentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.pdf = Path(self.directory.name) / "source.pdf"
        self.pdf.write_bytes(b"%PDF-source-hash-fixture")

    def test_mixed_pdf_recovers_scanned_middle_page_and_offsets(self):
        pages = ["# Introduction\nThis clinical paper used a valid sample.",
                 "", "# Results\nThe result is descriptive."]
        calls = []

        def read_ocr(snapshot, number, *, languages):
            calls.append((number, languages, Path(snapshot).read_bytes()))
            return "SCANNED_TOKEN_742" if number == 2 else ""

        with patch.dict(sys.modules, {"pypdf": fake_pdf_reader(pages)}), patch(
            "sra.pdf_visual.ocr_pdf_page", side_effect=read_ocr
        ):
            doc = load_document(self.pdf, pdf_ocr_mode="missing")
        self.assertEqual(calls, [(2, "eng", self.pdf.read_bytes())])
        self.assertIn("SCANNED_TOKEN_742", doc.text)
        self.assertEqual(doc.extraction_details["ocr_pages"], [2])
        self.assertEqual(doc.extraction_details["physical_page_text_coverage"],
                         "all_pages_with_text")
        p1, p2, p3 = doc.extraction_details["page_records"]
        self.assertEqual([x["method"] for x in (p1, p2, p3)],
                         ["native", "tesseract", "native"])
        self.assertEqual(doc.text[p2["start_char"]:p2["end_char"]],
                         "SCANNED_TOKEN_742")
        self.assertEqual(doc.sha256, hashlib.sha256(self.pdf.read_bytes()).hexdigest())
        self.assertTrue(all(x["needs_visual_review"] for x in (p1, p2, p3)))

    def test_missing_or_failed_page_is_never_called_complete(self):
        pages = ["# Introduction\nThis paper has an abstract.", ""]
        with patch.dict(sys.modules, {"pypdf": fake_pdf_reader(pages)}):
            doc = load_document(self.pdf, pdf_ocr_mode="off")
        self.assertEqual(doc.extraction_details["pages_without_extractable_text"], [2])
        self.assertEqual(doc.extraction_details["physical_page_text_coverage"], "incomplete")
        with patch.dict(sys.modules, {"pypdf": fake_pdf_reader(pages)}), patch(
            "sra.pdf_visual.ocr_pdf_page", return_value=""
        ):
            doc = load_document(self.pdf, pdf_ocr_mode="missing")
        self.assertEqual(doc.extraction_details["pages_without_extractable_text"], [2])
        self.assertEqual(doc.extraction_details["page_records"][1]["method"], "no_text")
        self.assertEqual(doc.extraction_details["ocr_pages"], [2])

    def test_ocr_all_pages_and_no_text(self):
        with patch.dict(sys.modules, {"pypdf": fake_pdf_reader(["Native content is here."])}), patch(
            "sra.pdf_visual.ocr_pdf_page", return_value="Rendered OCR content"
        ) as run:
            doc = load_document(self.pdf, pdf_ocr_mode="all", ocr_languages="eng+tur")
        self.assertEqual(doc.text, "Rendered OCR content")
        self.assertIn("+tesseract", doc.parser_backend)
        self.assertEqual(doc.extraction_details["ocr_languages"], "eng+tur")
        run.assert_called_once()
        with patch.dict(sys.modules, {"pypdf": fake_pdf_reader([""])}), patch(
            "sra.pdf_visual.ocr_pdf_page", return_value=""
        ):
            with self.assertRaisesRegex(ValueError, "No extractable text"):
                load_document(self.pdf, pdf_ocr_mode="missing")

    def test_pdf_limits_and_invalid_languages(self):
        for bad_mode, bad_lang in (("invalid", "eng"), ("missing", "eng;rm -rf /"),
                                    ("off", "ENG"), ("off", "")):
            with self.subTest(mode=bad_mode, lang=bad_lang), self.assertRaises(ValueError):
                load_document(self.pdf, pdf_ocr_mode=bad_mode, ocr_languages=bad_lang)
        with patch.dict(sys.modules, {"pypdf": fake_pdf_reader(["text", "text"])}), patch(
            "sra.pdf_visual.MAX_OCR_PAGES", 1
        ):
            with self.assertRaisesRegex(ValueError, "100-page OCR"):
                load_document(self.pdf, pdf_ocr_mode="all")
        with patch.dict(sys.modules, {"pypdf": fake_pdf_reader(["", ""])}), patch(
            "sra.pdf_visual.MAX_OCR_PAGES", 1
        ), patch("sra.pdf_visual.ocr_pdf_page", return_value="recognized"):
            with self.assertRaisesRegex(ValueError, "100-page OCR"):
                load_document(self.pdf, pdf_ocr_mode="missing")
        with patch.dict(sys.modules, {"pypdf": fake_pdf_reader(["one", "two"])}), patch(
            "sra.document.MAX_PDF_PAGES", 1
        ):
            with self.assertRaisesRegex(ValueError, "500-page"):
                load_document(self.pdf)
        with patch.dict(sys.modules, {"pypdf": fake_pdf_reader(["a"*60])}), patch(
            "sra.document.MAX_EXTRACTED_TEXT_CHARS", 59
        ):
            with self.assertRaisesRegex(ValueError, "4,000,000"):
                load_document(self.pdf)

    def test_missing_ocr_binary_rejected(self):
        with patch("sra.pdf_visual.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Tesseract OCR"):
                ocr_pdf_page(self.pdf, 1, languages="eng")


class ExternalPDFProcessTests(unittest.TestCase):
    def test_render_success_uses_bounded_command(self):
        with patch("sra.pdf_visual.shutil.which", return_value="/usr/bin/pdftoppm"), patch(
            "sra.pdf_visual.subprocess.run"
        ) as run:
            def call(argv, **kwargs):
                self.assertNotIn("shell", kwargs)
                self.assertEqual(kwargs["timeout"], 45)
                Path(argv[-1] + ".png").write_bytes(b"PNG")
                return SimpleNamespace(returncode=0)
            run.side_effect = call
            image, mime = render_pdf_page("paper.pdf", 2)
        self.assertEqual((image, mime), (b"PNG", "image/png"))
        self.assertIn("-scale-to", run.call_args.args[0])

    def test_color_render_uses_jpeg_and_max_scale(self):
        with patch("sra.pdf_visual.shutil.which", return_value="/usr/bin/pdftoppm"), patch(
            "sra.pdf_visual.subprocess.run"
        ) as run:
            def call(argv, **kwargs):
                self.assertIn("-jpegopt", argv)
                Path(argv[-1] + ".jpg").write_bytes(b"JPG")
                return SimpleNamespace(returncode=0)
            run.side_effect=call
            image,mime=render_pdf_page("paper.pdf",1,color=True)
        self.assertEqual((image,mime),(b"JPG","image/jpeg"))

    def test_render_validates_page_executable_output_timeout_and_size(self):
        for n in (-1, 0, 501, True):
            with self.subTest(page=n), self.assertRaises(ValueError):
                render_pdf_page("paper.pdf", n)
        with patch("sra.pdf_visual.shutil.which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "pdftoppm"):
                render_pdf_page("paper.pdf", 1)
        with patch("sra.pdf_visual.shutil.which", return_value="pdftoppm"), patch(
            "sra.pdf_visual.subprocess.run", return_value=SimpleNamespace(returncode=1)
        ):
            with self.assertRaisesRegex(RuntimeError, "rendering failed"):
                render_pdf_page("paper.pdf", 1)
        with patch("sra.pdf_visual.shutil.which", return_value="pdftoppm"), patch(
            "sra.pdf_visual.subprocess.run", return_value=SimpleNamespace(returncode=0)
        ):
            with self.assertRaisesRegex(RuntimeError, "did not produce"):
                render_pdf_page("paper.pdf", 1)
        from subprocess import TimeoutExpired
        with patch("sra.pdf_visual.shutil.which", return_value="pdftoppm"), patch(
            "sra.pdf_visual.subprocess.run", side_effect=TimeoutExpired("pdftoppm", 45)
        ):
            with self.assertRaisesRegex(RuntimeError, "45-second"):
                render_pdf_page("paper.pdf", 1)
        with patch("sra.pdf_visual.shutil.which", return_value="pdftoppm"), patch(
            "sra.pdf_visual.subprocess.run"
        ) as run, patch("sra.pdf_visual.MAX_PAGE_IMAGE_BYTES", 2):
            def large(argv, **kwargs):
                Path(argv[-1] + ".png").write_bytes(b"ABCD")
                return SimpleNamespace(returncode=0)
            run.side_effect = large
            with self.assertRaisesRegex(ValueError, "image limit"):
                render_pdf_page("paper.pdf", 1)

    def test_ocr_command_success_fail_timeout_and_size(self):
        with patch("sra.pdf_visual.shutil.which", return_value="tesseract"), patch(
            "sra.pdf_visual.render_pdf_page", return_value=(b"IMG", "image/png")
        ), patch("sra.pdf_visual.subprocess.run") as run:
            def call(argv, **kwargs):
                self.assertEqual(kwargs["timeout"], 65)
                self.assertEqual(argv[-4:], ["-l", "eng", "--psm", "3"])
                self.assertTrue(Path(argv[1]).is_file())
                return SimpleNamespace(returncode=0, stdout=b"Results: twenty cases.\f")
            run.side_effect = call
            self.assertEqual(ocr_pdf_page("source.pdf", 1, languages="eng"),
                             "Results: twenty cases.")
            run.side_effect = None
            run.return_value = SimpleNamespace(returncode=1, stdout=b"error")
            with self.assertRaisesRegex(RuntimeError, "Tesseract OCR failed"):
                ocr_pdf_page("source.pdf", 1, languages="eng")
            from subprocess import TimeoutExpired
            run.side_effect = TimeoutExpired("tesseract", 65)
            with self.assertRaisesRegex(RuntimeError, "65-second"):
                ocr_pdf_page("source.pdf", 1, languages="eng")
            run.side_effect = None
            run.return_value = SimpleNamespace(returncode=0, stdout=b"A"*100)
            with patch("sra.pdf_visual.MAX_OCR_PAGE_CHARACTERS", 10):
                with self.assertRaisesRegex(ValueError, "page-text size"):
                    ocr_pdf_page("source.pdf", 1, languages="eng")
            run.return_value = SimpleNamespace(returncode=0, stdout=b"A"*30)
            with patch("sra.pdf_visual.MAX_OCR_PAGE_CHARACTERS", 10):
                with self.assertRaisesRegex(ValueError, "OCR text exceeded"):
                    ocr_pdf_page("source.pdf", 1, languages="eng")

    def test_ocr_validations_and_vision_jpeg_digest(self):
        for mode in (None, 5, "x"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                validate_ocr_settings(mode, "eng")
        with self.assertRaises(ValueError):
            validate_ocr_settings("missing", "eng+invalid")
        with patch("sra.pdf_visual.render_pdf_page", return_value=(b"JPG", "image/jpeg")) as fake:
            url, digest = pdf_page_image_url("source.pdf", 3)
            self.assertEqual(url, "data:image/jpeg;base64,"+base64.b64encode(b"JPG").decode())
            self.assertEqual(digest, hashlib.sha256(b"JPG").hexdigest())
            fake.assert_called_once_with("source.pdf", 3, color=True)


def fake_model(_template, manuscript, **kwargs):
    payload=kwargs["_payload_override"]
    if payload["task"] == "whole_manuscript_synthesis":
        return {x: "Scientific interpretation is provisional." for x in SYNTHESIS_FIELDS}
    if payload["task"] == "scientific_page_image_review":
        return {"page_summary": "Visible axes and one chart in the rendered image.",
                "visual_findings": [{"severity": "medium", "issue": "Plot interpretation",
                                     "reason": "Error bars are unclear",
                                     "recommendation": "Inspect raw figure data",
                                     "visible_evidence": "A plot and two labeled axes"}]}
    return {"explanation": "The source passage reports observational methods.",
            "main_points": ["Observed outcome reported."],
            "critiques": [{"severity": "medium", "issue": "Causality uncertain",
                           "reason": "Observational design.",
                           "quote": manuscript[:24], "recommendation": "Assess confounding."}]}


class PDFVisionReviewTests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.pdf=Path(d.name)/"paper.pdf"
        self.pdf.write_bytes(b"%PDF-known")
        self.document = SimpleNamespace(
            source="paper.pdf", sha256=hashlib.sha256(self.pdf.read_bytes()).hexdigest(),
            text="# Methods\nA small cohort was observed.\n# Results\nThe signal increased.",
            parser_backend="pypdf-layout+tesseract", source_size_bytes=self.pdf.stat().st_size,
            extraction_details={"pdf_page_count": 1, "ocr_mode": "missing",
                                "ocr_pages": [1], "pages_without_extractable_text": [],
                                "physical_page_text_coverage": "all_pages_with_text",
                                "page_records": [{"page": 1, "method": "tesseract",
                                                  "start_char": 0, "end_char": 68}]},
            sections={"Methods": "A small cohort was observed.", "Results": "The signal increased."},
            section_start_lines={"Methods": 2, "Results": 4}, input_format="pdf",
        )

    def test_full_vision_flow_produces_grounded_page_references(self):
        calls=[]
        def model(*args, **kwargs):
            calls.append(kwargs)
            return fake_model(*args, **kwargs)
        with patch("sra.paper_review.load_document", return_value=self.document), patch(
            "sra.paper_review.pdf_page_image_url",
            return_value=("data:image/jpeg;base64,SlBH", "b"*64)
        ) as render, patch("sra.paper_review.request_single_model_review", side_effect=model):
            result=review_paper(self.pdf, model="mock", visual_pages=True)
        self.assertEqual(result["visual_pages"]["pages_reviewed"], 1)
        self.assertEqual(result["visual_pages"]["status"], "model_assessed_not_verified")
        self.assertEqual(len(calls), result["chunk_count"] + 2)
        self.assertTrue(all(c["_strict_completion"] for c in calls))
        self.assertIn("image/jpeg", calls[-2]["_image_data_url"])
        self.assertEqual(result["chunk_analyses"][0]["critiques"][0]["source_page"], 1)
        self.assertEqual(result["pdf_extraction"]["ocr_pages"], [1])
        self.assertIn("model observation", paper_review_markdown(result).lower()) if False else self.assertIn(
            "Model-assisted PDF image observations", paper_review_markdown(result))
        self.assertEqual(render.call_count, 1)
        empty_findings=dict(result)
        empty_visual=dict(result["visual_pages"])
        empty_visual["analyses"]=[{**result["visual_pages"]["analyses"][0],"visual_findings":[]}]
        empty_findings["visual_pages"]=empty_visual
        self.assertIn("No model-reported visual issues",paper_review_markdown(empty_findings))

    def test_visual_rejects_missing_text_and_malformed_responses(self):
        good={"page_summary": "A plot appears.", "visual_findings": []}
        self.assertEqual(_validated_visual(good,page=1,image_sha256="a"*64)["page"],1)
        bad=[None, [], {}, {**good,"page_summary":""},
             {**good,"visual_findings":"wrong"},
             {**good,"visual_findings":[{}]*13},
             {**good,"visual_findings":["text"]},
             {**good,"visual_findings":[{"severity":"critical"}]},
             {**good,"visual_findings":[{"severity":"low","issue":"",
                "reason":"yes","recommendation":"yes","visible_evidence":"yes"}]},
             {**good,"visual_findings":[{"severity":"low","issue":"yes",
                "reason":"","recommendation":"yes","visible_evidence":"yes"}]},
             {**good,"visual_findings":[{"severity":"low","issue":"yes",
                "reason":"yes","recommendation":"","visible_evidence":"yes"}]},
             {**good,"visual_findings":[{"severity":"low","issue":"yes",
                "reason":"yes","recommendation":"yes","visible_evidence":""}]}]
        for value in bad:
            with self.subTest(value=repr(value)[:70]),self.assertRaises(ValueError):
                _validated_visual(value,page=1,image_sha256="a"*64)

    def test_preflight_rejects_nondocument_vision_and_limits(self):
        manuscript=self.pdf.with_suffix(".md")
        manuscript.write_text("# Methods\nA study.\n",encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "only available for PDFs"):
            review_paper(manuscript,model="mock",visual_pages=True)
        with self.assertRaisesRegex(ValueError, "boolean"):
            review_paper(manuscript,model="mock",visual_pages="yes")
        too_big = SimpleNamespace(**{**vars(self.document), "extraction_details": {
            **self.document.extraction_details, "pdf_page_count": 31}})
        with patch("sra.paper_review.load_document", return_value=too_big), patch(
            "sra.paper_review.request_single_model_review"
        ) as model:
            with self.assertRaisesRegex(ValueError, "30-page"):
                review_paper(self.pdf,model="mock",visual_pages=True)
            model.assert_not_called()

    def test_source_hash_change_aborts_image_review(self):
        stale=SimpleNamespace(**{**vars(self.document),"sha256":"f"*64})
        with patch("sra.paper_review.load_document", return_value=stale), patch(
            "sra.paper_review.request_single_model_review", side_effect=fake_model
        ), patch("sra.paper_review.pdf_page_image_url") as renderer:
            with self.assertRaisesRegex(ValueError, "PDF changed"):
                review_paper(self.pdf,model="mock",visual_pages=True)
            renderer.assert_not_called()


class ModelCompletionSecurityTests(unittest.TestCase):
    def execute(self, finish="stop", response_model="model-x", **kwargs):
        content=json.dumps({"page_summary":"ok","visual_findings":[]})
        body={"model":response_model, "choices":[{"finish_reason":finish,
              "message":{"content":content}}]}
        with patch.dict(os.environ,{"OPENAI_API_KEY":"unit-test-key"}), patch(
            "sra.model_client._open_api_request", return_value=io.BytesIO(
                json.dumps(body).encode("utf-8")
            )
        ) as send:
            result=request_single_model_review(
                {"review_mode":"single"},"",model="model-x",
                base_url="https://api.example.invalid/v1",
                _system_override="Look at the page and return JSON",
                _payload_override={"task":"image-review"},
                _strict_completion=True, **kwargs,
            )
        return result,send.call_args.args[0]

    def test_strict_envelope_accepts_complete_exact_and_versioned_models(self):
        result,_=self.execute()
        self.assertEqual(result["page_summary"],"ok")
        result,_=self.execute(response_model="model-x-2026")
        self.assertEqual(result["page_summary"],"ok")

    def test_strict_envelope_rejects_truncation_filter_and_wrong_model(self):
        for finish in ("length","content_filter",None,"tool_calls"):
            with self.subTest(finish=finish),self.assertRaisesRegex(ValueError,"finish_reason"):
                self.execute(finish=finish)
        with self.assertRaisesRegex(ValueError,"identity"):
            self.execute(response_model="other-model")
        with self.assertRaisesRegex(ValueError,"identity"):
            self.execute(response_model=None)

    def test_vision_payload_transports_real_openai_compatible_image_object(self):
        result,req=self.execute(_image_data_url="data:image/jpeg;base64,SlBH",
                                _max_output_tokens=512)
        data=json.loads(req.data)
        self.assertEqual(data["max_tokens"],512)
        self.assertEqual(data["messages"][1]["content"][1]["type"],"image_url")
        self.assertEqual(data["messages"][1]["content"][1]["image_url"]["detail"],"high")
        self.assertNotIn("unit-test-key",req.data.decode())
        self.assertEqual(result["visual_findings"],[])

    def test_validation_rejects_unbounded_images_and_invalid_token_caps(self):
        for token in (0,127,8193,True,"2048"):
            with self.subTest(token=token),self.assertRaisesRegex(ValueError,"Output token limit"):
                self.execute(_max_output_tokens=token)
        for value in ("https://remote.example/image.png","data:text/plain;base64,QUJD",
                      "data:image/jpeg;base64,"+"A"*(8*1024*1024+1)):
            with self.subTest(prefix=value[:25]),self.assertRaisesRegex(ValueError,"bounded JPEG"):
                self.execute(_image_data_url=value)


if __name__=="__main__":
    unittest.main()
