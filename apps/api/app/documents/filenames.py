"""Saneado de nombres de archivo.

Responsabilidad única: convertir lo que envía el cliente en algo que no pueda
escapar de su directorio.

Un nombre como `../../etc/passwd`, uno con separadores de Windows o uno con bytes
nulos no debe llegar nunca al sistema de archivos. Se conserva solo lo que es
inequívocamente un nombre: letras, dígitos, punto, guion y guion bajo.
"""

from __future__ import annotations

import re
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")

# Los sistemas de archivos habituales limitan el nombre a 255 bytes. Se recorta
# antes para no depender de que el motor lo rechace.
MAX_NAME_LENGTH = 200


def safe_filename(name: str | None) -> str | None:
    """Reduce el nombre a algo que no pueda escapar de su directorio.

    Devuelve `None` cuando no queda nada utilizable, para que quien llama no
    tenga que comprobar si el resultado es una cadena vacía.
    """

    if not name:
        return None

    # `Path.name` descarta cualquier componente de ruta, incluidos los de
    # Windows: `..\\..\\x.pdf` queda como `x.pdf`.
    base = Path(name).name
    cleaned = _UNSAFE.sub("_", base).strip("._")
    return cleaned[:MAX_NAME_LENGTH] or None
