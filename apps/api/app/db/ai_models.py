"""Registro de consumo de IA y caché de llamadas (HU-27).

Por qué un registro y no solo un contador en memoria
----------------------------------------------------

HU-27 exige «limitar tokens, lotes, concurrencia, reintentos y llamadas repetidas
por hash/versión». Un tope mensual solo se puede aplicar si el gasto acumulado es
consultable y sobrevive a los reinicios: un contador en memoria se pondría a cero
con cada despliegue, y el tope dejaría de existir justo cuando más importa.

Adaptado del patrón `consumo_negocio` del proyecto `agentes-asobares`, que
agrega el consumo por día y por inquilino con los tokens como principal coste
variable.

Dos tablas, dos propósitos distintos
------------------------------------

**`ai_usage`** es el libro de consumo: una fila por llamada, con su modelo, su
versión de prompt y su coste estimado. Es lo que permite responder «¿cuánto se
gastó este mes?» y «¿qué modelo produjo este resultado?».

**`ai_cache`** es la memoria de resultados: la misma entrada con el mismo modelo
y la misma versión de prompt no se vuelve a pedir. Sin esto, reanalizar el mismo
expediente paga dos veces por el mismo trabajo, que es el gasto más fácil de
evitar y el que más se repite en un flujo con revisiones.

Sobre el coste: se guarda una **estimación** a partir de una tabla de precios,
no una cifra contable. Un modelo sin tarifa conocida deja el coste en NULL, nunca
en cero: cero afirmaría que la llamada fue gratis.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base, BigIntColumn, JsonColumn, utcnow

# Estados posibles de una llamada. `omitida` es un resultado legítimo y no un
# error: significa que el tope de gasto impidió la llamada, y distinguirlo de
# `fallida` evita que un límite presupuestario parezca una avería.
AI_CALL_STATUSES = ("completada", "fallida", "omitida_por_presupuesto", "servida_de_cache")


def content_hash(*parts: str) -> str:
    """Hash estable de los componentes de una llamada.

    Se incluye el modelo y la versión de prompt además del contenido: el mismo
    texto con otro modelo o otro prompt **no** es la misma llamada, y servirlo
    desde caché devolvería un resultado que no corresponde a la configuración
    vigente.
    """

    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8", errors="replace"))
        digest.update(b"\x1f")  # separador que no aparece en texto normal
    return digest.hexdigest()


class AiUsage(Base):
    """Una llamada a un proveedor de IA, con su coste estimado."""

    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_created_at", "created_at"),
        Index("ix_ai_usage_run", "analysis_run_id"),
        Index("ix_ai_usage_status", "status"),
    )

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    # Ejecución a la que pertenece la llamada, cuando la hay. Nulo para llamadas
    # suelas —una consulta a la base de conocimiento, por ejemplo—.
    analysis_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="SET NULL")
    )
    # Nodo del grafo que hizo la llamada. Permite saber dónde se va el
    # presupuesto, que es la pregunta que precede a cualquier optimización.
    node: Mapped[str | None] = mapped_column(String(64))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    # Versión del prompt y del esquema con los que se hizo la llamada. Sin esto,
    # comparar dos ejecuciones no significa nada (HU-27).
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    schema_version: Mapped[str | None] = mapped_column(String(40))

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="completada")

    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # False cuando el proveedor no informó del consumo. Distinguirlo de «cero
    # tokens» importa: uno es un dato ausente y el otro un hecho.
    usage_reported: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Coste estimado en dólares. NULL cuando el modelo no tiene tarifa conocida:
    # no es gratis, es desconocido.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))

    cache_key: Mapped[str | None] = mapped_column(String(64))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_kind: Mapped[str | None] = mapped_column(String(64))

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AiUsage {self.id} {self.model} {self.status}>"


class AiCache(Base):
    """Resultado de una llamada, reutilizable por su hash.

    La clave incluye modelo y versión de prompt además del contenido: cambiar de
    modelo invalida la caché por construcción, sin necesidad de acordarse de
    purgarla.
    """

    __tablename__ = "ai_cache"
    __table_args__ = (
        UniqueConstraint(
            "cache_key", "model", "prompt_version", name="uq_ai_cache_entry"
        ),
        Index("ix_ai_cache_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[str | None] = mapped_column(String(40))

    # Respuesta estructurada ya validada. Se guarda el objeto, no el texto
    # crudo: una respuesta que no pasó la validación de esquema no debe poder
    # reutilizarse como si la hubiera pasado.
    payload: Mapped[dict[str, object]] = mapped_column(JsonColumn, nullable=False)
    raw_text: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AiCache {self.id} {self.model} hits={self.hits}>"
