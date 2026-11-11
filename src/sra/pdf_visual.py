"""Bounded local PDF rendering, OCR, and image transport for scientific review.

These tools extract *text* and image pixels; they do not validate mathematical
figures or scientifically interpret diagrams.
"""
from __future__ import annotations

import base64
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

MAX_PAGE_IMAGE_BYTES = 16 * 1024 * 1024
MAX_OCR_PAGE_CHARACTERS = 250_000
MAX_OCR_PAGES = 100
MAX_VISION_PAGES = 30
SUPPORTED_OCR_MODES = ("off", "missing", "all")


def validate_ocr_settings(mode: str, languages: str) -> None:
    if mode not in SUPPORTED_OCR_MODES:
        raise ValueError("PDF OCR mode must be off, missing or all.")
    if not isinstance(languages, str) or re.fullmatch(
        r"[a-z]{3}(?:\+[a-z]{3}){0,3}", languages
    ) is None:
        raise ValueError("OCR languages must be 3-letter Tesseract codes, e.g. eng+tur.")


def render_pdf_page(
    pdf_path: str | Path, page_number: int, *, color: bool = False,
) -> tuple[bytes, str]:
    """Render one numbered page at <= 2,000 pixels, bounded per process/byte."""
    if type(page_number) is not int or not 1 <= page_number <= 500:
        raise ValueError("PDF page number must be from 1 to 500.")
    exe = shutil.which("pdftoppm")
    if exe is None:
        raise RuntimeError("PDF page rendering requires Poppler's pdftoppm executable.")
    fmt = "jpeg" if color else "png"
    mime = "image/jpeg" if color else "image/png"
    with tempfile.TemporaryDirectory(prefix="sra-pdf-page-") as directory:
        stem = Path(directory) / "page"
        command = [
            exe, "-f", str(page_number), "-l", str(page_number),
            "-singlefile", "-scale-to", "2000",
        ]
        if color:
            command.extend(["-jpeg", "-jpegopt", "quality=80"])
        else:
            command.extend(["-gray", "-png"])
        command.extend([str(pdf_path), str(stem)])
        try:
            result = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=45, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("PDF page rendering exceeded the 45-second limit.") from exc
        if result.returncode != 0:
            raise RuntimeError("PDF rendering failed; the PDF may be malformed or unsupported.")
        image_path = stem.with_suffix(".jpg" if color else ".png")
        if not image_path.is_file():
            raise RuntimeError("PDF renderer did not produce the requested page image.")
        with image_path.open("rb") as stream:
            image = stream.read(MAX_PAGE_IMAGE_BYTES + 1)
    if not image or len(image) > MAX_PAGE_IMAGE_BYTES:
        raise ValueError("Rendered PDF page exceeded the 16 MiB image limit or was empty.")
    return image, mime


def ocr_pdf_page(pdf_path: str | Path, page_number: int, *, languages: str) -> str:
    """Run locally installed Tesseract on a bounded rendered page."""
    validate_ocr_settings("all", languages)
    exe = shutil.which("tesseract")
    if exe is None:
        raise RuntimeError(
            "Scanned PDF text requires Tesseract OCR; install tesseract-ocr "
            "or use --ocr-mode off explicitly."
        )
    image, _mime = render_pdf_page(pdf_path, page_number)
    with tempfile.TemporaryDirectory(prefix="sra-ocr-page-") as directory:
        picture = Path(directory) / "page.png"
        picture.write_bytes(image)
        try:
            result = subprocess.run(
                [exe, str(picture), "stdout", "-l", languages, "--psm", "3"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=65, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("PDF OCR exceeded the 65-second per-page limit.") from exc
    if result.returncode != 0:
        raise RuntimeError(
            "Tesseract OCR failed. Verify that the requested OCR languages are installed."
        )
    if len(result.stdout) > MAX_OCR_PAGE_CHARACTERS * 4:
        raise ValueError("PDF OCR output exceeded the allowed page-text size.")
    text = result.stdout.decode("utf-8", errors="replace").replace(
        "\r\n", "\n"
    ).replace("\f", "").strip()
    if len(text) > MAX_OCR_PAGE_CHARACTERS:
        raise ValueError("PDF OCR text exceeded the allowed page-text size.")
    return text


def pdf_page_image_url(pdf_path: str | Path, page_number: int) -> tuple[str, str]:
    """Return a data URI for *opt-in* page vision, and the rendered-image hash."""
    import hashlib

    image, mime = render_pdf_page(pdf_path, page_number, color=True)
    digest = hashlib.sha256(image).hexdigest()
    return f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}", digest
