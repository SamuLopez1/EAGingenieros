"""Fixtures sintéticas con posiciones verificables en los archivos de origen."""

import io
import os
import shutil
from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook
from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.documents.extraction import Locator, extract


def synthetic_pdf(*pages: str | None, encrypted: bool = False) -> bytes:
    writer = PdfWriter()
    for content in pages:
        page = writer.add_blank_page(width=400, height=250)
        if content is not None:
            font = DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            })
            page[NameObject("/Resources")] = DictionaryObject({
                NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
            })
            stream = DecodedStreamObject()
            stream.set_data(f"BT /F1 12 Tf 10 80 Td ({content}) Tj ET".encode("ascii"))
            page[NameObject("/Contents")] = stream
    if encrypted:
        writer.encrypt("clave-exclusiva-de-la-fixture")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


@pytest.fixture
def scan_pdf() -> bytes:
    image = Image.new("RGB", (1000, 350), "white")
    ImageDraw.Draw(image).text(
        (50, 96), "EXPEDIENTE EAG 123", fill="black", font=ImageFont.load_default(size=56),
    )
    out = io.BytesIO()
    image.save(out, format="PDF")
    return out.getvalue()


def test_pdf_mixed_applies_ocr_only_to_sparse_pages() -> None:
    native = "Texto digital verificable en la primera pagina del expediente."
    calls = []

    def recognise(source: Path, page: int, language: str) -> tuple[str, float]:
        assert source.read_bytes() == data
        calls.append((page, language))
        return "Texto sintetico reconocido", 92

    data = synthetic_pdf(native, None, None)
    result = extract(data, "pdf", max_ocr_pages=1, ocr=recognise)
    assert calls == [(2, "spa+eng")]
    assert result.status == "revision" and result.total_pages == 3
    assert [(f.locator.page, f.method, f.text) for f in result.fragments] == [
        (1, "texto", native), (2, "ocr", "Texto sintetico reconocido"),
    ]
    assert [(w.code, w.locator) for w in result.warnings] == [("limite_ocr", Locator(page=3))]


@pytest.mark.parametrize(
    ("text", "confidence", "warning"),
    [("", None, "ocr_sin_texto_suficiente"), ("ABC", 37, "ocr_baja_confianza")],
)
def test_pdf_warns_on_insufficient_ocr(
    scan_pdf: bytes, text: str, confidence: float | None, warning: str,
) -> None:
    result = extract(scan_pdf, "pdf", ocr=lambda *_: (text, confidence))
    assert result.status == "revision"
    assert (result.warnings[0].code, result.warnings[0].locator) == (warning, Locator(page=1))
    assert bool(result.fragments) == bool(text)


def test_ocr_unavailable_is_explicit(scan_pdf: bytes) -> None:
    def absent(*_) -> tuple[str, float]:
        raise FileNotFoundError

    result = extract(scan_pdf, "pdf", ocr=absent)
    assert [w.code for w in result.warnings] == ["ocr_no_disponible", "sin_texto"]
    assert result.status == "revision"


@pytest.mark.skipif(
    os.getenv("EAG_TEST_REAL_OCR") != "1", reason="requiere Poppler y Tesseract reales",
)
def test_real_ocr_on_synthetic_scan(scan_pdf: bytes) -> None:
    assert shutil.which("pdftoppm") and shutil.which("tesseract")
    result = extract(scan_pdf, "pdf")
    assert result.status == "listo", result.warnings
    assert len(result.fragments) == 1
    fragment = result.fragments[0]
    assert fragment.locator == Locator(page=1)
    assert fragment.method == "ocr" and "EXPEDIENTE EAG 123" in fragment.text


def test_corrupt_encrypted_empty_and_page_budget() -> None:
    assert extract(b"corrupto", "pdf").error_code == "archivo_ilegible"
    assert extract(synthetic_pdf(None, encrypted=True), "pdf").error_code == "archivo_cifrado"
    assert extract(synthetic_pdf(*([None] * 101)), "pdf").error_code == "limite_paginas"
    assert extract(synthetic_pdf(None), "pdf", max_ocr_pages=0).status == "revision"


def test_docx_heading_paragraph_and_table_locators() -> None:
    doc = Document()
    doc.add_heading("Condiciones verificables", level=1)
    doc.add_paragraph("Primer requisito")
    doc.add_table(rows=1, cols=2).cell(0, 1).text = "Garantía de fixture"
    doc.add_paragraph("Segundo requisito")
    out = io.BytesIO()
    doc.save(out)
    result = extract(out.getvalue(), "docx")
    assert result.status == "listo"
    heading = "Condiciones verificables"
    assert [(f.text, f.locator) for f in result.fragments] == [
        (heading, Locator(section=heading, paragraph=1)),
        ("Primer requisito", Locator(section=heading, paragraph=2)),
        ("Garantía de fixture", Locator(section=heading, table=1, row=1, column=2)),
        ("Segundo requisito", Locator(section=heading, paragraph=3)),
    ]


def test_xlsx_coordinates_formula_and_coverage() -> None:
    workbook = Workbook()
    sheet = workbook.create_sheet("Presupuesto")
    sheet["B3"] = 17
    sheet["C3"] = "=B3*2"
    sheet["BM4"] = "fuera de cobertura"
    out = io.BytesIO()
    workbook.save(out)
    result = extract(out.getvalue(), "xlsx")
    assert result.status == "revision"
    assert [(f.text, f.locator) for f in result.fragments] == [
        ("17", Locator(sheet="Presupuesto", cell="B3", row=3, column=2)),
        ("=B3*2", Locator(sheet="Presupuesto", cell="C3", row=3, column=3)),
    ]
    assert result.warnings[0].code == "limite_celdas"
    assert result.warnings[0].locator == Locator(sheet="Presupuesto")
