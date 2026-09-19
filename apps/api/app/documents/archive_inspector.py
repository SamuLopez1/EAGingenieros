"""Inspección de la estructura interna de un archivo comprimido.

Responsabilidad única: detectar construcciones peligrosas dentro de un ZIP. Un
DOCX o un XLSX son ZIP, así que estas comprobaciones se aplican a todos los
formatos de oficina.

Los tres ataques que cubre:

- **zip slip**: una entrada con `../` en el nombre escribiría fuera del
  directorio de extracción.
- **bomba de descompresión**: pocos kilobytes que descomprimen a gigabytes.
- **macros y ejecutables anidados**: código que se ejecuta al abrir el documento.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import defusedxml  # type: ignore[import-untyped]
import defusedxml.common  # type: ignore[import-untyped]
import defusedxml.ElementTree  # type: ignore[import-untyped]

from app.documents.validation_types import QuarantineReason

# Un DOCX legítimo de 20 MB descomprime a bastante más, pero no a gigabytes.
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024

# Un archivo que descomprime a más de 100 veces su tamaño es una bomba.
MAX_COMPRESSION_RATIO = 100

# Extensiones que no deberían aparecer dentro de un documento de oficina.
EXECUTABLE_SUFFIXES = (".exe", ".dll", ".js", ".vbs", ".ps1", ".bat")

# Un XML de oficina no es más grande que esto; revisar más sería gastar memoria
# en algo que no es un documento normal.
MAX_XML_BYTES = 5 * 1024 * 1024

# Revisar como máximo estos XML por archivo: suficiente para detectar el ataque
# sin recorrer cientos de entradas.
MAX_XML_FILES = 20


def _check_paths(infos: list[zipfile.ZipInfo]) -> tuple[QuarantineReason, str] | None:
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


def _check_xml(
    archive: zipfile.ZipFile, names: set[str]
) -> tuple[QuarantineReason, str] | None:
    """Revisa el XML interno buscando bombas de entidades.

    Es el ataque «billion laughs»: cada entidad expande a varias anteriores, de
    modo que un archivo de pocos kilobytes descomprime a gigabytes.
    """

    for name in [n for n in names if n.endswith(".xml")][:MAX_XML_FILES]:
        try:
            content = archive.read(name)
        except (KeyError, zipfile.BadZipFile):  # pragma: no cover - defensivo
            continue
        if len(content) > MAX_XML_BYTES:
            continue
        try:
            defusedxml.ElementTree.fromstring(content)
        except defusedxml.ElementTree.ParseError:
            # Un XML que no parsea no es peligroso, pero el documento no será
            # utilizable: se avisa sin rechazar.
            continue
        except defusedxml.common.DefusedXmlException as error:
            return (
                QuarantineReason.DANGEROUS_TYPE,
                f"el XML interno «{name}» contiene construcciones prohibidas: {error}",
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
                _check_xml(archive, names),
            ):
                if check is not None:
                    return check
    except zipfile.BadZipFile:
        return QuarantineReason.CORRUPT, "el archivo comprimido está dañado"

    return None, None
