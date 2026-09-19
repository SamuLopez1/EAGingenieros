"""Análisis antivirus.

Responsabilidad única: decir si un archivo contiene malware. No decide si se
acepta —eso corresponde al validador— y no inspecciona estructura.

La regla que gobierna este módulo: **cuando el antivirus no puede analizar, no
devuelve «limpio»**. Lanza una excepción para que quien decide pueda distinguir
«analizado y limpio» de «no analizado». Devolver `True` ante un fallo
convertiría la caída del antivirus en una aprobación silenciosa, que es el error
más común y el más difícil de detectar en este tipo de control.
"""

from __future__ import annotations

from typing import Protocol

import pyclamd  # type: ignore[import-untyped]


class AntivirusUnavailableError(RuntimeError):
    """El antivirus no pudo analizar el archivo."""


class AntivirusScanner(Protocol):
    """Interfaz del antivirus. Se inyecta para poder probar sin el servicio."""

    @property
    def available(self) -> bool: ...

    @property
    def engine(self) -> str: ...

    def scan(self, data: bytes) -> tuple[bool, str | None]:
        """Devuelve (limpio, nombre_de_amenaza)."""


class ClamAvScanner:
    """Antivirus ClamAV por socket local.

    Se usa el socket y no la línea de comandos: evita escribir el archivo en
    disco —donde quedaría sin cifrar y sin borrar si el proceso muere— y es más
    rápido para archivos pequeños.
    """

    def __init__(self, *, host: str = "127.0.0.1", port: int = 3310) -> None:
        self._host = host
        self._port = port

    @property
    def engine(self) -> str:
        return f"clamav:{self._host}:{self._port}"

    @property
    def available(self) -> bool:
        try:
            client = pyclamd.ClamdNetworkSocket(self._host, self._port)
            return bool(client.ping())
        except Exception:  # noqa: BLE001 - cualquier fallo significa no disponible
            return False

    def scan(self, data: bytes) -> tuple[bool, str | None]:
        """Analiza el contenido. Lanza si el antivirus no responde."""

        try:
            client = pyclamd.ClamdNetworkSocket(self._host, self._port)
            result = client.scan_stream(data)
        except Exception as error:  # noqa: BLE001 - el error se propaga como fallo
            raise AntivirusUnavailableError(
                f"el antivirus no respondió: {type(error).__name__}"
            ) from error

        if not result:
            return True, None
        # `scan_stream` devuelve {clave: (estado, nombre)} o {clave: None}.
        for value in result.values():
            if value and value[0] == "FOUND":
                return False, str(value[1])
        return True, None
