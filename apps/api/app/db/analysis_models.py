"""Persistencia del análisis de requisitos.

Sin estas tablas, la épica E7 no se puede cumplir: el análisis se devolvía en la
respuesta HTTP y no quedaba en ninguna parte. Corregir un requisito (HU-32),
aprobar una versión concreta (HU-33) o invalidar una aprobación cuando cambian
las entradas (HU-34) exigen que el análisis exista como registro consultable y
versionado, no como un objeto que se pierde al cerrar la petición.

Decisiones que se reflejan en el esquema
----------------------------------------

**La salida automática nunca se sobrescribe (HU-32).** La corrección de una
persona se guarda en ``analysis_reviews`` como un registro aparte, con su autor,
fecha y motivo. Si se modificara la fila original, sería imposible medir en qué
discrepa el sistema de la persona, que es justamente lo que el piloto necesita
para decidir si la herramienta sirve (HU-42).

**Aprobar es congelar, no marcar (A4, HU-33).** La aprobación guarda la firma de
lo aprobado: qué documentos y con qué versión, qué versión del perfil y qué
decisiones. La aprobación está vigente mientras esa firma siga coincidiendo con
la realidad. Un cambio posterior no «invalida» nada retroactivamente: hace que
la firma deje de coincidir, y el informe se bloquea solo (HU-34).

**El estado del grafo se puede reanudar (B7).** ``graph_thread_id`` enlaza la
ejecución con el checkpoint de LangGraph en PostgreSQL, de modo que la revisión
humana puede ocurrir horas después sin perder el trabajo hecho.

**La configuración de IA queda versionada (HU-27).** ``model_id``,
``prompt_version`` y ``schema_version`` se guardan con cada ejecución: un
resultado solo es interpretable si se sabe con qué se produjo.
"""

from __future__ import annotations

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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base, BigIntColumn, JsonColumn, utcnow

# --- Vocabularios cerrados -------------------------------------------------
# Se declaran aquí y no como ENUM de PostgreSQL para que añadir un valor sea un
# cambio de código y no una migración de tipo, que en producción es una
# operación con bloqueo.

RUN_STATUSES = ("en_curso", "completado", "fallido", "esperando_revision", "aprobado")

# Los cuatro estados del producto. No hay más: un quinto valor rompería la
# promesa de que toda afirmación cae en una categoría auditable (HU-31).
COMPARISON_STATES = ("cumple", "cumple_parcialmente", "no_cumple", "revision_manual")

# Quién produjo una decisión. Distinguirlo es lo que permite medir discrepancias
# entre el sistema y la persona (HU-32, HU-42).
DECIDED_BY = ("regla", "recuperacion", "humano")


class AnalysisRun(Base):
    """Una ejecución del grafo de análisis sobre una oportunidad."""

    __tablename__ = "analysis_runs"
    __table_args__ = (
        Index("ix_analysis_run_opportunity", "opportunity_id"),
        Index("ix_analysis_run_status", "status"),
        UniqueConstraint("graph_thread_id", name="uq_analysis_run_thread"),
    )

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    started_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(String(24), nullable=False, default="en_curso")
    error: Mapped[str | None] = mapped_column(Text)
    review_reason: Mapped[str | None] = mapped_column(Text)

    # Contadores del recorrido. Se copian del estado del grafo al terminar para
    # poder consultar la ejecución sin deserializar el checkpoint.
    documents_read: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunks_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requirements_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requirements_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # --- Configuración de IA con la que se produjo (HU-27) ---
    # Un resultado es interpretable solo si se sabe con qué modelo, con qué
    # prompt y con qué esquema se generó. Sin esto, comparar dos ejecuciones no
    # significa nada.
    model_id: Mapped[str | None] = mapped_column(String(120))
    prompt_version: Mapped[str | None] = mapped_column(String(40))
    schema_version: Mapped[str | None] = mapped_column(String(40))

    # Identificador del hilo del checkpointer de LangGraph. Es lo que permite
    # reanudar tras una interrupción para revisión humana (B7).
    graph_thread_id: Mapped[str] = mapped_column(String(120), nullable=False)

    steps: Mapped[list[dict[str, object]]] = mapped_column(
        JsonColumn, nullable=False, default=list
    )

    requirements: Mapped[list[AnalysisRequirement]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AnalysisRequirement.position",
    )
    approval: Mapped[AnalysisApproval | None] = relationship(
        back_populates="run", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AnalysisRun {self.id} op={self.opportunity_id} {self.status}>"


class AnalysisRequirement(Base):
    """Un requisito extraído, con la evidencia de dónde salió.

    ``citation_verified`` es el campo que decide si el requisito puede sustentar
    algo. Un requisito cuya cita no se encontró en el documento se conserva y se
    muestra —puede ser un fallo de OCR— pero nunca sostiene un cumplimiento.
    """

    __tablename__ = "analysis_requirements"
    __table_args__ = (Index("ix_analysis_requirement_run", "run_id"),)

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False
    )
    # Posición dentro de la ejecución. Es la referencia estable que usan las
    # correcciones humanas, porque el identificador puede cambiar entre
    # ejecuciones del mismo expediente.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(String(40))

    source_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL")
    )
    source_locator: Mapped[str | None] = mapped_column(String(300))
    quote: Mapped[str | None] = mapped_column(Text)

    citation_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_note: Mapped[str | None] = mapped_column(Text)

    # Confianza declarada por el extractor. Nulo cuando el extractor no la
    # produce: inventar un valor por defecto convertiría una ausencia en un dato.
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))

    run: Mapped[AnalysisRun] = relationship(back_populates="requirements")
    match: Mapped[AnalysisMatch | None] = relationship(
        back_populates="requirement", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AnalysisRequirement {self.id} run={self.run_id}>"


class AnalysisMatch(Base):
    """Estado propuesto para un requisito, con el motivo y la regla aplicada.

    HU-29 exige que cada cálculo conserve «entradas, regla, resultado y motivo».
    Los cuatro están aquí: ``inputs`` es lo que se comparó, ``rule`` la regla que
    decidió, ``state`` el resultado y ``rationale`` el motivo en lenguaje legible.
    """

    __tablename__ = "analysis_matches"
    __table_args__ = (Index("ix_analysis_match_requirement", "requirement_id"),)

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_requirements.id", ondelete="CASCADE"), nullable=False
    )

    state: Mapped[str] = mapped_column(String(24), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)

    # Qué produjo la decisión: una regla determinista, recuperación semántica o
    # una persona. Sin esta distinción no se puede medir si el sistema acierta.
    decided_by: Mapped[str] = mapped_column(String(16), nullable=False, default="recuperacion")
    # Nombre de la regla aplicada, cuando la decisión es determinista. Es lo que
    # hace reproducible el resultado: la misma entrada con la misma regla da lo
    # mismo, y se puede volver a comprobar.
    rule: Mapped[str | None] = mapped_column(String(80))
    inputs: Mapped[dict[str, object]] = mapped_column(JsonColumn, nullable=False, default=dict)

    evidence_chunk_ids: Mapped[list[int]] = mapped_column(
        JsonColumn, nullable=False, default=list
    )

    requirement: Mapped[AnalysisRequirement] = relationship(back_populates="match")
    reviews: Mapped[list[AnalysisReview]] = relationship(
        back_populates="match", cascade="all, delete-orphan", order_by="AnalysisReview.id"
    )

    @property
    def effective_state(self) -> str:
        """El estado que cuenta: la última corrección humana, o el propuesto.

        La fila original nunca se modifica (HU-32), así que el estado vigente se
        deriva. Guardarlo además en una columna crearía dos verdades que podrían
        divergir.
        """

        if self.reviews:
            return self.reviews[-1].new_state
        return self.state

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AnalysisMatch req={self.requirement_id} {self.state}>"


