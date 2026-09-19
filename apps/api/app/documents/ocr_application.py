"""Volcado del texto reconocido sobre las páginas.

Responsabilidad única: aplicar el resultado del OCR a las páginas y decidir qué
avisos produce. Sabe de confianza y de reemplazo de texto; no reconoce ni decide
qué páginas procesar.

El texto reconocido **reemplaza** al vacío en lugar de concatenarse: el original
no aporta nada y concatenar duplicaría el contenido, con lo que un fragmento
citaría dos veces la misma frase.
"""

from __future__ import annotations

from app.documents.extraction_types import PageText

# Por debajo de esta confianza se avisa: el texto puede tener errores que
# afecten a una cita.
MIN_TRUSTED_CONFIDENCE = 0.6


def apply_recognition(
    pages: list[PageText], recognised: dict[int, tuple[str, float | None]]
) -> list[str]:
    """Vuelca el texto reconocido sobre las páginas y devuelve los avisos."""

    by_number = {p.number: p for p in pages}
    low_confidence: list[int] = []

    for number, (text, confidence) in recognised.items():
        page = by_number.get(number)
        if page is None or not text.strip():
            continue
        # El texto reconocido reemplaza al vacío; no se concatena, porque el
        # original no aporta nada y duplicaría el contenido.
        page.text = text
        page.from_ocr = True
        page.ocr_confidence = confidence
        if confidence is not None and confidence < 0.6:
            low_confidence.append(number)

    warnings: list[str] = []
    if low_confidence:
        warnings.append(
            f"OCR con confianza baja en las páginas {low_confidence}: "
            "conviene revisarlas manualmente antes de confiar en sus citas"
        )
    still_empty = [p.number for p in pages if p.is_empty]
    if still_empty:
        warnings.append(f"páginas sin texto tras el OCR: {still_empty}")
    return warnings
