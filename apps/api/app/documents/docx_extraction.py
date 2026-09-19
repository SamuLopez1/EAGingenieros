"""Extracción de texto de DOCX.

Las tablas se extraen porque en los pliegos contienen requisitos tabulados, y
omitirlas perdería justamente el contenido que hay que comparar.
"""

from __future__ import annotations

import io

from app.documents.extraction_types import (
    ExtractionError,
    ExtractionResult,
    ExtractionStatus,
    PageText,
)

# Separador de celdas al extraer tablas. Conserva la relación entre columnas, que
# un espacio perdería.
CELL_SEPARATOR = " | "


def extract_docx(data: bytes) -> ExtractionResult:
    """Extrae texto de un DOCX conservando párrafos y tablas.

    Las tablas se extraen porque en pliegos contienen requisitos tabulados, y
    omitirlas perdería exactamente el contenido que hay que comparar.
    """

    import docx
    from docx.opc.exceptions import PackageNotFoundError

    try:
        document = docx.Document(io.BytesIO(data))
    except PackageNotFoundError as error:
        raise ExtractionError(f"DOCX ilegible: {error}") from error
    except Exception as error:  # noqa: BLE001 - archivos corruptos lanzan tipos variados
        raise ExtractionError(f"DOCX ilegible: {error}") from error

    blocks: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if text:
            blocks.append(text)

    for table in document.tables:
        # Se marca cada fila con separador de celdas para que la fragmentación
        # conserve la relación entre columnas.
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                blocks.append(" | ".join(cells))

    text = "\n\n".join(blocks)
    pages = [PageText(number=1, text=text)]
    warnings: list[str] = []
    if not text.strip():
        warnings.append("el DOCX no contiene texto extraíble")
    return ExtractionResult(
        status=(
            ExtractionStatus.COMPLETED_WITH_WARNINGS if warnings else ExtractionStatus.COMPLETED
        ),
        pages=pages,
        warnings=warnings,
    )
