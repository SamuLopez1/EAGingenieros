"""Importación oficial limitada a asociaciones verificadas y HTTPS oficial."""

from __future__ import annotations

import ipaddress
import socket
import ssl
from http.client import HTTPException, HTTPSConnection
from pathlib import Path
from time import monotonic
from typing import Literal, Protocol
from urllib.parse import SplitResult, urljoin, urlsplit
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, TypeAdapter, field_validator

DocumentKind = Literal["pliego", "adenda"]
OFFICIAL_HOSTS = frozenset({"community.secop.gov.co", "www.secop.gov.co", "www.datos.gov.co"})


class SourceError(ValueError):
    pass


class SourceTooLarge(SourceError):
    pass


def official_url(value: str) -> SplitResult:
    if any(ord(char) <= 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise SourceError("enlace oficial no permitido")
    target = urlsplit(value)
    if (
        target.scheme != "https"
        or target.hostname not in OFFICIAL_HOSTS
        or target.port not in (None, 443)
        or target.username is not None
        or target.password is not None
        or target.fragment
    ):
        raise SourceError("enlace oficial no permitido")
    return target


class OfficialReference(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: UUID
    source_dataset: Literal["p6dx-8zbt"]
    source_id: str = Field(min_length=1, max_length=128)
    source_record_id: str = Field(min_length=1, max_length=160)
    kind: DocumentKind
    title: str = Field(min_length=1, max_length=140)
    filename: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    verified_at: AwareDatetime
    evidence: str = Field(min_length=1, max_length=300)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        official_url(value)
        return value


def load_manifest(path: Path | None) -> tuple[OfficialReference, ...]:
    if path is None:
        return ()
    try:
        with path.open("rb") as source:
            raw = source.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError
        entries = TypeAdapter(tuple[OfficialReference, ...]).validate_json(raw)
        ids = {entry.id for entry in entries}
        source_keys = {(entry.source_dataset, entry.source_id, entry.source_record_id)
                       for entry in entries}
        if len(ids) != len(entries) or len(source_keys) != len(entries):
            raise ValueError
        return entries
    except (OSError, ValueError):
        raise RuntimeError("El manifiesto de asociaciones oficiales es inválido.") from None


class OfficialDownloader(Protocol):
    def read(self, url: str, limit: int) -> tuple[bytes, str | None]: ...


def pinned_address(host: str) -> str:
    addresses = {
        ipaddress.ip_address(result[4][0]) for result in
        socket.getaddrinfo(host, 443, family=socket.AF_INET, type=socket.SOCK_STREAM)
    }
    if not addresses or any(not addr.is_global or addr.is_multicast for addr in addresses):
        raise SourceError("dirección de descarga no permitida")
    return str(min(addresses, key=lambda addr: (addr.version, int(addr))))


class PinnedHTTPSConnection(HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float) -> None:
        self._tls = ssl.create_default_context()
        super().__init__(host, timeout=timeout, context=self._tls)
        self._address = address

    def connect(self) -> None:
        sock = socket.create_connection((self._address, 443), self.timeout)
        try:
            self.sock = self._tls.wrap_socket(sock, server_hostname=self.host)
        except OSError:
            sock.close()
            raise


class SecopDocumentDownloader:
    def read(self, url: str, limit: int) -> tuple[bytes, str | None]:
        deadline = monotonic() + 20
        try:
            for _ in range(3):
                target = official_url(url)
                host = target.hostname
                assert host is not None
                address = pinned_address(host)
                seconds = min(8.0, deadline - monotonic())
                if seconds <= 0:
                    raise SourceError("agotado el tiempo de descarga")
                connection = PinnedHTTPSConnection(host, address, seconds)
                try:
                    path = target.path or "/"
                    if target.query:
                        path += "?" + target.query
                    connection.request("GET", path, headers={"Accept-Encoding": "identity"})
                    with connection.getresponse() as response:
                        if response.status in (301, 302, 303, 307, 308):
                            location = response.getheader("Location")
                            if not location:
                                raise SourceError("redirección oficial inválida")
                            url = urljoin(url, location)
                            continue
                        if response.status != 200:
                            raise SourceError("el proveedor rechazó la descarga")
                        length = response.getheader("Content-Length")
                        if length is not None and (not length.isascii() or not length.isdecimal()):
                            raise SourceError("tamaño oficial inválido")
                        if length is not None and int(length) > limit:
                            raise SourceTooLarge("el archivo supera el límite")
                        result = bytearray()
                        while True:
                            if monotonic() >= deadline:
                                raise SourceError("agotado el tiempo de descarga")
                            chunk = response.read1(min(65_536, limit + 1 - len(result)))
                            if not chunk:
                                break
                            result.extend(chunk)
                            if len(result) > limit:
                                raise SourceTooLarge("el archivo supera el límite")
                        if length is not None and len(result) != int(length):
                            raise SourceError("respuesta oficial incompleta")
                        return bytes(result), response.getheader("Content-Type")
                finally:
                    connection.close()
        except SourceError:
            raise
        except (OSError, HTTPException, ValueError):
            raise SourceError("no fue posible obtener el documento oficial") from None
        raise SourceError("se superó el límite de redirecciones")
