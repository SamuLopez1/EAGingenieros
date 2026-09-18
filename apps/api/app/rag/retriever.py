"""Recuperación de evidencia y respuesta con cita obligatoria.

La regla que gobierna este módulo (decisión B9 del plan):

**El sistema responde solo con fragmentos recuperados de los documentos de la
empresa, y cita documento, página y fragmento textual.** Si ningún fragmento
supera el umbral de relevancia, responde que no hay evidencia en lugar de
completar con conocimiento general.

Por qué esto no es negociable: el producto se usa para decidir si una empresa se
presenta a una licitación pública. Un sistema que completa con conocimiento
plausible cuando no encuentra evidencia produce afirmaciones de capacidad
empresarial que la empresa no tiene. En contratación pública eso no es un error
de interfaz: es una oferta temeraria con consecuencias legales.

Consecuencias de diseño:

- **El umbral se evalúa antes de llamar al modelo.** Si no hay fragmentos
  suficientes, no se gasta una llamada para que el modelo improvise.
- **La respuesta se construye desde los fragmentos**, no se valida después. Es
  más fácil impedir una invención que detectarla.
- **Se distingue "no está en los documentos" de "los documentos no cubren el
  tema"**, porque llevan a acciones distintas: la primera sugiere revisar la
  base de conocimiento, la segunda buscar el documento que falta.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.knowledge_models import KnowledgeChunk, KnowledgeDocument


@dataclass(frozen=True)
class RetrievedChunk:
    """Fragmento recuperado con su origen verificable."""

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

    @property
    def citation(self) -> str:
        """Cita legible para mostrar junto a una afirmación."""

        parts = [self.document_title]
        if self.locator:
            parts.append(self.locator)
        return " · ".join(parts)


@dataclass
class RetrievalResult:
    """Resultado de una recuperación, con su evaluación de suficiencia."""

    chunks: list[RetrievedChunk]
    threshold: float
    question: str
    # Motivo por el que no hay evidencia, cuando aplica. Se distinguen dos
    # casos porque llevan a acciones distintas.
    no_evidence_reason: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        return bool(self.chunks) and self.no_evidence_reason is None

    @property
    def top_score(self) -> float | None:
        return self.chunks[0].score if self.chunks else None


class Embedder(Protocol):
    """Convierte texto en vectores. Se inyecta para poder probar sin red."""

    @property
    def model_id(self) -> str: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class KnowledgeUnavailableError(RuntimeError):
    """No hay índice utilizable o falta configuración."""


class Retriever:
    """Búsqueda por similitud sobre el índice vectorial."""

    def __init__(
        self,
        session: Session,
        *,
        embedder: Embedder,
        threshold: float = 0.35,
        default_limit: int = 6,
        include_expired: bool = False,
    ) -> None:
        self._db = session
        self._embedder = embedder
        self._threshold = threshold
        self._default_limit = default_limit
        # Por defecto se excluye la evidencia vencida: un certificado caducado no
        # debe sustentar un cumplimiento. Se puede incluir para auditoría.
        self._include_expired = include_expired

    def retrieve(
        self,
        question: str,
        *,
        limit: int | None = None,
        categories: list[str] | None = None,
    ) -> RetrievalResult:
        """Recupera los fragmentos más relevantes para una consulta."""

        cleaned = question.strip()
        if not cleaned:
            return RetrievalResult(
                chunks=[], threshold=self._threshold, question=question,
                no_evidence_reason="la consulta está vacía",
            )

        model = self._embedder.model_id
        query_vector = self._embedder.embed([cleaned])[0]

        # El filtro por modelo es imprescindible: comparar vectores generados
        # por modelos distintos produce distancias sin significado y devolvería
        # resultados aparentemente válidos pero arbitrarios.
        distance = KnowledgeChunk.embedding.cosine_distance(query_vector).label("distance")
        statement = (
            select(KnowledgeChunk, KnowledgeDocument, distance)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .where(KnowledgeChunk.embedding_model == model)
            .where(KnowledgeChunk.embedding.is_not(None))
            .where(KnowledgeDocument.is_current.is_(True))
            .where(KnowledgeDocument.index_status == "indexado")
        )
        if categories:
            statement = statement.where(KnowledgeDocument.category.in_(categories))
        statement = statement.order_by(distance).limit(limit or self._default_limit)

        rows = self._db.execute(statement).all()
        if not rows:
            return RetrievalResult(
                chunks=[], threshold=self._threshold, question=cleaned,
                no_evidence_reason=(
                    "no hay documentos indexados con el modelo de representación "
                    "actual; puede requerirse reindexar"
                ),
            )

        retrieved: list[RetrievedChunk] = []
        for chunk, document, dist in rows:
            # La distancia coseno va de 0 (idéntico) a 2 (opuesto). Se convierte
            # a similitud para que el umbral sea legible: 1 es idéntico.
            score = 1.0 - float(dist)
            if score < self._threshold:
                continue
            if document.is_expired and not self._include_expired:
                continue
            retrieved.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    document_title=document.title,
                    category=document.category,
                    content=chunk.content,
                    locator=chunk.locator,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    score=score,
                    is_verified=document.verification_status == "verificado",
                    is_expired=document.is_expired,
                )
            )

        if not retrieved:
            return RetrievalResult(
                chunks=[], threshold=self._threshold, question=cleaned,
                no_evidence_reason=(
                    f"ningún fragmento superó el umbral de relevancia ({self._threshold})"
                ),
            )

        notes = []
        expired = [c for c in retrieved if c.is_expired]
        if expired:
            notes.append(f"{len(expired)} fragmentos provienen de documentos vencidos")
        unverified = [c for c in retrieved if not c.is_verified]
        if unverified:
            notes.append(
                f"{len(unverified)} fragmentos provienen de documentos sin verificar"
            )

        return RetrievalResult(
            chunks=retrieved, threshold=self._threshold, question=cleaned, notes=notes
        )
