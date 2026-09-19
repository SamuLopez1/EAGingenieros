"""Selección del extractor según el formato.

Responsabilidad única: decidir qué extractor usar y convertir cualquier fallo en
un resultado declarado.

El formato se determina por extensión y, si no la hay, por el tipo MIME
declarado. No se confía solo en el MIME: los navegadores lo envían de forma
inconsistente y un PDF etiquetado como `application/octet-stream` es común.
"""

from __future__ import annotations

from pathlib import Path

from app.documents.docx_extraction import extract_docx
from app.documents.extraction_types import (
    ExtractionError,
    ExtractionResult,
    ExtractionStatus,
)
from app.documents.pdf_extraction import extract_pdf
from app.documents.xlsx_extraction import extract_xlsx

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xlsm"}

# Correspondencia entre tipo MIME y extensión, para cuando el archivo llega sin
# nombre.
_MIME_TO_SUFFIX = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}


def extract_document(
    data: bytes,
    filename: str | None = None,
    *,
    content_type: str | None = None,
    password: str | None = None,
    enable_ocr: bool = True,
    ocr_language: str = "spa",
) -> ExtractionResult:
    """Extrae texto del documento, eligiendo el extractor por formato.

    El formato se decide por extensión y, si no la hay, por el tipo MIME
    declarado. No se confía solo en el MIME: los navegadores lo envían de forma
    inconsistente y un PDF etiquetado como `application/octet-stream` es común.
    """

    suffix = Path(filename or "").suffix.lower()
    if not suffix and content_type:
        suffix = {
            "application/pdf": ".pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        }.get(content_type.split(";")[0].strip().lower(), "")

    if suffix not in SUPPORTED_EXTENSIONS:
        return ExtractionResult(
            status=ExtractionStatus.UNSUPPORTED,
            error=(
                f"formato no soportado: {suffix or 'desconocido'}. "
                f"Soportados: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            ),
        )

    try:
        if suffix == ".pdf":
            return extract_pdf(
                data,
                password=password,
                enable_ocr=enable_ocr,
                ocr_language=ocr_language,
            )
        if suffix == ".docx":
            return extract_docx(data)
        return extract_xlsx(data)
    except ExtractionError as error:
        return ExtractionResult(status=ExtractionStatus.FAILED, error=str(error))
    except Exception as error:  # noqa: BLE001 - ningún fallo debe escapar sin declararse
        return ExtractionResult(
            status=ExtractionStatus.FAILED, error=f"fallo inesperado: {type(error).__name__}"
        )
