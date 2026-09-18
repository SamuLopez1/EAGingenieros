"""Modelo de la base de conocimiento y del índice vectorial.

Separación clave respecto al expediente de una oportunidad:

- **Documento de conocimiento** (`KnowledgeDocument`): material permanente de la
  empresa —certificados, contratos, hojas de vida—. Se reutiliza en todos los
  análisis y tiene su propia política de retención.
- **Documento de oportunidad**: material temporal de un proceso concreto, que se
  purga a los 30 días.

Mezclarlos haría que la purga borrara evidencia empresarial que debe durar, o
que un certificado vencido siguiera sustentando cumplimientos indefinidamente.

Sobre el índice vectorial:

- Cada fragmento guarda el **modelo que lo generó**. Mezclar vectores de modelos
  distintos en una misma consulta devuelve resultados sin sentido y sin error
  visible: la distancia entre espacios vectoriales diferentes no significa nada.
- La tabla es única para todos los fragmentos, con el modelo como columna, y la
  búsqueda filtra por modelo. Así reindexar con otro modelo es una migración de
  datos, no un cambio de esquema.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base, BigIntColumn, utcnow

# Dimensión de los vectores. Debe coincidir con la del modelo configurado; si
# cambia, se exige reindexar (ver `EmbeddingModel`).
EMBEDDING_DIMENSIONS = 1024


class KnowledgeDocument(Base):
    """Documento aportado por la empresa para la base de conocimiento.

    ``content_hash`` detecta que un archivo se volvió a subir sin cambios: en
    ese caso no se reindexa, porque el índice ya refleja su contenido y
    reindexar consumiría cuota de embeddings sin aportar nada.
    """

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    # Categoría del material: experiencia, personal, financiero, legal, otro.
    category: Mapped[str] = mapped_column(String(48), nullable=False, default="no_clasificado")
    original_filename: Mapped[str | None] = mapped_column(String(300))
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    # Estado de verificación humana: un documento sin verificar puede sustentar
    # un borrador, pero no un cumple definitivo.
    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pendiente"
    )
    # Vigencia. Un documento vencido no debe sustentar un cumple.
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Indexación: "pendiente" | "indexado" | "fallido"
    index_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pendiente")
    index_error: Mapped[str | None] = mapped_column(Text)

    # Versión lógica: reemplazar un documento crea una versión nueva y deja la
    # anterior como reemplazada, para que los análisis ya aprobados sigan
    # apuntando a la evidencia que usaron.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    replaced_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL")
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=func.now()
    )

    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    @property
    def is_expired(self) -> bool:
        """Un documento sin fecha de vigencia no se considera vencido."""

        if self.valid_until is None:
            return False
        expires = self.valid_until
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        return expires < datetime.now(UTC)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<KnowledgeDocument {self.id} {self.category} v{self.version}>"


class KnowledgeChunk(Base):
    """Fragmento recuperable de un documento.

    ``locator`` es la referencia verificable —página, sección o celda— que
    permite al analista comprobar el fragmento contra el original. Un fragmento
    sin localizador resoluble es una afirmación que no se puede auditar.
    """

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "ordinal", name="uq_chunk_document_ordinal"),
        # Índice para la búsqueda por similitud. Se declara con la métrica de
        # distancia explícita porque el operador de consulta debe coincidir con
        # el de construcción del índice, o el planificador lo ignora.
        Index(
            "ix_chunk_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Localizador legible: "pág. 12", "§4.2", "hoja «Datos», celda B7".
    locator: Mapped[str | None] = mapped_column(String(200))
    page_number: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(300))
    token_estimate: Mapped[int | None] = mapped_column(Integer)

    # El modelo se guarda por fragmento: la búsqueda filtra por él para no
    # comparar vectores de espacios distintos.
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    document: Mapped[KnowledgeDocument] = relationship(back_populates="chunks")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<KnowledgeChunk {self.id} doc={self.document_id} #{self.ordinal}>"


class RagQueryLog(Base):
    """Registro de consultas al recuperador.

    Existe por dos motivos: controlar el coste (HU-57) y poder auditar qué
    fragmentos sustentaron una afirmación (HU-56). No guarda la respuesta
    completa del modelo, solo las referencias.
    """

    __tablename__ = "rag_query_log"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    chunks_retrieved: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    had_evidence: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    top_score: Mapped[float | None] = mapped_column()
    # Tokens y coste estimado, para el tope mensual.
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[float | None] = mapped_column()

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<RagQueryLog {self.id} evidence={self.had_evidence}>"
