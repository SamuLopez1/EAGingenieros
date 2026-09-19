"""Extracción de texto de documentos con OCR cuando es necesario."""

from app.documents.extraction import (
    MAX_OCR_PAGES,
    MIN_CHARS_PER_PAGE,
    SUPPORTED_EXTENSIONS,
    ExtractionError,
    ExtractionResult,
    ExtractionStatus,
    PageText,
    UnsupportedFormatError,
    extract,
    extract_docx,
    extract_pdf,
    extract_xlsx,
    looks_like_scanned_pdf,
)

__all__ = [
    "MAX_OCR_PAGES",
    "MIN_CHARS_PER_PAGE",
    "SUPPORTED_EXTENSIONS",
    "ExtractionError",
    "ExtractionResult",
    "ExtractionStatus",
    "PageText",
    "UnsupportedFormatError",
    "extract",
    "extract_docx",
    "extract_pdf",
    "extract_xlsx",
    "looks_like_scanned_pdf",
]
