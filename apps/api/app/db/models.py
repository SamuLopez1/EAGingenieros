"""Modelo de datos del MVP.

Alcance de esta entrega: oportunidades y ejecuciones de sincronización. No
incluye documentos, análisis ni informes, que corresponden a issues posteriores.

Decisiones relevantes:

- La clave natural de una oportunidad es ``(source_dataset, source_id)``. Es la
  base de la sincronización idempotente: la misma fila oficial, vista dos veces,
  actualiza el mismo registro en lugar de crear otro.
- Se conserva la carga original de la fuente en ``raw_payload``. La normalización
  puede corregirse más adelante sin volver a consultar SECOP, y una discrepancia
  se puede auditar contra el dato tal como llegó.
- Los campos desconocidos son ``NULL``, nunca cero ni cadena vacía. En este
  dominio "no sé" y "cero" son cosas distintas: confundirlos produce
  comparaciones incorrectas.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.secop.client import RECEPTION_FIELD, parse_timestamp


class Base(DeclarativeBase):
    """Base declarativa de la aplicación."""


def utcnow() -> datetime:
    return datetime.now(UTC)


class Opportunity(Base):
    """Una oportunidad oficial, con su trazabilidad de origen.

    ``first_seen_at`` y ``last_synced_at`` son distintos a propósito: el primero
    registra cuándo apareció por primera vez en nuestro catálogo y no se
    modifica; el segundo, cuándo se confirmó por última vez contra la fuente.
    """

    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("source_dataset", "source_id", name="uq_opportunity_source"),
        Index("ix_opportunity_published_at", "published_at"),
        Index("ix_opportunity_entity", "entity"),
        Index("ix_opportunity_status", "status"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    source_dataset: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)

    reference: Mapped[str | None] = mapped_column(String(256))
    title: Mapped[str | None] = mapped_column(Text)
    entity: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(64))
    modality: Mapped[str | None] = mapped_column(String(128))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    official_url: Mapped[str | None] = mapped_column(Text)

    # Carga original de la fuente. Permite auditar y renormalizar sin red.
    raw_payload: Mapped[dict[str, object]] = mapped_column(
        JSONB().with_variant(JSON, "sqlite"), nullable=False
    )

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    @property
    def reception_at(self) -> datetime | None:
        return parse_timestamp(self.raw_payload.get(RECEPTION_FIELD))

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Opportunity {self.source_dataset}:{self.source_id}>"


class SyncRun(Base):
    """Una ejecución de sincronización, con su resultado observable.

    Existe para que un fallo parcial quede visible y sea reanudable en lugar de
    pasar por éxito. ``last_offset`` permite continuar donde se interrumpió.
    """

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_checkpoint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # running | completed | failed | interrupted
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, default="manual")
    dataset: Mapped[str] = mapped_column(String(32), nullable=False)

    records_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    requests_made: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Motivo del fallo, sin datos sensibles: solo tipo y mensaje acotado.
    error_kind: Mapped[str | None] = mapped_column(String(64))
    error_detail: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<SyncRun {self.id} {self.outcome}>"


class SyncCursor(Base):
    """Posición persistida de la sincronización por conjunto de datos.

    Sin esto, una reanudación tendría que empezar desde el principio y
    dependería de que el conjunto no cambie de orden entre ejecuciones.
    """

    __tablename__ = "sync_cursors"

    dataset: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_id: Mapped[int | None] = mapped_column(ForeignKey("sync_runs.id"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=func.now()
    )

    run: Mapped[SyncRun | None] = relationship()
