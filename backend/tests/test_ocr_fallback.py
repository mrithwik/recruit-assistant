"""OCR fallback for scanned/image PDFs (see scanning/parser.py). This
environment has neither pytesseract nor the tesseract/poppler system
binaries installed, which is exactly the "optional feature not present"
case the fallback needs to degrade gracefully for — so the first test below
exercises that real path, not a simulation of it. The second test injects
fake pytesseract/pdf2image modules to confirm the OCR path is actually
reached and its output used when the libraries ARE available."""

import sys
from types import ModuleType

from app.scanning.parser import MIN_VIABLE_TEXT_LENGTH, _ocr_pdf_text


def test_ocr_unavailable_degrades_to_empty_string_not_a_crash():
    # Genuinely true in this environment — see module docstring.
    assert _ocr_pdf_text(b"not a real pdf") == ""


def test_ocr_path_used_when_libraries_available(monkeypatch):
    fake_pytesseract = ModuleType("pytesseract")
    fake_pytesseract.image_to_string = lambda image: "OCR'd resume text " * 20  # exceed MIN_VIABLE_TEXT_LENGTH

    fake_pdf2image = ModuleType("pdf2image")
    fake_pdf2image.convert_from_bytes = lambda file_bytes: ["fake-page-image"]

    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)

    result = _ocr_pdf_text(b"scanned pdf bytes")

    assert "OCR'd resume text" in result
    assert len(result) >= MIN_VIABLE_TEXT_LENGTH


def test_ocr_failure_degrades_to_empty_string(monkeypatch):
    fake_pytesseract = ModuleType("pytesseract")

    def boom(image):
        raise RuntimeError("tesseract binary not found")

    fake_pytesseract.image_to_string = boom

    fake_pdf2image = ModuleType("pdf2image")
    fake_pdf2image.convert_from_bytes = lambda file_bytes: ["fake-page-image"]

    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)
    monkeypatch.setitem(sys.modules, "pdf2image", fake_pdf2image)

    assert _ocr_pdf_text(b"scanned pdf bytes") == ""