class AnalysisReview(Base):
    """Corrección humana de un estado propuesto (HU-32).

    Se guarda como registro nuevo y no como modificación del anterior: la salida
    automática inicial se conserva para poder medir en qué discrepa el sistema de
    la persona. Sin eso, el piloto no podría responder si la herramienta acierta.
    """

    __tablename__ = "analysis_reviews"
    __table_args__ = (Index("ix_analysis_review_match", "match_id"),)

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_matches.id", ondelete="CASCADE"), nullable=False
    )
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    previous_state: Mapped[str] = mapped_column(String(24), nullable=False)
    new_state: Mapped[str] = mapped_column(String(24), nullable=False)

    # El motivo es obligatorio: una corrección sin justificación no es auditable
    # y la HU-32 lo exige explícitamente.
    reason: Mapped[str] = mapped_column(Text, nullable=False)

    # Evidencia alternativa que aporta la persona, si la hay.
    evidence_chunk_ids: Mapped[list[int]] = mapped_column(
        JsonColumn, nullable=False, default=list
    )
    observation: Mapped[str | None] = mapped_column(Text)

    match: Mapped[AnalysisMatch] = relationship(back_populates="reviews")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AnalysisReview {self.id} {self.previous_state}->{self.new_state}>"


class AnalysisApproval(Base):
    """Aprobación humana de una ejecución concreta (HU-33, decisión A4).

    Aprobar **congela**: se guarda la firma de lo que se aprobó —documentos con su
    versión, versión del perfil y decisiones— y la aprobación está vigente
    mientras esa firma siga coincidiendo con la realidad.

    Un cambio posterior no invalida nada retroactivamente (HU-34 se cumple
    congelando, no invalidando): simplemente la firma deja de coincidir y el
    informe se bloquea. Es más robusto que intentar perseguir qué cambió, porque
    no depende de que el sistema detecte todos los cambios posibles.
    """

    __tablename__ = "analysis_approvals"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    # Firma de lo aprobado. Es lo que permite comprobar vigencia sin guardar una
    # copia completa del expediente.
    snapshot_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    # Detalle legible de la firma, para poder explicar al analista qué cambió.
    snapshot: Mapped[dict[str, object]] = mapped_column(JsonColumn, nullable=False, default=dict)

    # Versión del perfil empresarial comparada. La firma ya la incluye, pero se
    # guarda aparte porque es el dato que el informe debe citar.
    profile_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("profile_versions.id", ondelete="SET NULL")
    )

    # Aprobar no equivale a postular ni a decidir participar. Se deja constancia
    # explícita para que nadie lea esta tabla como una decisión de negocio.
    note: Mapped[str | None] = mapped_column(Text)

    run: Mapped[AnalysisRun] = relationship(back_populates="approval")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<AnalysisApproval run={self.run_id}>"
