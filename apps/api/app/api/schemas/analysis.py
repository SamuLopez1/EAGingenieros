"""Contratos HTTP del análisis de requisitos.

La traza (`StepResponse`) se expone a propósito: permite ver por qué nodo pasó el
análisis y qué hizo en cada uno. Sin ella, un resultado de «revisión manual»
sería indistinguible de un fallo.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    opportunity_id: int
    document_ids: list[int] = Field(min_length=1)


class RequirementResponse(BaseModel):
    """Requisito extraído, con su cita y si se pudo verificar.

    `citation_verified` es el campo que decide si el requisito puede sustentar
    algo: una cita que no se encuentra en el documento no es una prueba.
    """

    text: str
    category: str | None
    source_document_id: int | None
    source_locator: str | None
    quote: str | None
    citation_verified: bool
    validation_note: str | None


class MatchResponse(BaseModel):
    """Propuesta de estado para un requisito.

    El análisis propone; nunca aprueba. La confirmación es humana por diseño.
    """

    requirement_index: int
    state: str
    rationale: str | None
    evidence_chunk_ids: list[int]


class StepResponse(BaseModel):
    """Un nodo ejecutado del grafo."""

    node: str
    status: str
    detail: str | None


class AnalysisResponse(BaseModel):
    """Resultado completo del análisis de una oportunidad."""

    opportunity_id: int
    documents_read: int
    chunks_available: int
    requirements: list[RequirementResponse]
    matches: list[MatchResponse]
    steps: list[StepResponse]
    rejected_requirements: int
    awaiting_review: bool
    review_reason: str | None
    error: str | None
