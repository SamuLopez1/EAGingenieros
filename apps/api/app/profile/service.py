"""Servicio del perfil empresarial.

Reglas que aplica:

1. **Editar crea una versión nueva.** Nunca se sobrescribe: un análisis aprobado
   debe seguir apuntando a la versión del perfil que usó. Sin esto, cambiar el
   patrimonio de un año alteraría retroactivamente un informe ya emitido.
2. **Solo una versión vigente.** La anterior se marca como no vigente en la
   misma transacción, para que no haya un instante con dos vigentes.
3. **El resumen de preparación es explícito.** Saber cuántos datos sustentan un
   cumplimiento y cuántos no es lo que permite decidir si el perfil está listo
   para comparar. Un perfil a medias produce comparaciones engañosas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.profile_models import (
    CapabilityRecord,
    ExperienceRecord,
    FinancialRecord,
    LegalRecord,
    PersonnelRecord,
    ProfileVersion,
)


class ProfileError(RuntimeError):
    """Operación no válida sobre el perfil."""


@dataclass
class VerifiableRecord(Protocol):
    """Contrato mínimo de un registro del perfil que admite verificación.

    Los cinco tipos de registro comparten `verification_status` sin heredar de
    una clase común, así que el contrato se declara aquí en lugar de tipar el
    parámetro como `object`, que obligaría a un `cast` en cada llamada.
    """

    verification_status: str


@dataclass
class SectionReadiness:
    """Preparación de una sección del perfil."""

    name: str
    total: int
    verified: int
    with_evidence: int
    expired: int

    @property
    def supports_claims(self) -> int:
        """Datos que pueden sostener un cumplimiento a la vez.

        Es la intersección de las tres condiciones, no la suma: un dato vencido
        con evidencia sigue sin servir.
        """

        return self.verified  # se recalcula en `readiness` con la intersección real

    @property
    def is_empty(self) -> bool:
        return self.total == 0


@dataclass
class ProfileReadiness:
    """Resumen de si el perfil puede usarse para comparar."""

    version_id: int | None
    version: int | None
    sections: list[SectionReadiness] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def total_records(self) -> int:
        return sum(s.total for s in self.sections)

    @property
    def usable_records(self) -> int:
        return sum(s.supports_claims for s in self.sections)

    @property
    def has_any_data(self) -> bool:
        return self.total_records > 0

    @property
    def is_ready(self) -> bool:
        """Un perfil vacío no está listo: comparar contra nada no es útil."""

        return self.usable_records > 0


def _section(name: str, records: list) -> SectionReadiness:  # type: ignore[type-arg]
    """Calcula la preparación de una sección.

    `verified` cuenta los datos que cumplen las tres condiciones —evidencia,
    verificación humana y vigencia—, que es exactamente lo que exige
    `supports_claim`. No se cuenta por separado para no dar dos cifras que
    podrían interpretarse de forma contradictoria.
    """

    return SectionReadiness(
        name=name,
        total=len(records),
        verified=sum(1 for r in records if r.supports_claim),
        with_evidence=sum(1 for r in records if r.evidence_document_id is not None),
        expired=sum(1 for r in records if r.is_expired),
    )


class ProfileService:
    def __init__(self, session: Session) -> None:
        self._db = session

    # --- Consultas ---------------------------------------------------------

    def current(self) -> ProfileVersion | None:
        """Versión vigente del perfil, o None si aún no existe."""

        return self._db.execute(
            select(ProfileVersion)
            .where(ProfileVersion.is_current.is_(True))
            .order_by(ProfileVersion.version.desc())
        ).scalars().first()

    def get_version(self, version_id: int) -> ProfileVersion | None:
        return self._db.get(ProfileVersion, version_id)

    def list_versions(self) -> list[ProfileVersion]:
        return list(
            self._db.execute(
                select(ProfileVersion).order_by(ProfileVersion.version.desc())
            )
            .scalars()
            .all()
        )

    def readiness(self, version: ProfileVersion | None = None) -> ProfileReadiness:
        """Resumen de preparación del perfil."""

        profile = version or self.current()
        if profile is None:
            return ProfileReadiness(
                version_id=None,
                version=None,
                notes=["no hay ninguna versión del perfil; cree una para empezar"],
            )

        sections = [
            _section("experiencia", list(profile.experience)),
            _section("personal", list(profile.personnel)),
            _section("capacidades", list(profile.capabilities)),
            _section("financiero", list(profile.financials)),
            _section("legal", list(profile.legal)),
        ]

        notes: list[str] = []
        pending = sum(s.total - s.verified for s in sections)
        if pending:
            notes.append(
                f"{pending} datos no pueden sustentar un cumplimiento: "
                "les falta evidencia, verificación humana o vigencia"
            )
        expired = sum(s.expired for s in sections)
        if expired:
            notes.append(f"{expired} datos están vencidos")
        empty = [s.name for s in sections if s.is_empty]
        if empty:
            notes.append(f"secciones sin datos: {', '.join(empty)}")

        return ProfileReadiness(
            version_id=profile.id,
            version=profile.version,
            sections=sections,
            notes=notes,
        )

    # --- Edición -----------------------------------------------------------

    def _next_version_number(self) -> int:
        last = self._db.execute(
            select(func.max(ProfileVersion.version))
        ).scalar()
        return int(last or 0) + 1

    def create_version(
        self,
        *,
        change_reason: str,
        created_by: int | None = None,
        summary: str | None = None,
        copy_from_current: bool = False,
    ) -> ProfileVersion:
        """Crea una versión nueva del perfil.

        Con `copy_from_current` se parte del perfil vigente. Es lo habitual:
        añadir un certificado no debería obligar a reescribir todo lo anterior.
        """

        reason = change_reason.strip()
        if not reason:
            # Un historial sin motivo no permite auditar por qué cambió un
            # cumplimiento de resultado entre dos análisis.
            raise ProfileError("el motivo del cambio es obligatorio")

        previous = self.current()
        source = previous if (copy_from_current and previous is not None) else None

        profile = ProfileVersion(
            version=self._next_version_number(),
            is_current=True,
            change_reason=reason[:2000],
            created_by=created_by,
            summary=summary,
        )

        if source is not None:
            # Cada bucle usa su propio nombre: reutilizar uno solo obligaría al
            # verificador de tipos a inferir un tipo común que no existe.
            for experience in source.experience:
                profile.experience.append(_clone_experience(experience))
            for person in source.personnel:
                profile.personnel.append(_clone_personnel(person))
            for capability in source.capabilities:
                profile.capabilities.append(_clone_capability(capability))
            for financial in source.financials:
                profile.financials.append(_clone_financial(financial))
            for legal in source.legal:
                profile.legal.append(_clone_legal(legal))

        self._db.add(profile)
        if previous is not None:
            # La anterior deja de ser vigente en la misma transacción: sin esto
            # habría un instante con dos versiones vigentes y una comparación
            # podría tomar la equivocada.
            previous.is_current = False
        self._db.flush()
        return profile

    def add_experience(self, profile: ProfileVersion, **values: object) -> ExperienceRecord:
        record = ExperienceRecord(**values)
        profile.experience.append(record)
        self._db.flush()
        return record

    def add_personnel(self, profile: ProfileVersion, **values: object) -> PersonnelRecord:
        record = PersonnelRecord(**values)
        profile.personnel.append(record)
        self._db.flush()
        return record

    def add_capability(self, profile: ProfileVersion, **values: object) -> CapabilityRecord:
        record = CapabilityRecord(**values)
        profile.capabilities.append(record)
        self._db.flush()
        return record

    def add_financial(self, profile: ProfileVersion, **values: object) -> FinancialRecord:
        record = FinancialRecord(**values)
        profile.financials.append(record)
        self._db.flush()
        return record

    def add_legal(self, profile: ProfileVersion, **values: object) -> LegalRecord:
        record = LegalRecord(**values)
        profile.legal.append(record)
        self._db.flush()
        return record

    def verify_record(
        self,
        record: VerifiableRecord,
        *,
        status: str,
        actor_id: int | None = None,
    ) -> None:
        """Marca un dato como verificado o pendiente.

        La verificación humana es lo que convierte un dato en algo que puede
        sustentar un cumplimiento. No se hace automáticamente al adjuntar
        evidencia: adjuntar un documento no garantiza que respalde lo afirmado.
        """

        if status not in ("pendiente", "verificado", "rechazado"):
            raise ProfileError(f"estado de verificación no válido: {status}")
        record.verification_status = status
        self._db.flush()

    def commit(self) -> None:
        self._db.commit()

    def rollback(self) -> None:
        self._db.rollback()

    # --- Vencimientos ------------------------------------------------------

    def expiring_soon(self, *, days: int = 30) -> list[tuple[str, object]]:
        """Datos que vencen pronto.

        Se expone para poder avisar antes de que un certificado caduque y deje
        de sustentar cumplimientos sin que nadie lo note.
        """

        from datetime import timedelta

        limit = (datetime.now(UTC) + timedelta(days=days)).date()
        today = datetime.now(UTC).date()
        profile = self.current()
        if profile is None:
            return []

        found: list[tuple[str, object]] = []
        groups: list[tuple[str, list]] = [  # type: ignore[type-arg]
            ("experiencia", list(profile.experience)),
            ("personal", list(profile.personnel)),
            ("capacidades", list(profile.capabilities)),
            ("financiero", list(profile.financials)),
            ("legal", list(profile.legal)),
        ]
        for name, records in groups:
            for item in records:
                until = getattr(item, "valid_until", None)
                if until is None:
                    continue
                if isinstance(until, datetime):
                    until = until.date()
                if today <= until <= limit:
                    found.append((name, item))
        return found


# --- Clonado entre versiones ----------------------------------------------
#
# Se copian los campos explícitamente en lugar de usar `copy.copy`: la copia
# superficial compartiría la identidad de la fila y SQLAlchemy la trataría como
# el mismo registro, de modo que editar la versión nueva modificaría la anterior
# y se perdería justo lo que el versionado pretende conservar.


def _clone_experience(r: ExperienceRecord) -> ExperienceRecord:
    return ExperienceRecord(
        contract_reference=r.contract_reference, entity=r.entity,
        object_description=r.object_description, specialty=r.specialty, role=r.role,
        start_date=r.start_date, end_date=r.end_date, amount=r.amount,
        currency=r.currency, evidence_document_id=r.evidence_document_id,
        evidence_locator=r.evidence_locator,
        verification_status=r.verification_status, valid_from=r.valid_from,
        valid_until=r.valid_until,
    )


def _clone_personnel(r: PersonnelRecord) -> PersonnelRecord:
    return PersonnelRecord(
        internal_id=r.internal_id, full_name=r.full_name, role=r.role,
        education_level=r.education_level, profession=r.profession,
        experience_years=r.experience_years,
        certifications=list(r.certifications or []),
        evidence_document_id=r.evidence_document_id,
        evidence_locator=r.evidence_locator,
        verification_status=r.verification_status, valid_from=r.valid_from,
        valid_until=r.valid_until,
    )


def _clone_capability(r: CapabilityRecord) -> CapabilityRecord:
    return CapabilityRecord(
        name=r.name, category=r.category, description=r.description,
        quantity=r.quantity, unit=r.unit,
        evidence_document_id=r.evidence_document_id,
        evidence_locator=r.evidence_locator,
        verification_status=r.verification_status, valid_from=r.valid_from,
        valid_until=r.valid_until,
    )


def _clone_financial(r: FinancialRecord) -> FinancialRecord:
    return FinancialRecord(
        indicator=r.indicator, period=r.period, value=r.value, unit=r.unit,
        formula=r.formula, evidence_document_id=r.evidence_document_id,
        evidence_locator=r.evidence_locator,
        verification_status=r.verification_status, valid_from=r.valid_from,
        valid_until=r.valid_until,
    )


def _clone_legal(r: LegalRecord) -> LegalRecord:
    return LegalRecord(
        document_type=r.document_type, identifier=r.identifier, issuer=r.issuer,
        issued_on=r.issued_on, valid_until=r.valid_until,
        evidence_document_id=r.evidence_document_id,
        evidence_locator=r.evidence_locator,
        verification_status=r.verification_status, valid_from=r.valid_from,
    )
