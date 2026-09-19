"""Validación de un archivo antes de que avance al procesamiento.

Responsabilidad única: aplicar las comprobaciones en orden y decidir. No
inspecciona bytes ni habla con el antivirus; delega y compone el resultado.

El orden va de lo más barato a lo más caro: un ejecutable renombrado se rechaza
sin gastar un análisis de antivirus.
"""

from __future__ import annotations

from app.documents.antivirus import AntivirusScanner
from app.documents.antivirus_check import check_antivirus
from app.documents.archive_inspector import inspect_archive
from app.documents.content_inspector import (
    detect_content_type,
    detect_dangerous_signature,
    is_allowed,
)
from app.documents.filenames import safe_filename
from app.documents.size_and_type_checks import check_declared_type, check_size
from app.documents.validation_rejections import reject
from app.documents.validation_types import QuarantineReason, ValidationResult

DEFAULT_MAX_BYTES = 20 * 1024 * 1024

PDF_TYPE = "application/pdf"


def validate_upload(
    data: bytes,
    *,
    filename: str | None,
    declared_content_type: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    scanner: AntivirusScanner | None = None,
    require_antivirus: bool = False,
) -> ValidationResult:
    """Valida un archivo antes de que avance al procesamiento."""

    warnings: list[str] = []

    if filename is not None and safe_filename(filename) is None:
        return reject(
            QuarantineReason.UNSAFE_NAME, "el nombre del archivo no es utilizable"
        )

    if (rejected := check_size(data, max_bytes)) is not None:
        return rejected

    # La firma peligrosa se comprueba antes del tipo para no confundir un
    # ejecutable con un archivo simplemente desconocido.
    if (danger := detect_dangerous_signature(data)) is not None:
        return reject(
            QuarantineReason.DANGEROUS_TYPE,
            f"el contenido es un {danger}",
            size_bytes=len(data),
        )

    detected = detect_content_type(data)
    if detected is None or not is_allowed(detected):
        return reject(
            QuarantineReason.TYPE_MISMATCH,
            "el contenido no corresponde a un formato admitido "
            f"({detected or 'desconocido'})",
            detected_type=detected,
            size_bytes=len(data),
        )

    if (mismatch := check_declared_type(declared_content_type, detected)) is not None:
        return mismatch

    # La inspección interna solo aplica a los formatos que son ZIP.
    if detected != PDF_TYPE:
        reason, detail = inspect_archive(data)
        if reason is not None:
            return reject(
                reason, detail or "", detected_type=detected, size_bytes=len(data)
            )

    rejected = check_antivirus(
        data,
        detected_type=detected,
        scanner=scanner,
        require_antivirus=require_antivirus,
        warnings=warnings,
    )
    if rejected is not None:
        return rejected

    scanned = scanner is not None and scanner.available
    return ValidationResult(
        accepted=True,
        detected_type=detected,
        size_bytes=len(data),
        warnings=warnings,
        scanned=scanned,
        scan_engine=scanner.engine if scanned and scanner is not None else None,
    )
