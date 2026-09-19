"""Pruebas de extracción de texto.

Se generan documentos reales en memoria —PDF, DOCX y XLSX— en lugar de simular
los extractores. Un doble de prueba en este módulo no probaría nada: lo que
puede fallar es precisamente la interacción con el formato.
"""

from __future__ import annotations

import io

from app.documents import extract, looks_like_scanned_pdf
from app.documents.docx_extraction import extract_docx
from app.documents.extraction_types import ExtractionStatus
from app.documents.ocr_policy import MIN_CHARS_PER_PAGE
from app.documents.pdf_extraction import extract_pdf
from app.documents.xlsx_extraction import extract_xlsx

# --- Generadores de documentos reales -------------------------------------


def make_pdf(text_by_page: list[str]) -> bytes:
    """Crea un PDF real con el texto indicado en cada página.

    El texto se reparte en varias líneas: `drawString` no ajusta automáticamente
    y una línea larga se saldría de la página y no se extraería.
    """

    from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for text in text_by_page:
        words = text.split()
        line = ""
        y = 760
        for word in words:
            if len(line) + len(word) > 85:
                pdf.drawString(60, y, line)
                y -= 14
                line = word
            else:
                line = f"{line} {word}".strip()
        if line:
            pdf.drawString(60, y, line)
        pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.read()


def make_empty_pdf(page_count: int = 2) -> bytes:
    """PDF sin capa de texto, que simula un documento escaneado."""

    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=595, height=842)
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)
    return buffer.read()


def make_docx(paragraphs: list[str], table: list[list[str]] | None = None) -> bytes:
    import docx

    document = docx.Document()
    for text in paragraphs:
        document.add_paragraph(text)
    if table:
        rows = len(table)
        cols = len(table[0])
        created = document.add_table(rows=rows, cols=cols)
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                created.cell(r, c).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer.read()


def make_xlsx(sheets: dict[str, list[list[object]]]) -> bytes:
    import openpyxl

    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for name, rows in sheets.items():
        sheet = workbook.create_sheet(title=name)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    return buffer.read()


# --- PDF -------------------------------------------------------------------


def test_pdf_extracts_text_and_page_markers() -> None:
    # El texto debe superar el umbral de densidad por pagina, o el extractor
    # consideraria correctamente que la pagina es una imagen.
    parrafo = (
        "El proponente debe acreditar experiencia minima de cinco anos en "
        "interventoria de obras de infraestructura vial, mediante certificaciones "
        "expedidas por el contratante, con soporte de contratos ejecutados."
    )
    data = make_pdf([parrafo])

    result = extract_pdf(data, enable_ocr=False)

    assert result.status is ExtractionStatus.COMPLETED
    assert "cinco anos" in result.text
    # El marcador es lo que da localizador a cada fragmento.
    assert "[[pagina:1]]" in result.text


def test_pdf_multipage_keeps_page_numbers() -> None:
    data = make_pdf(["Primera pagina con contenido.", "Segunda pagina distinta."])

    result = extract_pdf(data, enable_ocr=False)

    assert result.page_count == 2
    assert "[[pagina:1]]" in result.text
    assert "[[pagina:2]]" in result.text


def test_scanned_pdf_without_text_is_detected() -> None:
    """Sin capa de texto el PDF es una imagen, y hay que saberlo."""

    data = make_empty_pdf()

    assert looks_like_scanned_pdf(data) is True


def test_pdf_with_text_is_not_reported_as_scanned() -> None:
    data = make_pdf(["Contenido suficiente para superar el umbral de texto."])

    assert looks_like_scanned_pdf(data) is False


def test_ocr_is_disabled_reports_the_gap_instead_of_silence() -> None:
    """Con OCR desactivado, las páginas sin texto deben declararse.

    Devolver un resultado vacío sin advertencia se confundiría con un documento
    sin contenido, que es un problema distinto.
    """

    data = make_empty_pdf()

    result = extract_pdf(data, enable_ocr=False)

    assert result.status is ExtractionStatus.COMPLETED_WITH_WARNINGS
    assert any("OCR desactivado" in w for w in result.warnings)
    assert result.ocr_reason is not None


def test_scanned_pdf_is_flagged_for_ocr() -> None:
    data = make_empty_pdf()

    result = extract_pdf(data, enable_ocr=True)

    # El motivo debe explicar por qué se activó, no solo que se activó.
    assert result.ocr_reason is not None
    assert "escaneado" in result.ocr_reason or "capa de texto" in result.ocr_reason


def test_low_text_density_triggers_ocr_reason() -> None:
    """Un PDF con muy poco texto por página se considera escaneado."""

    data = make_pdf(["x"])

    result = extract_pdf(data, enable_ocr=True)

    assert result.ocr_reason is not None


def test_corrupt_pdf_is_reported_as_failure() -> None:
    """Un PDF corrupto devuelve resultado fallido, no una excepcion."""

    result = extract_pdf(b"esto no es un pdf")

    assert result.status is ExtractionStatus.FAILED
    assert result.error


def test_encrypted_pdf_without_password_is_declared() -> None:
    """Un PDF cifrado no debe devolver texto vacío sin explicación."""

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.encrypt("secreta")
    buffer = io.BytesIO()
    writer.write(buffer)
    buffer.seek(0)

    result = extract_pdf(buffer.read())

    assert result.status is ExtractionStatus.FAILED
    assert "cifrado" in (result.error or "").lower()


