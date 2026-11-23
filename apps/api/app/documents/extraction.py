"""Extracción local con localizadores estructurados y cobertura explícita."""

from __future__ import annotations

import csv
import io
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from openpyxl import load_workbook
from openpyxl.cell.read_only import ReadOnlyCell
from pydantic import BaseModel, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_PDF_PAGES = 100
MIN_PDF_CHARS = 40
MIN_OCR_CONFIDENCE = 60
MAX_SEGMENTS = 1_000
MAX_TEXT_CHARS = 200_000
MAX_FRAGMENT_CHARS = 12_000
MAX_SHEETS = 20
MAX_ROWS = 2_000
MAX_COLUMNS = 64
MAX_DOCX_BLOCKS = 5_000

OCRPage = Callable[[Path, int, str], tuple[str, float | None]]
Format = Literal["pdf", "docx", "xlsx"]
SUPPORTED_MEDIA: dict[str, Format] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}


class Locator(BaseModel):
    page: int | None = None
    section: str | None = None
    paragraph: int | None = None
    table: int | None = None
    row: int | None = None
    column: int | None = None
    sheet: str | None = None
    cell: str | None = None


class Fragment(BaseModel):
    locator: Locator
    text: str = Field(max_length=MAX_FRAGMENT_CHARS)
    method: Literal["texto", "ocr"] = "texto"
    confidence: float | None = Field(default=None, ge=0, le=100)


class Notice(BaseModel):
    code: str
    locator: Locator | None = None


class Result(BaseModel):
    status: Literal["listo", "revision", "fallido"]
    fragments: list[Fragment] = Field(default_factory=list, max_length=MAX_SEGMENTS)
    warnings: list[Notice] = Field(default_factory=list, max_length=256)
    error_code: str | None = None
    total_pages: int | None = None


class Coverage:
    def __init__(self) -> None:
        self.fragments: list[Fragment] = []
        self.warnings: list[Notice] = []
        self.chars = 0

    @property
    def full(self) -> bool:
        return self.chars >= MAX_TEXT_CHARS or len(self.fragments) >= MAX_SEGMENTS

    def warn(self, code: str, locator: Locator | None = None) -> None:
        notice = Notice(code=code, locator=locator)
        if len(self.warnings) < 255 and notice not in self.warnings:
            self.warnings.append(notice)

    def add(
        self, locator: Locator, text: str, *, method: Literal["texto", "ocr"] = "texto",
        confidence: float | None = None,
    ) -> None:
        text = text.replace("\x00", "").strip()
        if not text:
            return
        if self.full:
            self.warn("limite_texto")
            return
        length = min(MAX_TEXT_CHARS - self.chars, MAX_FRAGMENT_CHARS)
        if len(text) > length:
            self.warn("limite_texto", locator)
        text = text[:length]
        self.fragments.append(Fragment(
            locator=locator, text=text, method=method, confidence=confidence,
        ))
        self.chars += len(text)

    def finish(self, *, pages: int | None = None) -> Result:
        if not self.fragments:
            self.warn("sin_texto")
        return Result(
            status="revision" if self.warnings else "listo",
            fragments=self.fragments, warnings=self.warnings, total_pages=pages,
        )


def failed(code: str) -> Result:
    return Result(status="fallido", error_code=code)


