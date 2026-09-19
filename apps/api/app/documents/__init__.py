"""Extracción y validación de documentos.

El módulo se divide por responsabilidad: inspección de contenido, inspección de
archivos comprimidos, antivirus, saneado de nombres y extracción de texto. Este
punto de entrada reexporta lo que el resto del sistema necesita.
"""

from app.documents.antivirus import (
    AntivirusScanner,
    AntivirusUnavailableError,
    ClamAvScanner,
)
from app.documents.archive_inspector import inspect_archive
from app.documents.content_inspector import (
    ALLOWED_CONTENT_TYPES,
    detect_content_type,
    detect_dangerous_signature,
)
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
from app.documents.filenames import safe_filename
from app.documents.size_and_type_checks import check_declared_type, check_size
from app.documents.validation import DEFAULT_MAX_BYTES, validate_upload
from app.documents.validation_types import QuarantineReason, ValidationResult

__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "DEFAULT_MAX_BYTES",
    "MAX_OCR_PAGES",
    "MIN_CHARS_PER_PAGE",
    "SUPPORTED_EXTENSIONS",
    "AntivirusScanner",
    "AntivirusUnavailableError",
    "ClamAvScanner",
    "ExtractionError",
    "ExtractionResult",
    "ExtractionStatus",
    "PageText",
    "QuarantineReason",
    "UnsupportedFormatError",
    "ValidationResult",
    "check_declared_type",
    "check_size",
    "detect_content_type",
    "detect_dangerous_signature",
    "extract",
    "extract_docx",
    "extract_pdf",
    "extract_xlsx",
    "inspect_archive",
    "looks_like_scanned_pdf",
    "safe_filename",
    "validate_upload",
]
