"""Contratos HTTP publicados por FastAPI y, posteriormente, OpenAPI."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HealthResponse(BaseModel):
    status: Literal["ok"]
    version: str
    environment: str


class SessionResponse(BaseModel):
    """Sesión resuelta por el servidor; el rol no procede del cliente."""

    subject_id: UUID
    organization_id: UUID
    role: Literal["administrador", "analista"]


class InvitationCreateRequest(BaseModel):
    """Entrada mínima para una invitación creada exclusivamente por un administrador."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def require_basic_email_shape(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.count("@") != 1 or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("email inválido")
        return normalized


class InvitationResponse(BaseModel):
    """No devuelve correo ni claves; el identificador sirve para acciones administrativas."""

    invitation_id: UUID
    status: Literal["sent", "resent", "revoked"]
