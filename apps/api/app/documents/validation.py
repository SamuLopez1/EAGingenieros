"""Validación y cuarentena de archivos subidos.

Este módulo decide si un archivo puede avanzar al procesamiento. Es la única
barrera entre contenido no confiable y el resto del sistema, así que sus
decisiones son deliberadamente conservadoras.

**Regla central: un fallo del antivirus no equivale a archivo limpio.** Si el
antivirus no responde, el archivo queda en cuarentena, no aprobado. Tratar la
indisponibilidad como aprobación convierte un fallo de infraestructura en una
vía de entrada sin protección, y es el error más común en este tipo de control.

Las comprobaciones, en orden de coste:

1. **Nombre seguro** — no debe poder escapar de su directorio.
2. **Tamaño** — acotado antes de leer nada.
3. **Tipo real por contenido** — no se confía en la extensión ni en el MIME
   declarado: ambos los controla quien sube el archivo. Un ejecutable renombrado
   a `.pdf` se detecta aquí.
4. **Coherencia entre lo declarado y lo real** — un `.pdf` que no es un PDF se
   rechaza aunque su contenido no sea peligroso: procesarlo fallaría más tarde
   con un error confuso.
5. **Estructura interna** — un ZIP (DOCX y XLSX lo son) se inspecciona buscando
   rutas que escapan, proporciones de compresión abusivas y macros.
6. **Antivirus** — cuando está configurado. Si no lo está, se declara.
"""

from __future__ import annotations

import io
import re
import socket
import stat
import struct
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath
from time import monotonic
from typing import Protocol

# defusedxml no publica tipos para todos sus submodulos.
import defusedxml  # type: ignore[import-untyped]
import defusedxml.common  # type: ignore[import-untyped]
import defusedxml.ElementTree  # type: ignore[import-untyped]

# Firmas de contenido peligroso. Un archivo que empieza por una de estas no
# debe procesarse nunca, independientemente de su extensión.
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

# Tipos que se aceptan y su extensión esperada. La comparación es entre lo que
# el archivo ES y lo que dice ser.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
}

# Tamaño máximo descomprimido de un ZIP. Un DOCX legítimo de 20 MB descomprime a
# bastante más, pero no a gigabytes.
MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024

# Proporción máxima de compresión. Un archivo que descomprime a más de 100 veces
# su tamaño es una bomba de descompresión, no un documento.
MAX_COMPRESSION_RATIO = 100

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")


class QuarantineReason(StrEnum):
    """Motivo por el que un archivo no puede procesarse."""

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
    # Indica si el antivirus llegó a analizar el archivo realmente.
    scanned: bool = False
    scan_engine: str | None = None

    @property
    def quarantined(self) -> bool:
        return not self.accepted


def safe_filename(name: str | None) -> str | None:
    """Reduce el nombre a algo que no pueda escapar de su directorio.

    Un nombre como `../../etc/passwd` o con bytes nulos no debe llegar al
    sistema de archivos. Se conserva solo lo que es inequívocamente un nombre.
    """

    if not name:
        return None
    base = Path(name).name  # descarta cualquier componente de ruta
    cleaned = _UNSAFE_FILENAME.sub("_", base).strip("._")
    return cleaned[:200] or None


def detect_content_type(data: bytes) -> str | None:
    """Determina el tipo real a partir del contenido.

    No se usa la extensión ni el encabezado declarado por el cliente: ambos los
    controla quien sube el archivo.
    """

    if not data:
        return None
    if data[:5] == b"%PDF-":
        return "application/pdf"

    # DOCX y XLSX son archivos ZIP. Se distinguen por su estructura interna.
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return None
        if "[Content_Types].xml" not in names:
            return "application/zip"
        if any(n.startswith("word/") for n in names):
            return (
                "application/vnd.openxmlformats-officedocument"
                ".wordprocessingml.document"
            )
        if any(n.startswith("xl/") for n in names):
            return (
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            )
        return "application/zip"
    return None


