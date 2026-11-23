"""Campos de SECOP para el catálogo y una lectura conservadora de su vigencia."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal, TypedDict

from app.secop.client import RECEPTION_FIELD, parse_timestamp

Validity = Literal["abierto", "cerrado", "vencido", "desconocida"]
CLOSED = (
    "adjudicado", "adjudicada", "adjudicado y celebrado", "proceso adjudicado y celebrado",
    "cancelado", "cancelada", "cerrado", "cerrada", "desierto", "desierta",
    "terminado", "terminada",
)
OFFERING = ("abierto", "abierta", "presentación de oferta", "presentación de ofertas")
OFFER_PHASE = (
    "presentación de oferta", "presentación de ofertas", "presentación de oferta (fase selección)",
)


class SourceFields(TypedDict):
    department: str | None
    city: str | None
    reception_at: datetime | None


def optional_text(payload: Mapping[str, object], field: str) -> str | None:
    value = payload.get(field)
    return value.strip() or None if isinstance(value, str) else None


def source_fields(payload: Mapping[str, object]) -> SourceFields:
    return {
        "department": optional_text(payload, "departamento_entidad"),
        "city": optional_text(payload, "ciudad_entidad"),
        "reception_at": parse_timestamp(payload.get(RECEPTION_FIELD)),
    }


def validity(
    status: str | None, phase: str | None, reception_at: datetime | None, now: datetime
) -> Validity:
    official = (status or "").strip().lower()
    if official in CLOSED:
        return "cerrado"
    accepts_offers = official in OFFERING or (
        official == "publicado" and (phase or "").strip().lower() in OFFER_PHASE
    )
    if reception_at is None or not accepts_offers:
        return "desconocida"
    deadline = reception_at if reception_at.tzinfo else reception_at.replace(tzinfo=UTC)
    return "abierto" if deadline > now else "vencido"
