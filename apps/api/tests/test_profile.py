"""Pruebas del perfil empresarial.

Se usan sesiones SQLite en archivo temporal. Dos reglas concentran el riesgo y
por eso tienen pruebas específicas:

  - un dato sin evidencia, sin verificar o vencido no puede sustentar un
    «cumple»;
  - editar el perfil crea una versión nueva sin alterar la anterior.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base
from app.profile.service import ProfileError, ProfileService


@pytest.fixture
def db(tmp_path) -> Session:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'p.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def service(db: Session) -> ProfileService:
    return ProfileService(db)


def verified_evidence() -> dict[str, object]:
    """Datos que sí cumplen las tres condiciones para sustentar un cumplimiento."""

    return {"evidence_document_id": 1, "verification_status": "verificado"}


# --- Versionado ------------------------------------------------------------


def test_first_version_is_current(service: ProfileService) -> None:
    profile = service.create_version(change_reason="perfil inicial")

    assert profile.version == 1
    assert profile.is_current
    assert service.current() is profile


def test_creating_a_version_requires_a_reason(service: ProfileService) -> None:
    """Sin motivo, el historial no permite auditar por qué cambió un veredicto."""

    with pytest.raises(ProfileError):
        service.create_version(change_reason="   ")


def test_new_version_marks_the_previous_as_not_current(service: ProfileService) -> None:
    first = service.create_version(change_reason="inicial")
    second = service.create_version(change_reason="se añadió un certificado")

    assert second.version == 2
    assert second.is_current
    assert not first.is_current
    assert service.current() is second


def test_only_one_version_is_current_at_a_time(service: ProfileService) -> None:
    """Dos vigentes harían que una comparación tomara la equivocada."""

    service.create_version(change_reason="v1")
    service.create_version(change_reason="v2")
    service.create_version(change_reason="v3")

    vigentes = [v for v in service.list_versions() if v.is_current]
    assert len(vigentes) == 1


def test_editing_a_version_does_not_alter_the_previous(service: ProfileService) -> None:
    """Un análisis aprobado debe seguir apuntando a la evidencia que usó."""

    first = service.create_version(change_reason="v1")
    service.add_financial(
        first, indicator="patrimonio", period="2024", value=Decimal("1000")
    )
    service.commit()

    second = service.create_version(change_reason="v2", copy_from_current=True)
    nuevo = service.add_financial(
        second, indicator="patrimonio", period="2025", value=Decimal("2500")
    )
    service.commit()

    # La versión anterior conserva su dato original.
    assert len(first.financials) == 1
    assert first.financials[0].value == Decimal("1000")
    assert nuevo.value == Decimal("2500")


def test_copy_from_current_brings_the_existing_data(service: ProfileService) -> None:
    """Añadir un certificado no debe obligar a reescribir todo el perfil."""

    first = service.create_version(change_reason="v1")
    service.add_experience(first, contract_reference="C-001", entity="EAG")
    service.commit()

    second = service.create_version(change_reason="v2", copy_from_current=True)

    assert len(second.experience) == 1
    assert second.experience[0].contract_reference == "C-001"


def test_cloned_records_are_independent(service: ProfileService) -> None:
    """La copia superficial compartiría la fila y editar una alteraría la otra."""

    first = service.create_version(change_reason="v1")
    service.add_experience(first, contract_reference="C-001")
    service.commit()

    second = service.create_version(change_reason="v2", copy_from_current=True)
    second.experience[0].contract_reference = "MODIFICADO"
    service.commit()

    assert first.experience[0].contract_reference == "C-001"


def test_versions_can_be_listed(service: ProfileService) -> None:
    service.create_version(change_reason="v1")
    service.create_version(change_reason="v2")

    versions = service.list_versions()

    assert [v.version for v in versions] == [2, 1]


# --- Evidencia -------------------------------------------------------------


def test_record_with_evidence_and_verification_supports_a_claim(
    service: ProfileService,
) -> None:
    profile = service.create_version(change_reason="v1")
    record = service.add_experience(
        profile, contract_reference="C-001", **verified_evidence()
    )

    assert record.supports_claim


def test_record_without_evidence_does_not_support_a_claim(
    service: ProfileService,
) -> None:
    """Un valor sin soporte puede mostrarse, pero no sostener un «cumple»."""

    profile = service.create_version(change_reason="v1")
    record = service.add_experience(
        profile, contract_reference="C-001", verification_status="verificado"
    )

    assert not record.supports_claim


def test_unverified_record_does_not_support_a_claim(service: ProfileService) -> None:
    """Adjuntar un documento no garantiza que respalde lo afirmado."""

    profile = service.create_version(change_reason="v1")
    record = service.add_experience(
        profile, contract_reference="C-001", evidence_document_id=1,
        verification_status="pendiente",
    )

    assert not record.supports_claim


def test_expired_record_does_not_support_a_claim(service: ProfileService) -> None:
    """Un certificado vencido deja de sustentar cumplimientos sin que nadie lo note."""

    profile = service.create_version(change_reason="v1")
    ayer = datetime.now(UTC).date() - timedelta(days=1)
    record = service.add_legal(
        profile, document_type="RUP", valid_until=ayer, **verified_evidence()
    )

    assert record.is_expired
    assert not record.supports_claim


def test_record_without_expiry_is_not_expired(service: ProfileService) -> None:
    """No consta vencimiento no significa vencido."""

    profile = service.create_version(change_reason="v1")
    record = service.add_experience(
        profile, contract_reference="C-001", **verified_evidence()
    )

    assert not record.is_expired
    assert record.supports_claim


def test_verification_can_be_changed(service: ProfileService) -> None:
    profile = service.create_version(change_reason="v1")
    record = service.add_experience(
        profile, contract_reference="C-001", evidence_document_id=1
    )
    assert not record.supports_claim

    service.verify_record(record, status="verificado")

    assert record.supports_claim


def test_invalid_verification_status_is_rejected(service: ProfileService) -> None:
    profile = service.create_version(change_reason="v1")
    record = service.add_experience(profile, contract_reference="C-001")

    with pytest.raises(ProfileError):
        service.verify_record(record, status="inventado")


# --- Valores desconocidos --------------------------------------------------


def test_missing_amount_is_none_not_zero(service: ProfileService) -> None:
    """«No consta» y «vale cero» producen veredictos distintos al comparar."""

    profile = service.create_version(change_reason="v1")
    record = service.add_experience(profile, contract_reference="C-001")

    assert record.amount is None
    assert record.amount != 0


def test_explicit_zero_is_preserved(service: ProfileService) -> None:
    """Un valor cero real debe distinguirse de la ausencia de dato."""

    profile = service.create_version(change_reason="v1")
    record = service.add_financial(
        profile, indicator="sanciones", period="2024", value=Decimal("0")
    )

    assert record.value == Decimal("0")
    assert record.value is not None


# --- Preparación -----------------------------------------------------------


def test_readiness_without_a_profile_explains_what_to_do(
    service: ProfileService,
) -> None:
    readiness = service.readiness()

    assert not readiness.is_ready
    assert not readiness.has_any_data
    assert any("cree una" in n for n in readiness.notes)


def test_readiness_reports_usable_records(service: ProfileService) -> None:
    profile = service.create_version(change_reason="v1")
    service.add_experience(profile, contract_reference="C-001", **verified_evidence())
    service.add_experience(profile, contract_reference="C-002")  # sin evidencia
    service.commit()

    readiness = service.readiness()

    assert readiness.total_records == 2
    assert readiness.usable_records == 1


def test_readiness_warns_about_records_that_cannot_support_claims(
    service: ProfileService,
) -> None:
    profile = service.create_version(change_reason="v1")
    service.add_experience(profile, contract_reference="C-001")
    service.commit()

    readiness = service.readiness()

    assert any("no pueden sustentar" in n for n in readiness.notes)


def test_readiness_reports_empty_sections(service: ProfileService) -> None:
    profile = service.create_version(change_reason="v1")
    service.add_experience(profile, contract_reference="C-001")
    service.commit()

    readiness = service.readiness()

    assert any("sin datos" in n for n in readiness.notes)


def test_empty_profile_is_not_ready(service: ProfileService) -> None:
    """Comparar contra un perfil vacío no aporta nada."""

    service.create_version(change_reason="v1")

    assert not service.readiness().is_ready


def test_readiness_counts_expired_records(service: ProfileService) -> None:
    profile = service.create_version(change_reason="v1")
    ayer = datetime.now(UTC).date() - timedelta(days=1)
    service.add_legal(profile, document_type="RUP", valid_until=ayer, **verified_evidence())
    service.add_legal(profile, document_type="Cámara", **verified_evidence())
    service.commit()

    readiness = service.readiness()

    legal = next(s for s in readiness.sections if s.name == "legal")
    assert legal.expired == 1
    assert legal.supports_claims == 1


# --- Vencimientos próximos -------------------------------------------------


def test_expiring_soon_finds_upcoming_expirations(service: ProfileService) -> None:
    """Avisar antes evita que un certificado caduque sin que nadie lo note."""

    profile = service.create_version(change_reason="v1")
    en_diez = datetime.now(UTC).date() + timedelta(days=10)
    service.add_legal(profile, document_type="RUP", valid_until=en_diez)
    service.commit()

    proximos = service.expiring_soon(days=30)

    assert len(proximos) == 1
    assert proximos[0][0] == "legal"


def test_expiring_soon_ignores_far_future(service: ProfileService) -> None:
    profile = service.create_version(change_reason="v1")
    lejos = datetime.now(UTC).date() + timedelta(days=400)
    service.add_legal(profile, document_type="RUP", valid_until=lejos)
    service.commit()

    assert service.expiring_soon(days=30) == []


def test_expiring_soon_ignores_records_without_expiry(service: ProfileService) -> None:
    profile = service.create_version(change_reason="v1")
    service.add_experience(profile, contract_reference="C-001")
    service.commit()

    assert service.expiring_soon(days=30) == []


# --- Secciones -------------------------------------------------------------


def test_all_profile_sections_can_be_filled(service: ProfileService) -> None:
    profile = service.create_version(change_reason="v1")
    service.add_experience(profile, contract_reference="C-001")
    service.add_personnel(profile, full_name="Ana", role="Ingeniera")
    service.add_capability(profile, name="Retroexcavadora", quantity=Decimal("2"), unit="unidad")
    service.add_financial(profile, indicator="liquidez", period="2024", value=Decimal("1.8"))
    service.add_legal(profile, document_type="RUP")
    service.commit()

    readiness = service.readiness()

    assert readiness.total_records == 5
    assert all(not s.is_empty for s in readiness.sections)


def test_capability_quantity_keeps_its_unit(service: ProfileService) -> None:
    """Un «3» sin unidad no es comparable contra un requisito."""

    profile = service.create_version(change_reason="v1")
    record = service.add_capability(
        profile, name="Volqueta", quantity=Decimal("3"), unit="unidad"
    )

    assert record.quantity == Decimal("3")
    assert record.unit == "unidad"


def test_financial_record_stores_its_formula(service: ProfileService) -> None:
    """Sin fórmula, dos personas calculan distinto el mismo indicador."""

    profile = service.create_version(change_reason="v1")
    record = service.add_financial(
        profile,
        indicator="capital de trabajo",
        period="2024",
        value=Decimal("500000"),
        formula="activo corriente - pasivo corriente",
    )

    assert record.formula is not None


def test_personnel_stores_certifications_list(service: ProfileService) -> None:
    profile = service.create_version(change_reason="v1")
    record = service.add_personnel(
        profile, full_name="Ana", certifications=["PMP", "ISO 9001"]
    )

    assert "PMP" in record.certifications
