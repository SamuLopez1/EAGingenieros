"""Contratos HTTP de oportunidades.

Los contratos se declaran aquí, junto a la API, y se publican por OpenAPI para
que el cliente TypeScript se genere desde ellos. No se mantienen tipos
duplicados a mano en la interfaz.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    status: str | None
    modality: str | None
    published_at: datetime | None
    last_updated_at: datetime | None
    official_url: str | None
    first_seen_at: datetime
    last_synced_at: datetime


class OpportunityPage(BaseModel):
    """Página de resultados con los datos necesarios para paginar.

    ``total`` se incluye para que la interfaz pueda mostrar cuántos resultados
    hay sin tener que pedir todas las páginas.
    """

    items: list[OpportunitySummary]
    total: int
    limit: int
    offset: int

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
