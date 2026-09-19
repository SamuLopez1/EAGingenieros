"""Inspección del contenido real de un archivo.

Responsabilidad única: determinar qué ES un archivo, mirando sus bytes. No
decide si se acepta —eso corresponde al validador— ni sabe de antivirus.

Se mira el contenido y nunca la extensión ni el encabezado declarado por el
cliente: ambos los controla quien sube el archivo, así que un ejecutable
renombrado a `.pdf` no se detectaría por ninguno de los dos.
"""

from __future__ import annotations

import io
import zipfile

# Firmas de contenido peligroso. Un archivo que empieza por una de estas no debe
# procesarse nunca, independientemente de su extensión.
DANGEROUS_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "ejecutable de Windows (PE)"),
    (b"\x7fELF", "ejecutable de Linux (ELF)"),
    (b"\xca\xfe\xba\xbe", "ejecutable Mach-O"),
    (b"\xfe\xed\xfa\xce", "ejecutable Mach-O"),
    (b"\xfe\xed\xfa\xcf", "ejecutable Mach-O"),
    (b"\xcf\xfa\xed\xfe", "ejecutable Mach-O"),
    (b"#!", "script con shebang"),
    (b"<?php", "script PHP"),
    (b"\xd0\xcf\x11\xe0", "documento OLE (puede contener macros)"),
)

# Tipos admitidos y su extensión esperada.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}

DOCX_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def detect_content_type(data: bytes) -> str | None:
    """Determina el tipo real a partir del contenido."""

    if not data:
        return None
    if data[:5] == b"%PDF-":
        return "application/pdf"

    # DOCX y XLSX son archivos ZIP; se distinguen por su estructura interna.
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return None
        if "[Content_Types].xml" not in names:
            return "application/zip"
        if any(n.startswith("word/") for n in names):
            return DOCX_TYPE
        if any(n.startswith("xl/") for n in names):
            return XLSX_TYPE
        return "application/zip"
    return None


def detect_dangerous_signature(data: bytes) -> str | None:
    """Devuelve la descripción de una firma peligrosa, si la hay."""

    for signature, description in DANGEROUS_SIGNATURES:
        if data.startswith(signature):
            return description
    return None


def is_allowed(content_type: str | None) -> bool:
    return content_type in ALLOWED_CONTENT_TYPES
