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


# --- Base de conocimiento --------------------------------------------------


class KnowledgeDocumentSummary(BaseModel):
    """Documento de la base de conocimiento.

    No expone `storage_path`: es una ruta interna y publicarla revelaría la
    organización del almacenamiento sin aportar nada al usuario.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    category: str
    original_filename: str | None
    mime_type: str | None
    size_bytes: int | None
    verification_status: str
    index_status: str
    index_error: str | None
    version: int
    is_current: bool
    valid_from: datetime | None
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentPage(BaseModel):
    items: list[KnowledgeDocumentSummary]
    total: int
    limit: int
    offset: int


class IngestionResponse(BaseModel):
    """Resultado de subir un documento."""

    document_id: int | None
    status: str
    chunks_indexed: int = 0
    reused_existing: bool = False
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.status in ("indexado", "reutilizado")


class RetrievedChunkResponse(BaseModel):
    """Fragmento recuperado, con su origen verificable."""

    chunk_id: int
    document_id: int
    document_title: str
    category: str
    content: str
    locator: str | None
    page_number: int | None
    section: str | None
    score: float
    is_verified: bool
    is_expired: bool
    citation: str


class SupportedClaimResponse(BaseModel):
    text: str
    citations: list[str]


class QueryResponse(BaseModel):
    """Respuesta a una consulta sobre la base de conocimiento.

    `has_evidence=False` significa que el sistema declinó responder. Se expone
    explícitamente para que la interfaz no tenga que inferirlo de una lista
    vacía, que podría confundirse con un fallo técnico.
    """

    question: str
    has_evidence: bool
    claims: list[SupportedClaimResponse] = Field(default_factory=list)
    retrieved: list[RetrievedChunkResponse] = Field(default_factory=list)
    rejected_claims: list[str] = Field(default_factory=list)
    no_evidence_reason: str | None = None
    notes: list[str] = Field(default_factory=list)
