"""Contratos HTTP del perfil empresarial.

Separados de las rutas para que el archivo de endpoints contenga endpoints. Un
módulo que mezcla veinte definiciones de esquema con la lógica de las peticiones
obliga a saltar entre dos responsabilidades distintas para leer una sola ruta.

Los nombres siguen el sufijo `Request`/`Response` de forma consistente: al mirar
una firma se sabe de inmediato en qué dirección viaja el dato.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class SectionReadinessResponse(BaseModel):
    """Preparación de una sección del perfil."""

    name: str
    total: int
    verified: int
    with_evidence: int
    expired: int


class ProfileReadinessResponse(BaseModel):
    """Resumen de si el perfil puede usarse para comparar.

    Un perfil a medias produce comparaciones engañosas, así que conviene saberlo
    antes de analizar.
    """

    version_id: int | None
    version: int | None
    total_records: int
    usable_records: int
    is_ready: bool
    sections: list[SectionReadinessResponse]
    notes: list[str]


class ProfileVersionResponse(BaseModel):
    id: int
    version: int
    is_current: bool
    change_reason: str
    summary: str | None
    created_at: datetime


class CreateVersionRequest(BaseModel):
    """Datos para crear una versión del perfil.

    El motivo es obligatorio: un historial sin razón no permite auditar por qué
    un cumplimiento cambió de resultado entre dos análisis.
    """

    change_reason: str = Field(min_length=1, max_length=2000)
    summary: str | None = Field(default=None, max_length=2000)
    copy_from_current: bool = True


class ExperienceRequest(BaseModel):
    """Contrato o certificado de experiencia.

    Todos los campos son opcionales salvo ninguno: un contrato puede acreditar
    experiencia aunque falten datos, y forzar un valor convertiría «no consta» en
    un dato inventado.
    """

    contract_reference: str | None = Field(default=None, max_length=200)
    entity: str | None = None
    object_description: str | None = None
    specialty: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, max_length=200)
    start_date: date | None = None
    end_date: date | None = None
    amount: Decimal | None = None
    currency: str | None = Field(default=None, max_length=8)
    evidence_document_id: int | None = None
    evidence_locator: str | None = Field(default=None, max_length=300)
    valid_until: date | None = None


class CapabilityRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=120)
    description: str | None = None
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=40)
    evidence_document_id: int | None = None
    evidence_locator: str | None = Field(default=None, max_length=300)
    valid_until: date | None = None


class FinancialRequest(BaseModel):
    """Indicador financiero de un período.

    La fórmula es opcional pero recomendable: sin ella, dos personas obtienen
    valores distintos del mismo estado financiero y ninguna sabe por qué.
    """

    indicator: str = Field(min_length=1, max_length=120)
    period: str = Field(min_length=1, max_length=32)
    value: Decimal | None = None
    unit: str | None = Field(default=None, max_length=40)
    formula: str | None = None
    evidence_document_id: int | None = None
    evidence_locator: str | None = Field(default=None, max_length=300)
    valid_until: date | None = None


class RecordResponse(BaseModel):
    """Dato del perfil recién creado.

    `supports_claim` se devuelve siempre: saber si el dato puede sustentar un
    cumplimiento es más útil que saber solo que se guardó.
    """

    id: int
    supports_claim: bool


class VerifyRequest(BaseModel):
    status: str = Field(pattern="^(pendiente|verificado|rechazado)$")
