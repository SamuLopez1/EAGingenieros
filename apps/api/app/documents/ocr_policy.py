"""Decisión de cuándo aplicar OCR a un PDF.

Responsabilidad única: decidir **qué páginas** necesitan reconocimiento y por qué.
No reconoce nada —eso lo hace `ocr.py`— ni extrae texto.

El criterio es la densidad de texto por página, no el tipo de archivo: un PDF
escaneado y uno digital son indistinguibles por extensión.

Se evalúa **por página** además de por media, porque un pliego puede tener anexos
escaneados entre páginas digitales: promediar ocultaría precisamente esas páginas,
que son las que necesitan OCR.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.documents.extraction_types import PageText

# Caracteres por página por debajo de los cuales se considera que la página es
# una imagen.
MIN_CHARS_PER_PAGE = 80

# Tope de páginas para OCR: reconocer cientos de páginas escaneadas puede tardar
# minutos, y superarlo se declara en lugar de bloquear la petición.
MAX_OCR_PAGES = 50


@dataclass
class OcrDecision:
    """Qué páginas reconocer y por qué."""

    targets: list[int]
    reason: str | None
    warning: str | None = None

    @property
    def needed(self) -> bool:
        return bool(self.targets)


def decide_ocr(
    pages: list[PageText], *, max_pages: int = MAX_OCR_PAGES
) -> OcrDecision:
    """Decide qué páginas necesitan OCR.

    Devuelve también el motivo, para poder explicar por qué se activó en lugar de
    aplicar OCR en silencio.
    """

    if not pages:
        return OcrDecision(targets=[], reason=None)

    total_chars = sum(len(p.text.strip()) for p in pages)
    reason: str | None = None

    if total_chars == 0:
        reason = "el PDF no tiene capa de texto: es un documento escaneado"
    elif total_chars / len(pages) < MIN_CHARS_PER_PAGE:
        reason = (
            f"densidad de texto muy baja ({total_chars // len(pages)} caracteres por "
            f"página, umbral {MIN_CHARS_PER_PAGE}): probablemente escaneado"
        )

    sparse = [p.number for p in pages if len(p.text.strip()) < MIN_CHARS_PER_PAGE]
    targets = sparse or ([p.number for p in pages] if reason else [])

    warning: str | None = None
    if len(targets) > max_pages:
        warning = (
            f"OCR limitado a {max_pages} de {len(targets)} páginas sin texto; "
            "el resto queda sin reconocer"
        )
        targets = targets[:max_pages]

    return OcrDecision(targets=targets, reason=reason, warning=warning)