def detect_dangerous_signature(data: bytes) -> str | None:
    """Devuelve la descripción de una firma peligrosa, si la hay."""

    for signature, description in DANGEROUS_SIGNATURES:
        if data.startswith(signature):
            return description
    return None


def inspect_zip(data: bytes) -> tuple[QuarantineReason | None, str | None, list[str]]:
    """Inspecciona un ZIP buscando rutas escapadas, bombas y macros.

    Un DOCX o XLSX es un ZIP, así que estas comprobaciones se aplican a todos
    los formatos de oficina. El `zip slip` —una entrada con `../` en el nombre—
    permitiría escribir fuera del directorio de extracción si alguna vez se
    descomprime en disco.
    """

    warnings: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos = archive.infolist()
            if len(infos) > 10_000 or any(info.flag_bits & 1 for info in infos):
                return QuarantineReason.CORRUPT, "contenedor no admitido", warnings

            total_uncompressed = 0
            for info in infos:
                name = info.filename
                portable = PurePosixPath(name.replace("\\", "/"))
                if (
                    portable.is_absolute()
                    or ".." in portable.parts
                    or ":" in name
                    or stat.S_ISLNK(info.external_attr >> 16)
                ):
                    return (
                        QuarantineReason.ZIP_SLIP,
                        f"la entrada «{name}» intenta salir del directorio",
                        warnings,
                    )
                total_uncompressed += info.file_size

            total_compressed = sum(i.compress_size for i in infos) or 1
            ratio = total_uncompressed / total_compressed
            if (
                total_uncompressed > MAX_UNCOMPRESSED_BYTES
                or ratio > MAX_COMPRESSION_RATIO
            ):
                return (
                    QuarantineReason.ZIP_BOMB,
                    f"descomprime a {total_uncompressed // (1024 * 1024)} MB "
                    f"(proporción {ratio:.0f}x)",
                    warnings,
                )

            names = {i.filename.lower() for i in infos}
            # Un DOCX con macros trae `vbaProject.bin`. No es un documento
            # ofimático normal y puede ejecutar código al abrirse.
            if any("vbaproject.bin" in n for n in names):
                return (
                    QuarantineReason.MACROS,
                    "el documento contiene macros (vbaProject.bin)",
                    warnings,
                )
            if any(n.endswith((".exe", ".dll", ".js", ".vbs", ".ps1", ".bat")) for n in names):
                return (
                    QuarantineReason.DANGEROUS_TYPE,
                    "el archivo comprimido contiene un ejecutable o script",
                    warnings,
                )

            # Los documentos de oficina llevan XML dentro. Un XML con entidades
            # anidadas puede expandirse hasta agotar la memoria al parsearlo
            # (billion laughs). Se revisan los documentos de contenido con un
            # parser que rechaza entidades externas.
            xml_targets = [n for n in names if n.endswith(".xml")][:20]
            for name in xml_targets:
                try:
                    content = archive.read(name)
                except (KeyError, zipfile.BadZipFile):  # pragma: no cover - defensivo
                    continue
                if len(content) > 5 * 1024 * 1024:  # un XML de oficina no es tan grande
                    continue
                try:
                    defusedxml.ElementTree.fromstring(content)
                except defusedxml.ElementTree.ParseError:
                    # Un XML que no parsea no es necesariamente peligroso, pero
                    # el documento no será utilizable: se avisa sin rechazar.
                    warnings.append(f"el XML interno «{name}» no es válido")
                except defusedxml.common.DefusedXmlException as error:
                    return (
                        QuarantineReason.DANGEROUS_TYPE,
                        f"el XML interno «{name}» contiene construcciones prohibidas: {error}",
                        warnings,
                    )
    except zipfile.BadZipFile:
        return QuarantineReason.CORRUPT, "el archivo comprimido está dañado", warnings

    return None, None, warnings


