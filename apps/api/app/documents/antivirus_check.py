"""Comprobación con antivirus dentro del flujo de validación.

Envuelve el escáner para traducir su resultado al contrato de validación.

La decisión que concentra este módulo: cuando el antivirus no puede analizar, el
resultado depende de si el análisis es obligatorio. Si lo es, se rechaza —un
antivirus caído no es un archivo limpio—. Si no lo es, se acepta pero se declara
que no se analizó, para que quien lea el resultado no lo confunda con «limpio».
"""

from __future__ import annotations

from app.documents.antivirus import AntivirusScanner, AntivirusUnavailableError
from app.documents.validation_rejections import reject
from app.documents.validation_types import QuarantineReason, ValidationResult


def check_antivirus(
    data: bytes,
    *,
    detected_type: str,
    scanner: AntivirusScanner | None,
    require_antivirus: bool,
    warnings: list[str],
) -> ValidationResult | None:
    """Analiza con antivirus. Devuelve un rechazo, o None si puede continuar."""

    if scanner is None:
        warnings.append("no hay antivirus configurado; el archivo no se analizó")
        return None

    if not scanner.available:
        return _unavailable(
            "no fue posible analizar el archivo: el antivirus no está disponible",
            detected_type=detected_type,
            size_bytes=len(data),
            require_antivirus=require_antivirus,
            warnings=warnings,
        )

    try:
        clean, threat = scanner.scan(data)
    except AntivirusUnavailableError as error:
        return _unavailable(
            str(error),
            detected_type=detected_type,
            size_bytes=len(data),
            require_antivirus=require_antivirus,
            warnings=warnings,
        )

    if not clean:
        return reject(
            QuarantineReason.MALWARE,
            f"se detectó contenido malicioso: {threat}",
            detected_type=detected_type,
            size_bytes=len(data),
        )
    return None


def _unavailable(
    detail: str,
    *,
    detected_type: str,
    size_bytes: int,
    require_antivirus: bool,
    warnings: list[str],
) -> ValidationResult | None:
    if require_antivirus:
        return reject(
            QuarantineReason.ANTIVIRUS_UNAVAILABLE,
            detail,
            detected_type=detected_type,
            size_bytes=size_bytes,
        )
    warnings.append(f"no se analizó con antivirus: {detail}")
    return None
