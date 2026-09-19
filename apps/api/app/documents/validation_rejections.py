"""Construcción de resultados de rechazo.

Responsabilidad única: dar forma a un rechazo. Se separa para que las
comprobaciones no repitan la construcción del resultado y para que añadir un
campo nuevo al contrato se haga en un solo sitio.
"""

from __future__ import annotations

from app.documents.validation_types import QuarantineReason, ValidationResult


def reject(
    reason: QuarantineReason,
    detail: str,
    *,
    detected_type: str | None = None,
    size_bytes: int = 0,
) -> ValidationResult:
    """Construye un resultado de rechazo."""

    return ValidationResult(
        accepted=False,
        reason=reason,
        detail=detail,
        detected_type=detected_type,
        size_bytes=size_bytes,
    )