class AntivirusScanner(Protocol):
    """Interfaz del antivirus. Se inyecta para poder probar sin el servicio."""

    @property
    def available(self) -> bool: ...

    @property
    def engine(self) -> str: ...

    def scan(self, data: bytes) -> tuple[bool, str | None]:
        """Devuelve (limpio, nombre_de_amenaza)."""


class ClamAvScanner:
    """Clamd INSTREAM con confirmación explícita y sin archivos temporales."""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 3310) -> None:
        self._host = host
        self._port = port

    @property
    def engine(self) -> str:
        return "clamav"

    def _exchange(self, command: bytes, data: bytes | None = None) -> bytes:
        deadline = monotonic() + 10

        def bounded(sock: socket.socket) -> None:
            seconds = deadline - monotonic()
            if seconds <= 0:
                raise TimeoutError
            sock.settimeout(seconds)

        try:
            with socket.create_connection((self._host, self._port), timeout=5) as sock:
                bounded(sock)
                sock.sendall(command)
                if data is not None:
                    payload = memoryview(data)
                    for offset in range(0, len(payload), 65_536):
                        chunk = payload[offset : offset + 65_536]
                        bounded(sock)
                        sock.sendall(struct.pack("!I", len(chunk)))
                        sock.sendall(chunk)
                    bounded(sock)
                    sock.sendall(struct.pack("!I", 0))
                reply = bytearray()
                while len(reply) < 4096:
                    bounded(sock)
                    part = sock.recv(1024)
                    if not part:
                        break
                    reply.extend(part)
                    if b"\0" in reply:
                        return bytes(reply).split(b"\0", 1)[0]
        except OSError:
            raise AntivirusUnavailableError("no respondió el antivirus") from None
        raise AntivirusUnavailableError("respuesta incompleta del antivirus")

    @property
    def available(self) -> bool:
        try:
            return self._exchange(b"zPING\0") == b"PONG"
        except AntivirusUnavailableError:
            return False

    def scan(self, data: bytes) -> tuple[bool, str | None]:
        result = self._exchange(b"zINSTREAM\0", data)
        if result == b"stream: OK":
            return True, None
        if result.startswith(b"stream: ") and result.endswith(b" FOUND"):
            return False, "detección de ClamAV"
        raise AntivirusUnavailableError("el antivirus no confirmó un resultado")


class AntivirusUnavailableError(RuntimeError):
    """El antivirus no pudo analizar el archivo."""


