"""Lectura de la capa de texto de un PDF.

Responsabilidad única: extraer el texto que el PDF ya contiene, sin OCR. Un PDF
escaneado no tiene capa de texto y este módulo devuelve páginas vacías; decidir
qué hacer con eso corresponde al extractor.
"""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.documents.extraction_types import ExtractionError, PageText


def read_pdf_pages(data: bytes, password: str | None = None) -> list[PageText]:
    """Extrae el texto digital de un PDF, página a página."""


    try:
        reader = PdfReader(io.BytesIO(data))
    except PdfReadError as error:
        raise ExtractionError(f"PDF ilegible: {error}") from error

    if reader.is_encrypted:
        # Un PDF cifrado sin contraseña no se puede leer. Se declara en lugar de
        # devolver vacío, que se confundiría con un documento sin texto.
        if password:
            try:
                reader.decrypt(password)
            except Exception as error:  # noqa: BLE001 - el proveedor lanza tipos variados
                raise ExtractionError("PDF cifrado y la contraseña no es válida") from error
        else:
            raise ExtractionError("PDF cifrado: requiere contraseña")

    pages: list[PageText] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - un página corrupta no debe abortar el resto
            pages.append(PageText(number=index, text=""))
            continue
        pages.append(PageText(number=index, text=text))
    return pages
