"""Extracción de texto de XLSX.

Cada hoja es una página, de modo que el localizador de un fragmento señala la hoja
de la que proviene.
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


def extract_xlsx(data: bytes) -> ExtractionResult:
    """Extrae texto de un XLSX, hoja por hoja.

    Cada hoja es una página, de modo que el localizador de un fragmento señala la
    hoja de la que proviene. Dentro de la hoja, las filas se separan con ` | `
    para conservar la relación entre columnas.
    """

    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except InvalidFileException as error:
        raise ExtractionError(f"XLSX ilegible: {error}") from error
    except Exception as error:  # noqa: BLE001 - archivos corruptos lanzan tipos variados
        raise ExtractionError(f"XLSX ilegible: {error}") from error

    pages: list[PageText] = []
    warnings: list[str] = []
    try:
        for index, sheet in enumerate(workbook.worksheets, start=1):
            rows: list[str] = []
            for row in sheet.iter_rows(values_only=True):
                cells = ["" if v is None else str(v).strip() for v in row]
                if any(cells):
                    rows.append(" | ".join(cells))
            body = f"[Hoja: {sheet.title}]\n" + "\n".join(rows) if rows else ""
            pages.append(PageText(number=index, text=body))
    finally:
        workbook.close()

    if not any(p.text.strip() for p in pages):
        warnings.append("el XLSX no contiene datos legibles")
    return ExtractionResult(
        status=(
            ExtractionStatus.COMPLETED_WITH_WARNINGS if warnings else ExtractionStatus.COMPLETED
        ),
        pages=pages,
        warnings=warnings,
    )
