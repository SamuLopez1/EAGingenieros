"""Envío de enlaces autenticados con una clave de proveedor estable."""

import re
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

import httpx

ADDRESS = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._%+\-]{0,63}@[A-Za-z0-9][A-Za-z0-9.\-]{0,240}\.[A-Za-z]{2,24}"
)
MailState = Literal[
    "en_curso",
    "aceptado",
    "reintentar",
    "rechazado",
    "incierto",
    "bloqueado",
]


def normalize_address(value: str) -> str:
    address = value.strip().lower()
    if len(address) > 254 or ".." in address or not ADDRESS.fullmatch(address):
        raise ValueError("Dirección de correo inválida.")
    return address


@dataclass(frozen=True)
class Mail:
    sender: str
    recipient: str
    link: str
    company: str = "EAG"

    def payload(self) -> dict[str, object]:
        return {
            "from": self.sender,
            "to": [self.recipient],
            "subject": f"{self.company} | Informe aprobado disponible",
            "text": f"Consulta el informe aprobado en el portal de {self.company}. "
            "Inicia sesión con una cuenta autorizada.\n\n" + self.link,
        }


@dataclass(frozen=True)
class ProviderResult:
    state: Literal["aceptado", "reintentar", "rechazado", "incierto"]
    provider_id: UUID | None = None


class MailGateway(Protocol):
    def send(self, mail: Mail, key: str) -> ProviderResult: ...


@dataclass(frozen=True)
class ResendGateway:
    client: httpx.Client

    def send(self, mail: Mail, key: str) -> ProviderResult:
        try:
            response = self.client.post(
                "/emails", headers={"Idempotency-Key": key}, json=mail.payload()
            )
            if response.is_success:
                return ProviderResult("aceptado", UUID(str(response.json()["id"])))
            if response.status_code == 409:
                code = response.json().get("name")
                return ProviderResult(
                    "reintentar" if code == "concurrent_idempotent_requests" else "incierto",
                )
            if response.status_code in {408, 429} or response.status_code >= 500:
                return ProviderResult("reintentar")
            return ProviderResult("rechazado")
        except httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError:
            return ProviderResult("reintentar")