# --- DOCX ------------------------------------------------------------------


def test_docx_extracts_paragraphs() -> None:
    data = make_docx(["El proponente debe acreditar experiencia.", "Segundo parrafo."])

    result = extract_docx(data)

    assert result.status is ExtractionStatus.COMPLETED
    assert "acreditar experiencia" in result.text
    assert "Segundo parrafo" in result.text


def test_docx_extracts_tables() -> None:
    """Los pliegos tabulan requisitos: omitir tablas perdería justo lo que hay que comparar."""

    data = make_docx(
        ["Requisitos:"],
        table=[["Requisito", "Valor"], ["Experiencia", "5 anos"]],
    )

    result = extract_docx(data)

    assert "Experiencia" in result.text
    assert "5 anos" in result.text
    # El separador conserva la relación entre columnas.
    assert "|" in result.text


def test_empty_docx_is_reported_with_warning() -> None:
    data = make_docx([])

    result = extract_docx(data)

    assert result.status is ExtractionStatus.COMPLETED_WITH_WARNINGS
    assert result.warnings


def test_corrupt_docx_is_reported_as_failure() -> None:
    """Un DOCX corrupto se declara con un error del dominio, no con una excepcion ciega."""

    result = extract(b"no es un docx", "x.docx")

    assert result.status is ExtractionStatus.FAILED
    assert result.error


# --- XLSX ------------------------------------------------------------------


def test_xlsx_extracts_sheets_as_pages() -> None:
    data = make_xlsx({"Datos": [["Nit", "Valor"], ["900123", 5000]]})

    result = extract_xlsx(data)

    assert result.page_count == 1
    assert "900123" in result.text
    # La hoja da el localizador del fragmento.
    assert "[Hoja: Datos]" in result.text


def test_xlsx_multiple_sheets_have_distinct_page_numbers() -> None:
    data = make_xlsx({"Uno": [["a"]], "Dos": [["b"]]})

    result = extract_xlsx(data)

    assert result.page_count == 2
    assert "[[pagina:1]]" in result.text
    assert "[[pagina:2]]" in result.text


def test_xlsx_preserves_row_structure() -> None:
    data = make_xlsx({"H": [["col1", "col2", "col3"]]})

    result = extract_xlsx(data)

    assert "col1 | col2 | col3" in result.text


def test_empty_xlsx_is_reported_with_warning() -> None:
    data = make_xlsx({"Vacia": []})

    result = extract_xlsx(data)

    assert result.status is ExtractionStatus.COMPLETED_WITH_WARNINGS


# --- Despachador -----------------------------------------------------------


def test_dispatch_by_extension() -> None:
    data = make_docx(["Contenido de prueba suficiente."])

    result = extract(data, "pliego.docx")

    assert result.status is ExtractionStatus.COMPLETED
    assert "Contenido de prueba" in result.text


def test_dispatch_by_content_type_when_extension_missing() -> None:
    """Los navegadores no siempre envían la extensión; el MIME sirve de respaldo."""

    data = make_docx(["Contenido con tipo mime."])

    result = extract(
        data,
        None,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert result.status is ExtractionStatus.COMPLETED


def test_unsupported_format_lists_what_is_supported() -> None:
    """Un formato no soportado debe decir cuáles sí lo están."""

    result = extract(b"datos", "archivo.zip")

    assert result.status is ExtractionStatus.UNSUPPORTED
    assert ".pdf" in (result.error or "")
    assert not result.is_usable


def test_unknown_format_without_hints_is_unsupported() -> None:
    result = extract(b"datos", None)

    assert result.status is ExtractionStatus.UNSUPPORTED


def test_result_is_not_usable_when_failed() -> None:
    result = extract(b"basura", "x.pdf")

    assert not result.is_usable


def test_supported_extensions_are_documented() -> None:
    from app.documents.dispatch import SUPPORTED_EXTENSIONS

    assert SUPPORTED_EXTENSIONS == {".pdf", ".docx", ".xlsx", ".xlsm"}


# --- Integración con la fragmentación -------------------------------------


def test_extracted_text_feeds_the_chunker_with_locators() -> None:
    """La cadena completa: extraer y fragmentar debe producir localizadores."""

    from app.rag.chunking import chunk_text

    data = make_pdf(
        [
            "El proponente debe acreditar experiencia minima de cinco anos en "
            "interventoria de obras de infraestructura vial.",
            "Segunda pagina con otros requisitos financieros y tecnicos exigidos.",
        ]
    )
    extraction = extract_pdf(data, enable_ocr=False)
    chunks = chunk_text(extraction.text)

    assert chunks
    # Sin el marcador de página, el fragmento no tendría localizador y la cita
    # no se podría verificar contra el documento.
    assert any(c.page_number is not None for c in chunks)
    assert any("[[pagina:" not in c.content for c in chunks)


def test_marker_never_leaks_into_chunk_content() -> None:
    """El marcador es interno: no debe aparecer en una cita al analista."""

    from app.rag.chunking import chunk_text

    data = make_pdf(["Contenido de prueba con longitud suficiente para fragmentar."])
    extraction = extract_pdf(data, enable_ocr=False)

    chunks = chunk_text(extraction.text)

    assert all("[[pagina:" not in c.content for c in chunks)
    assert MIN_CHARS_PER_PAGE > 0  # el umbral se documenta como constante