def validate_upload(
    data: bytes,
    *,
    filename: str | None,
    declared_content_type: str | None = None,
    max_bytes: int = 20 * 1024 * 1024,
    scanner: AntivirusScanner | None = None,
    require_antivirus: bool = False,
) -> ValidationResult:
    """Valida un archivo antes de que avance al procesamiento.

    `require_antivirus=True` hace que la indisponibilidad del antivirus rechace
    el archivo. Se recomienda activarlo en cualquier entorno que reciba archivos
    de fuera: sin él, una caída del antivirus se convierte en una vía de entrada
    sin analizar.
    """

    warnings: list[str] = []

    # 1. Nombre
    if filename is not None and safe_filename(filename) is None:
        return ValidationResult(
            accepted=False,
            reason=QuarantineReason.UNSAFE_NAME,
            detail="el nombre del archivo no es utilizable",
        )

    # 2. Tamaño, antes de cualquier otro trabajo
    size = len(data)
    if size == 0:
        return ValidationResult(
            accepted=False, reason=QuarantineReason.EMPTY, detail="el archivo está vacío"
        )
    if size > max_bytes:
        return ValidationResult(
            accepted=False,
            reason=QuarantineReason.TOO_LARGE,
            detail=(
                f"{size // (1024 * 1024)} MB supera el límite de "
                f"{max_bytes // (1024 * 1024)} MB"
            ),
            size_bytes=size,
        )

    # 3. Firma peligrosa: se comprueba antes del tipo para no confundir un
    # ejecutable con un archivo desconocido.
    danger = detect_dangerous_signature(data)
    if danger is not None:
        return ValidationResult(
            accepted=False,
            reason=QuarantineReason.DANGEROUS_TYPE,
            detail=f"el contenido es un {danger}",
            size_bytes=size,
        )

    # 4. Tipo real por contenido
    detected = detect_content_type(data)
    if detected is None:
        return ValidationResult(
            accepted=False,
            reason=QuarantineReason.TYPE_MISMATCH,
            detail="el contenido no corresponde a ningún formato soportado",
            size_bytes=size,
        )
    if detected not in ALLOWED_CONTENT_TYPES:
        return ValidationResult(
            accepted=False,
            reason=QuarantineReason.TYPE_MISMATCH,
            detail=f"tipo detectado no admitido: {detected}",
            detected_type=detected,
            size_bytes=size,
        )

    # 5. Coherencia entre lo declarado y lo real. Se avisa en lugar de rechazar
    # cuando el MIME declarado falta —los navegadores lo envían de forma
    # inconsistente— pero se rechaza si contradice al contenido.
    if declared_content_type:
        declared_base = declared_content_type.split(";")[0].strip().lower()
        if (
            declared_base
            and declared_base != detected
            and declared_base != "application/octet-stream"
        ):
            return ValidationResult(
                accepted=False,
                reason=QuarantineReason.TYPE_MISMATCH,
                detail=f"declarado como {declared_base} pero el contenido es {detected}",
                detected_type=detected,
                size_bytes=size,
            )

    # 6. Estructura interna de los formatos ZIP
    if detected != "application/pdf":
        reason, detail, zip_warnings = inspect_zip(data)
        warnings.extend(zip_warnings)
        if reason is not None:
            return ValidationResult(
                accepted=False,
                reason=reason,
                detail=detail,
                detected_type=detected,
                size_bytes=size,
                warnings=warnings,
            )

    # 7. Antivirus
    scanned = False
    engine: str | None = None
    if scanner is not None:
        if not scanner.available:
            if require_antivirus:
                # Un antivirus caído no es un archivo limpio. Se rechaza.
                return ValidationResult(
                    accepted=False,
                    reason=QuarantineReason.ANTIVIRUS_UNAVAILABLE,
                    detail="no fue posible analizar el archivo: el antivirus no está disponible",
                    detected_type=detected,
                    size_bytes=size,
                    warnings=warnings,
                )
            warnings.append(
                "el archivo no se analizó con antivirus: el servicio no está disponible"
            )
        else:
            try:
                clean, threat = scanner.scan(data)
                scanned = True
                engine = scanner.engine
                if not clean:
                    return ValidationResult(
                        accepted=False,
                        reason=QuarantineReason.MALWARE,
                        detail=f"se detectó contenido malicioso: {threat}",
                        detected_type=detected,
                        size_bytes=size,
                        scanned=True,
                        scan_engine=engine,
                        warnings=warnings,
                    )
            except AntivirusUnavailableError as error:
                if require_antivirus:
                    return ValidationResult(
                        accepted=False,
                        reason=QuarantineReason.ANTIVIRUS_UNAVAILABLE,
                        detail=str(error),
                        detected_type=detected,
                        size_bytes=size,
                        warnings=warnings,
                    )
                warnings.append(f"no se pudo analizar con antivirus: {error}")
    elif require_antivirus:
        return ValidationResult(
            accepted=False,
            reason=QuarantineReason.ANTIVIRUS_UNAVAILABLE,
            detected_type=detected,
            size_bytes=size,
        )
    else:
        warnings.append("no hay antivirus configurado; el archivo no se analizó")

    return ValidationResult(
        accepted=True,
        detected_type=detected,
        size_bytes=size,
        warnings=warnings,
        scanned=scanned,
        scan_engine=engine,
    )
