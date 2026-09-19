"""Perfil empresarial: qué puede acreditar la empresa.

Es la otra mitad de la comparación. El RAG recupera evidencia de los documentos;
este modelo estructura lo que la empresa afirma de sí misma, con su soporte
documental y su vigencia.

Tres decisiones que gobiernan el diseño:

1. **Un dato desconocido no es cero.** ``None`` significa «no consta» y ``0``
   significa «vale cero». En una comparación de requisitos la diferencia decide
   el veredicto: confundirlos marcaría incumplimiento donde solo falta
   información.

2. **Un valor sin evidencia no sustenta un cumplimiento.** La comparación exige
   `evidence_document_id` y estado `verificado`. Un dato sin soporte puede
   mostrarse, pero no puede sostener un `cumple` (HU-22).

3. **El perfil se versiona, no se sobrescribe.** Un análisis aprobado debe seguir
   apuntando a la versión del perfil que usó (HU-24 y decisión A4). Cambiar un
   patrimonio de 2024 no debe alterar retroactivamente un informe ya emitido.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base, BigIntColumn, JsonColumn, utcnow


class ProfileVersion(Base):
    """Una versión del perfil empresarial.

    Cada edición crea una versión nueva y deja la anterior como no vigente. Los
    análisis guardan la versión que compararon, de modo que un informe ya
    aprobado sigue siendo reproducible aunque el perfil haya cambiado después.
    """

    __tablename__ = "profile_versions"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Motivo del cambio, obligatorio: un historial sin razón no permite auditar
    # por qué un cumplimiento cambió de resultado.
    change_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    # Resumen legible para listar versiones sin cargar todo el perfil.
    summary: Mapped[str | None] = mapped_column(Text)

    experience: Mapped[list[ExperienceRecord]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    personnel: Mapped[list[PersonnelRecord]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    capabilities: Mapped[list[CapabilityRecord]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    financials: Mapped[list[FinancialRecord]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    legal: Mapped[list[LegalRecord]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<ProfileVersion {self.id} v{self.version}>"


class EvidenceMixin:
    """Campos comunes a todo dato del perfil que puede sustentar un cumplimiento.

    Se repiten en cada tabla en lugar de usar herencia de SQLAlchemy: las tablas
    son independientes y una jerarquía complicaría las consultas sin aportar
    nada. Lo que sí se comparte es el criterio, y vive en `supports_claim`.
    """

    @property
    def is_expired(self) -> bool:
        """Un dato vencido no puede sustentar un cumplimiento vigente."""

        until = getattr(self, "valid_until", None)
        if until is None:
            return False
        today = datetime.now(UTC).date()
        if isinstance(until, datetime):
            until = until.date()
        return until < today

    @property
    def supports_claim(self) -> bool:
        """Indica si este dato puede sostener un `cumple`.

        Exige tres cosas a la vez: soporte documental, verificación humana y
        vigencia. Falta cualquiera de las tres y el dato sirve para orientar,
        pero no para afirmar cumplimiento.
        """

        return (
            getattr(self, "evidence_document_id", None) is not None
            and getattr(self, "verification_status", None) == "verificado"
            and not self.is_expired
        )


class ExperienceRecord(Base, EvidenceMixin):
    """Contrato o certificado de experiencia.

    ``amount`` y ``currency`` son opcionales a propósito: un contrato puede
    acreditar experiencia sin que su valor conste, y forzar un cero convertiría
    «no consta» en «vale cero».
    """

    __tablename__ = "profile_experience"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile_versions.id", ondelete="CASCADE"), nullable=False
    )

    contract_reference: Mapped[str | None] = mapped_column(String(200))
    entity: Mapped[str | None] = mapped_column(Text)
    object_description: Mapped[str | None] = mapped_column(Text)
    # Especialidad o área: vial, edificaciones, interventoría, consultoría.
    specialty: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(200))

    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    currency: Mapped[str | None] = mapped_column(String(8))

    evidence_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL")
    )
    # Localizador dentro del documento: «pág. 2», «certificado del contrato».
    evidence_locator: Mapped[str | None] = mapped_column(String(300))
    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pendiente"
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)

    profile: Mapped[ProfileVersion] = relationship(back_populates="experience")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<ExperienceRecord {self.id} {self.contract_reference}>"


class PersonnelRecord(Base, EvidenceMixin):
    """Persona del equipo, con sus credenciales.

    Se guarda un identificador interno y no el documento de identidad: el perfil
    no necesita identificar legalmente a la persona para comparar un requisito
    de formación, y almacenar menos datos personales reduce la exposición
    (HU-21).
    """

    __tablename__ = "profile_personnel"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile_versions.id", ondelete="CASCADE"), nullable=False
    )

    internal_id: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(200))
    education_level: Mapped[str | None] = mapped_column(String(120))
    profession: Mapped[str | None] = mapped_column(String(200))
    # Años de experiencia: entero porque es lo que exigen los pliegos.
    experience_years: Mapped[int | None] = mapped_column(Integer)

    certifications: Mapped[list[str]] = mapped_column(JsonColumn, nullable=False, default=list)

    evidence_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL")
    )
    evidence_locator: Mapped[str | None] = mapped_column(String(300))
    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pendiente"
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)

    profile: Mapped[ProfileVersion] = relationship(back_populates="personnel")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<PersonnelRecord {self.id} {self.role}>"


class CapabilityRecord(Base, EvidenceMixin):
    """Equipo, capacidad técnica o disponibilidad acreditada."""

    __tablename__ = "profile_capabilities"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile_versions.id", ondelete="CASCADE"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    # Cantidad con unidad explícita. Un «3» sin unidad no es comparable.
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 2))
    unit: Mapped[str | None] = mapped_column(String(40))

    evidence_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL")
    )
    evidence_locator: Mapped[str | None] = mapped_column(String(300))
    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pendiente"
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)

    profile: Mapped[ProfileVersion] = relationship(back_populates="capabilities")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<CapabilityRecord {self.id} {self.name}>"


class FinancialRecord(Base, EvidenceMixin):
    """Indicador financiero de un período.

    ``formula`` documenta cómo se calculó. Sin ella, dos personas pueden obtener
    valores distintos del mismo estado financiero y ninguna sabría por qué.
    """

    __tablename__ = "profile_financials"
    __table_args__ = (
        # Un mismo indicador no puede repetirse para el mismo período: dos
        # valores distintos del mismo año harían la comparación ambigua.
        UniqueConstraint("profile_id", "indicator", "period", name="uq_financial_period"),
    )

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile_versions.id", ondelete="CASCADE"), nullable=False
    )

    indicator: Mapped[str] = mapped_column(String(120), nullable=False)
    # Período como texto: un pliego puede exigir «2024» o «2024-1».
    period: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    unit: Mapped[str | None] = mapped_column(String(40))
    formula: Mapped[str | None] = mapped_column(Text)

    evidence_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL")
    )
    evidence_locator: Mapped[str | None] = mapped_column(String(300))
    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pendiente"
    )
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)

    profile: Mapped[ProfileVersion] = relationship(back_populates="financials")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<FinancialRecord {self.id} {self.indicator} {self.period}>"


class LegalRecord(Base, EvidenceMixin):
    """Documento legal o habilitante: RUP, cámara de comercio, pólizas."""

    __tablename__ = "profile_legal"

    id: Mapped[int] = mapped_column(BigIntColumn, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(
        ForeignKey("profile_versions.id", ondelete="CASCADE"), nullable=False
    )

    document_type: Mapped[str] = mapped_column(String(120), nullable=False)
    identifier: Mapped[str | None] = mapped_column(String(200))
    issuer: Mapped[str | None] = mapped_column(String(200))
    issued_on: Mapped[date | None] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)

    evidence_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="SET NULL")
    )
    evidence_locator: Mapped[str | None] = mapped_column(String(300))
    verification_status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="pendiente"
    )
    valid_from: Mapped[date | None] = mapped_column(Date)

    profile: Mapped[ProfileVersion] = relationship(back_populates="legal")

    def __repr__(self) -> str:  # pragma: no cover - ayuda de depuración
        return f"<LegalRecord {self.id} {self.document_type}>"
