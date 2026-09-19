"""Inspección de la estructura interna de un archivo comprimido.

Responsabilidad única: coordinar las comprobaciones sobre un ZIP. Un DOCX o un
XLSX son ZIP, así que se aplican a todos los formatos de oficina.

Cubre tres ataques:
- **zip slip**: una entrada con `../` escribiría fuera del directorio.
- **bomba de descompresión**: pocos kilobytes que descomprimen a gigabytes.
- **macros y ejecutables anidados**, que se ejecutan al abrir el documento.

Las bombas de entidades XML se revisan en `xml_bomb_check`, que tiene su propia
dependencia y su propio criterio.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from app.documents.validation_types import QuarantineReason
from app.documents.xml_bomb_check import check_xml_bombs

MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024

MAX_COMPRESSION_RATIO = 100

# Extensiones que no deberían aparecer dentro de un documento de oficina.
EXECUTABLE_SUFFIXES = (".exe", ".dll", ".js", ".vbs", ".ps1", ".bat")


def _check_paths(infos: list[zipfile.ZipInfo]) -> tuple[QuarantineReason, str] | None:
    """Detecta entradas que intentan salir del directorio de extracción."""

    for info in infos:
        name = info.filename
        if name.startswith("/") or ".." in Path(name).parts:
            return (
                QuarantineReason.ZIP_SLIP,
                f"la entrada «{name}» intenta salir del directorio",
            )
    return None


def _check_compression(
    infos: list[zipfile.ZipInfo],
) -> tuple[QuarantineReason, str] | None:
    """Detecta bombas de descompresión."""

    total_uncompressed = sum(i.file_size for i in infos)
    total_compressed = sum(i.compress_size for i in infos) or 1
    ratio = total_uncompressed / total_compressed

    if total_uncompressed > MAX_UNCOMPRESSED_BYTES or ratio > MAX_COMPRESSION_RATIO:
        return (
            QuarantineReason.ZIP_BOMB,
            f"descomprime a {total_uncompressed // (1024 * 1024)} MB "
            f"(proporción {ratio:.0f}x)",
        )
    return None


def _check_names(names: set[str]) -> tuple[QuarantineReason, str] | None:
    """Detecta macros y ejecutables dentro del documento."""

    # Un DOCX con macros trae `vbaProject.bin` y puede ejecutar código al abrirse.
    if any("vbaproject.bin" in n for n in names):
        return (
            QuarantineReason.MACROS,
            "el documento contiene macros (vbaProject.bin)",
        )
    if any(n.endswith(EXECUTABLE_SUFFIXES) for n in names):
        return (
            QuarantineReason.DANGEROUS_TYPE,
            "el archivo comprimido contiene un ejecutable o script",
        )
    return None


def inspect_archive(data: bytes) -> tuple[QuarantineReason | None, str | None]:
    """Inspecciona un ZIP y devuelve el motivo de rechazo, si lo hay."""

    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            names = {i.filename.lower() for i in infos}

            for check in (
                _check_paths(infos),
                _check_compression(infos),
                _check_names(names),
                check_xml_bombs(archive, names),
            ):
                if check is not None:
                    return check
    except zipfile.BadZipFile:
        return QuarantineReason.CORRUPT, "el archivo comprimido está dañado"

    return None, None
