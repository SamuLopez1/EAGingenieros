"""Contrato del perfil maestro con revisión explícita y valores desconocidos."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal[
    "experiencia", "capacidad", "contrato", "certificado", "personal", "equipo",
    "financiero", "legal", "disponibilidad",
]
Label = Annotated[str, Field(min_length=1, max_length=160)]


class ProfileModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EvidenceReference(ProfileModel):
    document_id: UUID
    locator: str = Field(min_length=1, max_length=240)


class Entry(ProfileModel):
    category: Category
    title: Label
    description: str = Field(default="", max_length=1500)
    service_line: Label | None = None
    role: Label | None = None
    dedication_percent: Annotated[Decimal, Field(ge=0, le=100, decimal_places=2)] | None = None
    amount: Annotated[Decimal, Field(max_digits=14, decimal_places=4)] | None = None
    unit: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    status: Literal["pendiente", "verificado"] = "pendiente"
    evidence: list[EvidenceReference] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def check_validity(self) -> Self:
        if self.starts_on and self.ends_on and self.starts_on > self.ends_on:
            raise ValueError("El fin debe ser igual o posterior al inicio.")
        if self.amount is not None and not self.unit:
            raise ValueError("Indica la unidad del valor registrado.")
        if self.status == "verificado" and not self.evidence:
            raise ValueError("La verificación requiere documento y localizador.")
        if self.category == "disponibilidad":
            if not self.role:
                raise ValueError("Indica el cargo de la disponibilidad.")
            if self.status == "verificado" and (
                self.dedication_percent is None or self.starts_on is None or self.ends_on is None
            ):
                raise ValueError("Verificar disponibilidad requiere dedicación y periodo.")
        elif self.dedication_percent is not None:
            raise ValueError("Registra la dedicación en disponibilidad.")
        return self


class ProfileWrite(ProfileModel):
    base_version: int = Field(ge=0, le=2_147_483_646)
    entries: list[Entry] = Field(max_length=150)


class VersionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version: int
    author_id: UUID
    created_at: datetime


class ProfileView(BaseModel):
    version: int
    author_id: UUID | None
    created_at: datetime | None
    availability_status: Literal["pendiente", "verificado"]
    entries: list[Entry]


class EvidenceView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    sha256: str
