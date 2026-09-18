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
from sqlalchemy.types import JSON, TypeEngine

# JSONB en PostgreSQL —con índice y consultas por contenido— y JSON en otros
# motores. Sin esta variante, las pruebas no pueden usar SQLite en memoria y
# habría que levantar un PostgreSQL solo para probar la lógica de negocio.
JsonColumn = JSON().with_variant(JSONB(), "postgresql")

# BIGINT en PostgreSQL e INTEGER en SQLite. SQLite solo autoincrementa una
# columna declarada exactamente `INTEGER PRIMARY KEY`; con BIGINT la clave
# queda nula y toda inserción falla. Esta variante permite probar la lógica de
# negocio en memoria sin renunciar a BIGINT donde importa.
BigIntColumn: TypeEngine[int] = BigInteger().with_variant(Integer(), "sqlite")


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

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
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
    raw_payload: Mapped[dict[str, object]] = mapped_column(JsonColumn, nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Opportunity {self.source_dataset}:{self.source_id}>"


class SyncRun(Base):
    """Una ejecución de sincronización, con su resultado observable.

    Existe para que un fallo parcial quede visible y sea reanudable en lugar de
    pasar por éxito. ``last_offset`` permite continuar donde se interrumpió.
    """

    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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


class User(Base):
    """Persona con acceso al sistema.

    No hay registro público: las cuentas se crean por invitación de un
    administrador. El correo se normaliza a minúsculas antes de guardarlo, de
    modo que la unicidad no dependa de cómo lo escriba el usuario.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Cambiar la contraseña o desactivar la cuenta invalida los access tokens
    # ya emitidos sin necesidad de mantener una lista de revocación: basta con
    # comparar esta marca con el `iat` del token.
    password_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<User {self.id} {self.role}>"


class Session(Base):
    """Sesión renovable de un usuario.

    El refresh token se guarda hasheado, nunca en claro: un volcado de la base
    no debe permitir suplantar sesiones activas.

    ``family_id`` agrupa todos los tokens derivados de un mismo inicio de
    sesión. Si un refresh token ya rotado se presenta de nuevo, se revoca la
    familia completa, porque eso indica que alguien copió el token.
    """

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    family_id: Mapped[str] = mapped_column(String(64), nullable=False)
    refresh_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Marca el momento en que este token se usó para rotar. Un token con
    # `used_at` que vuelve a presentarse es una señal de robo.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user_agent: Mapped[str | None] = mapped_column(String(300))
    ip_address: Mapped[str | None] = mapped_column(String(64))

    user: Mapped[User] = relationship()

    @property
    def is_usable(self) -> bool:
        return self.revoked_at is None and self.used_at is None

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<Session {self.id} user={self.user_id}>"


class AuditEvent(Base):
    """Registro de acciones relevantes para auditoría.

    Nunca guarda contraseñas, tokens ni cabeceras de autorización. ``metadata``
    solo admite datos no sensibles, y esa restricción se aplica en el código que
    escribe, no confiando en quien lo llame.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    metadata_json: Mapped[dict[str, object]] = mapped_column(
        JsonColumn, nullable=False, default=dict
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AuditEvent {self.action} {self.outcome}>"