def ocr_page(pdf: Path, page: int, language: str) -> tuple[str, float | None]:
    """Rasteriza solo la página necesaria y reconoce texto en una pasada TSV."""
    output = pdf.parent / "page"
    subprocess.run(
        ["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile",
         "-scale-to", "2200", "-gray", str(pdf), str(output)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=10,
    )
    recognised = subprocess.run(
        ["tesseract", str(output.with_suffix(".pgm")), "stdout", "-l", language, "tsv"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=12,
    )
    lines: dict[tuple[str, str, str], list[str]] = {}
    scores: list[float] = []
    for entry in csv.DictReader(io.StringIO(recognised.stdout.decode("utf-8")), delimiter="\t"):
        word = (entry["text"] or "").strip()
        if not word:
            continue
        lines.setdefault((entry["block_num"], entry["par_num"], entry["line_num"]), []).append(word)
        score = float(entry["conf"])
        if 0 <= score <= 100:
            scores.append(score)
    return "\n".join(" ".join(words) for words in lines.values()), (
        sum(scores) / len(scores) if scores else None
    )


def extract_pdf(data: bytes, *, ocr: OCRPage, language: str, max_ocr_pages: int) -> Result:
    pdf = PdfReader(io.BytesIO(data))
    if pdf.is_encrypted:
        return failed("archivo_cifrado")
    pages = len(pdf.pages)
    if pages > MAX_PDF_PAGES:
        return failed("limite_paginas")
    coverage = Coverage()
    used_ocr = 0
    missing_ocr = False
    with tempfile.TemporaryDirectory(prefix="eag-ocr-") as temporary:
        source = Path(temporary) / "source.pdf"
        for number, page in enumerate(pdf.pages, 1):
            locator = Locator(page=number)
            try:
                native = (page.extract_text() or "").strip()
            except (PdfReadError, ValueError, KeyError, TypeError):
                native = ""
                coverage.warn("pagina_ilegible", locator)
            if len(native) >= MIN_PDF_CHARS:
                coverage.add(locator, native)
            elif used_ocr >= max_ocr_pages or missing_ocr:
                coverage.add(locator, native)
                coverage.warn("ocr_no_disponible" if missing_ocr else "limite_ocr", locator)
            else:
                used_ocr += 1
                if not source.exists():
                    source.write_bytes(data)
                try:
                    text, confidence = ocr(source, number, language)
                except FileNotFoundError:
                    missing_ocr = True
                    coverage.add(locator, native)
                    coverage.warn("ocr_no_disponible", locator)
                except (OSError, subprocess.SubprocessError, ValueError, KeyError):
                    coverage.add(locator, native)
                    coverage.warn("ocr_fallido", locator)
                else:
                    if text.strip() and len(text.strip()) >= len(native):
                        coverage.add(locator, text, method="ocr", confidence=confidence)
                        if confidence is None or confidence < MIN_OCR_CONFIDENCE:
                            coverage.warn("ocr_baja_confianza", locator)
                    else:
                        coverage.add(locator, native)
                        coverage.warn("ocr_sin_texto_suficiente", locator)
            if coverage.full and number < pages:
                coverage.warn("limite_texto")
                break
    return coverage.finish(pages=pages)


def extract_docx(data: bytes) -> Result:
    document = Document(io.BytesIO(data))
    coverage = Coverage()
    section: str | None = None
    paragraphs = 0
    tables = 0
    for index, block in enumerate(document.iter_inner_content(), 1):
        if index > MAX_DOCX_BLOCKS or coverage.full:
            coverage.warn("limite_texto")
            break
        if isinstance(block, Paragraph):
            paragraphs += 1
            style_name = (block.style.name or "") if block.style else ""
            if block.text.strip() and style_name.lower().startswith(("heading", "título")):
                section = block.text.strip()[:200]
            locator = Locator(paragraph=paragraphs, section=section)
            if block._p.xpath(".//w:drawing"):
                coverage.warn("elementos_no_textuales", locator)
            coverage.add(locator, block.text)
        elif isinstance(block, Table):
            tables += 1
            if len(block.rows) > MAX_ROWS:
                coverage.warn("limite_tabla", Locator(table=tables, section=section))
            for row_index, row in enumerate(block.rows[:MAX_ROWS], 1):
                if len(row.cells) > MAX_COLUMNS:
                    coverage.warn("limite_tabla", Locator(table=tables, row=row_index))
                for column_index, cell in enumerate(row.cells[:MAX_COLUMNS], 1):
                    locator = Locator(
                        section=section, table=tables, row=row_index, column=column_index,
                    )
                    if cell.tables or cell._tc.xpath(".//w:drawing"):
                        coverage.warn("elementos_no_textuales", locator)
                    coverage.add(locator, cell.text)
                if coverage.full:
                    coverage.warn("limite_texto")
                    break
    return coverage.finish()


def extract_xlsx(data: bytes) -> Result:
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
    coverage = Coverage()
    try:
        if len(workbook.worksheets) > MAX_SHEETS:
            coverage.warn("limite_hojas")
        for sheet in workbook.worksheets[:MAX_SHEETS]:
            name = sheet.title
            if (sheet.max_row or 0) > MAX_ROWS or (sheet.max_column or 0) > MAX_COLUMNS:
                coverage.warn("limite_celdas", Locator(sheet=name))
            rows = min(sheet.max_row or MAX_ROWS + 1, MAX_ROWS + 1)
            columns = min(sheet.max_column or MAX_COLUMNS + 1, MAX_COLUMNS + 1)
            for line in sheet.iter_rows(max_row=rows, max_col=columns):
                for cell in line:
                    if not isinstance(cell, ReadOnlyCell) or cell.value is None:
                        continue
                    if cell.row > MAX_ROWS or cell.column > MAX_COLUMNS:
                        coverage.warn("limite_celdas", Locator(sheet=name))
                        continue
                    loc = Locator(
                        sheet=name, cell=cell.coordinate, row=cell.row, column=cell.column,
                    )
                    coverage.add(loc, str(cell.value))
                if coverage.full:
                    coverage.warn("limite_texto")
                    break
            if coverage.full:
                break
    finally:
        workbook.close()
    return coverage.finish()


def extract(
    data: bytes, format: Format, *, language: str = "spa+eng", max_ocr_pages: int = 12,
    ocr: OCRPage = ocr_page,
) -> Result:
    try:
        if format == "pdf":
            return extract_pdf(data, ocr=ocr, language=language, max_ocr_pages=max_ocr_pages)
        if format == "docx":
            return extract_docx(data)
        return extract_xlsx(data)
    except MemoryError:
        return failed("limite_memoria")
    except Exception:  # noqa: BLE001 - los fallos del parser no exponen texto, nombres ni rutas
        return failed("archivo_ilegible")
