"""Tipos del resultado de validación.

Separados de la lógica para que quien solo necesite interpretar un resultado no
tenga que importar el módulo que lo produce, con su detector de firmas y su
cliente de antivirus.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class QuarantineReason(StrEnum):
    """Motivo por el que un archivo no puede procesarse.

    Se enumera en lugar de usar texto libre: un motivo tipado permite que quien
    consume el resultado decida sin comparar cadenas, y evita que dos puntos del
    código escriban el mismo motivo de forma distinta.
    """

    UNSAFE_NAME = "nombre_inseguro"
    TOO_LARGE = "demasiado_grande"
    EMPTY = "vacio"
    DANGEROUS_TYPE = "tipo_peligroso"
    TYPE_MISMATCH = "tipo_no_coincide"
    ZIP_SLIP = "ruta_escapada_en_zip"
    ZIP_BOMB = "bomba_de_descompresion"
    MACROS = "macros_presentes"
    CORRUPT = "archivo_corrupto"
    MALWARE = "malware_detectado"
    ANTIVIRUS_UNAVAILABLE = "antivirus_no_disponible"


@dataclass
class ValidationResult:
    """Resultado de validar un archivo."""

    accepted: bool
    reason: QuarantineReason | None = None
    detail: str | None = None
    detected_type: str | None = None
    size_bytes: int = 0
    warnings: list[str] = field(default_factory=list)
    # Indica si el antivirus llegó a analizar el archivo realmente. Es el campo
    # que distingue «limpio» de «no analizado», y esa diferencia importa.
    scanned: bool = False
    scan_engine: str | None = None

    @property
    def quarantined(self) -> bool:
        return not self.accepted
