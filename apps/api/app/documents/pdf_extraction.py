"""Extracción de texto de un PDF, con OCR cuando hace falta.

Coordina tres piezas: leer la capa de texto (`pdf_reader`), decidir qué páginas
necesitan reconocimiento (`ocr_policy`) y reconocerlas (`ocr`). La lógica de
decisión vive en la política, no aquí.
"""

from __future__ import annotations

from app.documents.extraction_types import (
    ExtractionError,
    ExtractionResult,
    ExtractionStatus,
)
from app.documents.ocr import DEFAULT_LANGUAGE, recognise_pages
from app.documents.ocr_application import apply_recognition
from app.documents.ocr_policy import MAX_OCR_PAGES, decide_ocr
from app.documents.pdf_reader import read_pdf_pages

__all__ = ["MAX_OCR_PAGES", "extract_pdf", "looks_like_scanned_pdf"]


def extract_pdf(
    data: bytes,
    *,
    password: str | None = None,
    enable_ocr: bool = True,
    ocr_language: str = DEFAULT_LANGUAGE,
    max_ocr_pages: int = MAX_OCR_PAGES,
) -> ExtractionResult:
    """Extrae texto de un PDF, con OCR para las páginas sin texto suficiente.

    Los fallos de lectura se devuelven como resultado fallido en lugar de
    propagarse: quien llama necesita distinguir «no se pudo leer» de «se leyó y
    está vacío», y una excepción sin capturar convertiría el segundo caso en un
    error de servidor.
    """

    try:
        pages = read_pdf_pages(data, password=password)
    except ExtractionError as error:
        return ExtractionResult(status=ExtractionStatus.FAILED, error=str(error))

    if not pages:
        return ExtractionResult(
            status=ExtractionStatus.COMPLETED_WITH_WARNINGS,
            warnings=["el PDF no contiene páginas"],
        )

    decision = decide_ocr(pages, max_pages=max_ocr_pages)
    warnings: list[str] = []
    if decision.warning:
        warnings.append(decision.warning)

    if not decision.needed:
        # Sin páginas que reconocer, el texto digital ya es todo lo que hay.
        return ExtractionResult(status=ExtractionStatus.COMPLETED, pages=pages)

    if not enable_ocr:
        warnings.append("OCR desactivado: hay páginas sin texto que no se procesaron")
        return ExtractionResult(
            status=ExtractionStatus.COMPLETED_WITH_WARNINGS,
            pages=pages,
            warnings=warnings,
            ocr_reason=decision.reason,
        )

    try:
        recognised = recognise_pages(
            data, decision.targets, language=ocr_language
        )
    except ExtractionError as error:
        # El fallo del OCR no invalida el texto digital ya extraído.
        warnings.append(f"el OCR falló: {error}")
        return ExtractionResult(
            status=ExtractionStatus.COMPLETED_WITH_WARNINGS,
            pages=pages,
            warnings=warnings,
            ocr_reason=decision.reason,
        )

    warnings.extend(apply_recognition(pages, recognised))
    return ExtractionResult(
        status=(
            ExtractionStatus.COMPLETED_WITH_WARNINGS if warnings else ExtractionStatus.COMPLETED
        ),
        pages=pages,
        warnings=warnings,
        ocr_reason=decision.reason,
    )


def looks_like_scanned_pdf(data: bytes) -> bool:
    """Indica si un PDF carece de capa de texto, sin extraerlo completo."""

    try:
        pages = read_pdf_pages(data)
    except ExtractionError:
        return False
    return all(p.is_empty for p in pages) if pages else False
