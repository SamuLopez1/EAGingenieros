"""Detección de bombas de entidades en el XML interno de un documento.

Responsabilidad única: detectar el ataque «billion laughs», en el que cada
entidad expande a varias anteriores de modo que un archivo de pocos kilobytes
descomprime a gigabytes al parsearlo.

Se usa un parser que rechaza entidades externas —el parser estándar las expande—
y se limita cuántos XML se inspeccionan: suficiente para detectar el ataque sin
recorrer cientos de entradas.
"""

from __future__ import annotations

import zipfile

import defusedxml  # type: ignore[import-untyped]
import defusedxml.common  # type: ignore[import-untyped]
import defusedxml.ElementTree  # type: ignore[import-untyped]

from app.documents.validation_types import QuarantineReason

# Un XML de oficina no es más grande que esto; revisar más sería gastar memoria
# en algo que no es un documento normal.
MAX_XML_BYTES = 5 * 1024 * 1024

# Revisar como máximo estos XML por archivo.
MAX_XML_FILES = 20


def check_xml_bombs(
    archive: zipfile.ZipFile, names: set[str]
) -> tuple[QuarantineReason, str] | None:
    """Revisa el XML interno buscando construcciones prohibidas.

    Un XML que no parsea no se rechaza: no es peligroso, aunque el documento
    pueda no ser utilizable.
    """

    targets = [n for n in names if n.endswith(".xml")][:MAX_XML_FILES]

    for name in targets:
        try:
            content = archive.read(name)
        except (KeyError, zipfile.BadZipFile):  # pragma: no cover - defensivo
            continue

        if len(content) > MAX_XML_BYTES:
            continue

        try:
            defusedxml.ElementTree.fromstring(content)
        except defusedxml.ElementTree.ParseError:
            continue
        except defusedxml.common.DefusedXmlException as error:
            return (
                QuarantineReason.DANGEROUS_TYPE,
                f"el XML interno «{name}» contiene construcciones prohibidas: {error}",
            )

    return None
