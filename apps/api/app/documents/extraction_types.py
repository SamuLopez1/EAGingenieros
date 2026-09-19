"""Contrato de la extracción de texto.

Se separa para que quien solo necesite interpretar un resultado no arrastre las
dependencias de los extractores: leer un PDF requiere pypdf, interpretar el
resultado no requiere nada.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ExtractionStatus(StrEnum):
    COMPLETED = "completado"
    COMPLETED_WITH_WARNINGS = "completado_con_advertencias"
    FAILED = "fallido"
    UNSUPPORTED = "no_soportado"


class ExtractionError(RuntimeError):
    """El archivo no se pudo procesar."""


class UnsupportedFormatError(ExtractionError):
    """El formato no está entre los soportados."""


@dataclass
class PageText:
    """Texto de una unidad con su procedencia."""

    number: int
    text: str
    from_ocr: bool = False
    ocr_confidence: float | None = None

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()


@dataclass
class ExtractionResult:
    """Resultado completo de extraer un documento."""

    status: ExtractionStatus
    pages: list[PageText] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    # Motivo por el que se activó el OCR, cuando ocurrió.
    ocr_reason: str | None = None

    @property
    def text(self) -> str:
        """Texto completo con marcadores de página.

        Los marcadores son la única forma de que la fragmentación sepa de qué
        página viene cada fragmento. Sin ellos, una cita no tendría localizador.
        """

        parts: list[str] = []
        for page in self.pages:
            if page.is_empty:
                continue
            parts.append(f"[[pagina:{page.number}]]")
            parts.append(page.text.strip())
            parts.append("")
        return "\n".join(parts).strip()

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def ocr_page_numbers(self) -> list[int]:
        return [p.number for p in self.pages if p.from_ocr]

    @property
    def is_usable(self) -> bool:
        """Indica si el resultado sirve para indexar."""

        return (
            self.status
            in (ExtractionStatus.COMPLETED, ExtractionStatus.COMPLETED_WITH_WARNINGS)
            and bool(self.text.strip())
        )


