"""Contratos HTTP de oportunidades.

Los contratos se declaran aquí, junto a la API, y se publican por OpenAPI para
que el cliente TypeScript se genere desde ellos. No se mantienen tipos
duplicados a mano en la interfaz.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.opportunity_fields import Validity, validity


class OpportunitySummary(BaseModel):
    """Oportunidad tal como aparece en el listado.

    Se omite deliberadamente la carga original de la fuente: el listado no la
    necesita y enviarla multiplicaría el tamaño de la respuesta.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_dataset: str
    source_id: str
    reference: str | None
    title: str | None
    entity: str | None
    department: str | None
    city: str | None
    phase: str | None
    status: str | None = Field(description="Estado oficial del procedimiento en SECOP II")
    modality: str | None
    published_at: datetime | None
    reception_at: datetime | None = Field(
        description="Fecha asignada a la recepción de respuestas en SECOP II"
    )
    last_updated_at: datetime | None
    official_url: str | None
    first_seen_at: datetime
    last_synced_at: datetime = Field(
        description="Última verificación de esta oportunidad contra la fuente"
    )


    @field_validator(
        "published_at", "reception_at", "last_updated_at", "first_seen_at", "last_synced_at"
    )
    @classmethod
    def ensure_utc(cls, value: datetime | None) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None and value.tzinfo is None else value

    @computed_field  # type: ignore[prop-decorator]
    @property
    def validity(self) -> Validity:
        return validity(self.status, self.phase, self.reception_at, datetime.now(UTC))


class OpportunityPage(BaseModel):
    """Página de resultados con los datos necesarios para paginar.

    ``total`` se incluye para que la interfaz pueda mostrar cuántos resultados
    hay sin tener que pedir todas las páginas.
    """

    items: list[OpportunitySummary]
    total: int
    limit: int
    offset: int
    catalog_synced_at: datetime | None = None
    latest_sync_outcome: str | None = None
    latest_sync_finished_at: datetime | None = None
    catalog_stale_after_hours: int = 24

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class SyncRunSummary(BaseModel):
    """Resultado observable de una ejecución de sincronización.

    Expone el resultado y los contadores, nunca el detalle del error tal como
    lo devolvió el proveedor: podría contener la URL consultada.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    window_start: datetime | None
    window_end: datetime | None
    outcome: str
    trigger: str
    dataset: str
    records_seen: int
    records_created: int
    records_updated: int
    records_skipped: int
    requests_made: int
    last_offset: int
    error_kind: str | None


class SyncTriggerResponse(BaseModel):
    """Respuesta al solicitar una sincronización."""

    outcome: str
    run_id: int | None
    records_seen: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_unchanged: int = 0
    requests_made: int = 0
    last_offset: int = 0
    error_kind: str | None = None
    notes: list[str] = Field(default_factory=list)
