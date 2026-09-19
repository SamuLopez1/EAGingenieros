"""Comprobaciones de tamaño y coherencia de tipo.

Dos preguntas concretas: ¿el archivo cabe? y ¿lo que dice ser coincide con lo
que es? Ninguna conoce el orden en que se aplican.
"""

from __future__ import annotations

from app.documents.validation_rejections import reject
from app.documents.validation_types import QuarantineReason, ValidationResult

# Tipos genéricos que los navegadores envían con frecuencia. No contradicen al
# contenido real, así que no deben provocar un rechazo.
TOLERATED_DECLARED_TYPES = frozenset({"application/octet-stream", ""})


def check_size(data: bytes, max_bytes: int) -> ValidationResult | None:
    """Comprueba que el archivo no esté vacío ni supere el límite."""

    if not data:
        return reject(QuarantineReason.EMPTY, "el archivo está vacío")
    if len(data) > max_bytes:
        return reject(
            QuarantineReason.TOO_LARGE,
            f"{len(data) // (1024 * 1024)} MB supera el límite de "
            f"{max_bytes // (1024 * 1024)} MB",
            size_bytes=len(data),
        )
    return None


def check_declared_type(
    declared: str | None, detected: str
) -> ValidationResult | None:
    """Comprueba que lo declarado no contradiga al contenido real.

    Se tolera que falte o que sea genérico —los navegadores son inconsistentes—,
    pero se rechaza si contradice: un `.pdf` declarado que es un DOCX indica que
    algo no cuadra.
    """

    if not declared:
        return None
    base = declared.split(";")[0].strip().lower()
    if base in TOLERATED_DECLARED_TYPES or base == detected:
        return None
    return reject(
        QuarantineReason.TYPE_MISMATCH,
        f"declarado como {base} pero el contenido es {detected}",
        detected_type=detected,
    )
