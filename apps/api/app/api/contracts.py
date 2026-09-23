"""Contratos HTTP de oportunidades.

Los contratos se declaran aquí, junto a la API, y se publican por OpenAPI para
que el cliente TypeScript se genere desde ellos. No se mantienen tipos
duplicados a mano en la interfaz.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.secop.sources import get_source


def _as_float(value: Any) -> float | None:
    """Decimal de la base a número de la respuesta.

    Se transporta como número y no como cadena porque el cliente lo formatea;
    el rango de una cuantía en pesos colombianos cabe de sobra en el entero
    exacto de un float de doble precisión, así que no se pierde un peso.
    """

    return None if value is None else float(value)


class OpportunitySummary(BaseModel):
    """Oportunidad tal como aparece en el listado.

    Se omite deliberadamente la carga original de la fuente: el listado no la
    necesita y enviarla multiplicaría el tamaño de la respuesta.

    La procedencia viaja en cada fila, no solo en un encabezado: al mezclar dos
    plataformas en una misma tabla, la única forma de que el analista sepa de
    dónde viene una oportunidad es que lo diga la propia fila.
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

    # --- Procedencia ------------------------------------------------------
    platform: str = "SECOP_II"
    platform_label: str = ""
    entity_nit: str | None = None

    # --- Valor económico --------------------------------------------------
    # `amount_label` acompaña siempre al número porque `precio_base` (SECOP II)
    # y `cuantia_proceso` (SECOP I) NO miden lo mismo. Mostrar ambos bajo la
    # etiqueta «valor» afirmaría una equivalencia que no existe.
    amount: float | None = None
    amount_label: str = ""

    # --- Posible duplicado entre fuentes ----------------------------------
    # Señal, nunca fusión. El sistema no colapsa dos filas por su cuenta: la
    # medición no respalda ninguna clave que garantice que son el mismo
    # proceso, así que la decisión queda en manos del analista.
    group_key: str | None = None
    possible_duplicate: bool = False
    duplicate_platforms: list[str] = Field(default_factory=list)

    @classmethod
    def from_opportunity(
        cls,
        item: Any,
        *,
        duplicate_platforms: set[str] | None = None,
    ) -> OpportunitySummary:
        """Construye la respuesta enriqueciendo con la etiqueta de su fuente."""

        platforms = duplicate_platforms or set()
        source = get_source(item.source_dataset)
        # Más de una plataforma en el mismo grupo es lo que constituye la
        # señal. Una sola plataforma repetida no se anuncia como duplicado, y
        # en ese caso la lista va vacía: el nombre del campo promete las
        # plataformas implicadas en la duplicación, y con una sola no hay
        # ninguna. Devolver `["SECOP_II"]` haría que quien lo lea creyera que
        # existe una segunda fila en otra plataforma.
        is_duplicate = len(platforms) > 1
        return cls(
            id=item.id,
            source_dataset=item.source_dataset,
            source_id=item.source_id,
            reference=item.reference,
            title=item.title,
            entity=item.entity,
            status=item.status,
            modality=item.modality,
            published_at=item.published_at,
            last_updated_at=item.last_updated_at,
            official_url=item.official_url,
            first_seen_at=item.first_seen_at,
            last_synced_at=item.last_synced_at,
            platform=item.platform,
            platform_label=source.short_label,
            entity_nit=item.entity_nit,
            amount=_as_float(item.amount),
            amount_label=source.amount_label,
            group_key=item.group_key,
            possible_duplicate=is_duplicate,
            duplicate_platforms=sorted(platforms) if is_duplicate else [],
        )


class SourceCoverage(BaseModel):
    """Lo que el sistema declara sobre una fuente.

    Existe para que la interfaz pueda decir qué está sincronizado de verdad en
    lugar de dejar creer que el listado cubre todo el mercado público.
    """

    dataset: str
    platform: str
    label: str
    short_label: str
    coverage: str
    note: str
    opportunity_count: int = 0
    amount_label: str = ""


class SourceCoverageResponse(BaseModel):
    sources: list[SourceCoverage]


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
