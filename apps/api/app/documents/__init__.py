"""Extracción y validación de documentos.

El módulo se divide por responsabilidad, con un archivo por pregunta:

Validación:
    content_inspector      qué ES el archivo, por sus bytes
    archive_inspector      qué hay dentro del ZIP
    size_and_type_checks   cabe y coincide con lo que dice ser
    antivirus              hay malware
    antivirus_validation   cómo se traduce al contrato de validación
    filenames              el nombre puede escapar de su directorio
    validation_types       qué es un rechazo
    validation_rejections  cómo se construye un rechazo
    validation             aplicar en orden y decidir

Extracción:
    extraction_types       qué es un resultado de extracción
    pdf_reader             leer la capa de texto de un PDF
    ocr                    reconocer texto en imágenes
    ocr_policy             qué páginas necesitan OCR y por qué
    ocr_application        volcar el texto reconocido sobre las páginas
    pdf_extraction         extraer de PDF, con OCR si hace falta
    docx_extraction        extraer de DOCX
    xlsx_extraction        extraer de XLSX
    dispatch               elegir el extractor según el formato

Este punto de entrada reexporta lo que el resto del sistema necesita, para que
nadie dependa de cómo está dividido por dentro.
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
from app.documents.dispatch import SUPPORTED_EXTENSIONS, extract_document
from app.documents.extraction_types import (
    ExtractionError,
    ExtractionResult,
    ExtractionStatus,
    PageText,
    UnsupportedFormatError,
)
from app.documents.filenames import safe_filename
from app.documents.pdf_extraction import looks_like_scanned_pdf
from app.documents.size_and_type_checks import check_declared_type, check_size
from app.documents.validation import DEFAULT_MAX_BYTES, validate_upload
from app.documents.validation_types import QuarantineReason, ValidationResult

# Nombre corto para el caso habitual: extraer de cualquier formato admitido.
extract = extract_document

__all__ = [
    "ALLOWED_CONTENT_TYPES",
    "DEFAULT_MAX_BYTES",
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
    "extract_document",
    "inspect_archive",
    "looks_like_scanned_pdf",
    "safe_filename",
    "validate_upload",
]
