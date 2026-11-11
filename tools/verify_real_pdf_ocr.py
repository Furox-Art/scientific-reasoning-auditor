"""Real OCR integration smoke test; no model API or external data is used.

Run on a Linux machine with Pillow, reportlab, pypdf, pdftoppm and Tesseract.
Builds a synthetic three-page PDF with a scanned (image-only) middle page.
"""
from __future__ import annotations

import hashlib
import io
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

from sra.document import load_document


def _text_page(text: str):
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=(595, 842))
    pdf.setFont("Helvetica", 16)
    pdf.drawString(50, 710, text)
    pdf.save()
    stream.seek(0)
    return PdfReader(stream).pages[0]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sra-real-ocr-") as folder:
        path = Path(folder) / "synthetic-3-page.pdf"
        image = Image.new("RGB", (1200, 1600), "white")
        canvas_image = ImageDraw.Draw(image)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        canvas_image.text((65, 140), "SCANNED_TOKEN_742", fill="black", font=font)
        canvas_image.text((65, 280), "Methods: Observational study.", fill="black", font=font)
        canvas_image.text((65, 420), "Results: 15 percent increase.", fill="black", font=font)
        # Draw axes that the OCR process should not silently count as verified semantics.
        canvas_image.line([(160, 1000), (160, 600), (830, 600)], fill="black", width=6)
        canvas_image.line([(250, 900), (350, 830), (500, 750), (700, 680)], fill="black", width=5)
        scan_stream = io.BytesIO()
        image.save(scan_stream, format="PDF", resolution=150)
        scan_stream.seek(0)
        scanned_page = PdfReader(scan_stream).pages[0]
        writer = PdfWriter()
        writer.add_page(_text_page("Introduction: This is an illustrative manuscript."))
        writer.add_page(scanned_page)
        writer.add_page(_text_page("Conclusion: The results need independent verification."))
        with path.open("wb") as target:
            writer.write(target)
        extracted = PdfReader(str(path))
        native_lengths = [len(page.extract_text() or "") for page in extracted.pages]
        if len(native_lengths) != 3 or native_lengths[1] != 0:
            raise AssertionError(f"Fixture was not a mixed scan: {native_lengths!r}")
        parsed = load_document(path, pdf_ocr_mode="missing", ocr_languages="eng")
        if "SCANNED_TOKEN_742" not in parsed.text:
            raise AssertionError("Tesseract failed to recover the image-only page token.")
        details = parsed.extraction_details
        if details["ocr_pages"] != [2]:
            raise AssertionError(f"Wrong OCR page allocation: {details['ocr_pages']!r}")
        if [rec["method"] for rec in details["page_records"]] != [
            "native", "tesseract", "native",
        ]:
            raise AssertionError("Unexpected page-by-page extraction methods.")
        if details["physical_page_text_coverage"] != "all_pages_with_text":
            raise AssertionError("Mixed PDF page text coverage was not established.")
        if details["image_and_chart_semantics_verified"] is not False:
            raise AssertionError("Image/chart semantic certainty must never be asserted.")
        if hashlib.sha256(path.read_bytes()).hexdigest() != parsed.sha256:
            raise AssertionError("Source digest mismatched extracted PDF bytes.")
        scanned = details["page_records"][1]
        if parsed.text[scanned["start_char"]:scanned["end_char"]].find(
            "SCANNED_TOKEN_742"
        ) == -1:
            raise AssertionError("Scanned text is not aligned to its physical PDF page.")
        print("PASS: 3 physical pages, page 2 OCR-only, original source digest stable.")
        print("PASS: page references, missing-text recovery and unverified figure semantics.")

        # K1 F1: a *single* page has a substantial digital title plus an
        # image-only token. OCR must recover the raster token despite >20
        # native characters, without discarding the digital text layer.
        hybrid_image = Image.new("RGB", (1200, 300), "white")
        draw_hybrid = ImageDraw.Draw(hybrid_image)
        hybrid_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48
        )
        draw_hybrid.text((50, 70), "SCANNED_TOKEN_742", font=hybrid_font, fill="black")
        hybrid = Path(folder) / "hybrid-digital-plus-raster.pdf"
        cv = canvas.Canvas(str(hybrid), pagesize=(595, 842))
        cv.setFont("Helvetica", 16)
        heading = "Clinical study with an observational trial and digital heading."
        cv.drawString(50, 760, heading)
        cv.drawImage(ImageReader(hybrid_image), 50, 410, width=480, height=120)
        cv.showPage()
        cv.save()
        extracted_hybrid = PdfReader(str(hybrid))
        if len(extracted_hybrid.pages[0].extract_text() or "") < 20:
            raise AssertionError("Hybrid fixture has no substantial native text.")
        reviewed_hybrid = load_document(hybrid, pdf_ocr_mode="missing", ocr_languages="eng")
        if heading not in reviewed_hybrid.text or "SCANNED_TOKEN_742" not in reviewed_hybrid.text:
            raise AssertionError("Hybrid page failed to retain native and image text.")
        record = reviewed_hybrid.extraction_details["page_records"][0]
        if record["method"] != "native+tesseract" or record["embedded_image_count"] < 1:
            raise AssertionError("Hybrid page did not execute image-aware OCR.")
        if reviewed_hybrid.extraction_details["image_and_chart_semantics_verified"] is not False:
            raise AssertionError("Hybrid OCR must not claim complete chart comprehension.")
        print("PASS: K1 F1 hybrid native-heading + embedded raster text recovered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
