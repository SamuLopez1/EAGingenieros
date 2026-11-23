"""Cobertura de dedicaciones, permisos y correcciones con datos sintéticos."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from app.comparison import rows_for
from app.db.session import create_session_factory
from app.documents.extraction import Fragment, Locator, Result
from app.documents.extraction_worker import run_one
from app.documents.requirements import OfflineAdapter, build_analysis
from app.profile import Entry
from app.staffing import demand_for, fit_for, plans_for
from tests.test_comparison import comparison_path, item
from tests.test_dossier import ADMIN, ANALYST, OUTSIDER, api, pdf, upload
from tests.test_dossier import catalog as catalog
from tests.test_profile import EVIDENCE, HEADERS, PATH
from tests.test_requirements import source

ID = str(UUID(int=20))
FIRST = "Habilitante: Cargo: Residente; dedicación: 60%; periodo: 2026-12-01 a 2026-12-20."
SECOND = "Obligación: Cargo: Residente; dedicación: 50%; periodo: 2026-12-11 a 2026-12-30."
UNCONFIRMED = "Habilitante: Cargo: Topógrafo; dedicación: 30%."


def availability(value: int | None, start: str | None, end: str | None, **kwargs: object) -> dict:
    return {
        "category": "disponibilidad",
        "title": "Cobertura registrada",
        "role": "Residente",
        "dedication_percent": value,
        "starts_on": start,
        "ends_on": end,
        "status": "verificado",
        "evidence": [{"document_id": ID, "locator": "Hoja QA, B3"}],
        **kwargs,
    }


def demands(*content: str):
    analysis = build_analysis(OfflineAdapter(), "staff-qa", [source("\n".join(content))], [])
    return [d for row in rows_for(analysis, [], None) if (d := demand_for(row, None, set()))]


def test_full_capacity_and_overlap_shortfall() -> None:
    records = [Entry.model_validate(availability(80, "2026-12-01", "2026-12-30"))]
    plan = plans_for(demands(FIRST, SECOND), records)[0]
    assert [(p.start.day, p.end.day, p.status, p.required, p.shortfall) for p in plan.periods] == [
        (1, 10, "confirmada", Decimal(60), Decimal(0)),
        (11, 20, "insuficiente", Decimal(110), Decimal(30)),
        (21, 30, "confirmada", Decimal(50), Decimal(0)),
    ]
    gap = plan.periods[1]
    assert gap.evaluate_staffing and len(gap.demand_ids) == 2
    assert len(gap.evidence) == 1 and gap.evidence[0].locator == "Hoja QA, B3"


def test_no_coverage_is_unknown_but_verified_zero_is_shortfall() -> None:
    demand = demands(FIRST)
    missing = plans_for(demand, [])[0].periods[0]
    assert missing.status == "por_confirmar" and missing.recorded is None
    assert missing.verify_availability and not missing.evaluate_staffing
    none = Entry.model_validate(availability(0, "2026-12-01", "2026-12-20"))
    gap = plans_for(demand, [none])[0].periods[0]
    assert gap.status == "insuficiente" and gap.shortfall == 60


def test_pending_partial_period_and_overlapping_supply_not_added() -> None:
    registered = [
        Entry.model_validate(availability(40, "2026-12-01", "2026-12-11")),
        Entry.model_validate(availability(40, "2026-12-01", "2026-12-11", title="Otro registro")),
        Entry.model_validate(availability(70, "2026-12-10", "2026-12-12")),
        Entry.model_validate(availability(None, None, None, status="pendiente", evidence=[])),
    ]
    parts = plans_for(demands(FIRST), registered)[0].periods
    assert [(p.start.day, p.end.day, p.status, p.recorded) for p in parts] == [
        (1, 9, "por_confirmar", Decimal(40)),
        (10, 11, "por_confirmar", Decimal(40)),
        (12, 12, "confirmada", Decimal(70)),
        (13, 20, "por_confirmar", None),
    ]
    assert parts[0].evaluate_staffing and parts[0].shortfall == 20
    assert parts[1].verify_availability and "superpuestos" in parts[1].reason


def test_missing_period_and_cited_service_line() -> None:
    pending = demands(UNCONFIRMED)[0]
    assert pending.missing == ["inicio", "fin"]
    assert plans_for([pending], [])[0].periods == []
    explicit = build_analysis(
        OfflineAdapter(),
        "fit",
        [
            source("Objeto: Línea de servicio: Consultoría vial."),
            source("Objeto: Línea de servicio: Interventoría.", adenda=True),
        ],
        [],
    )
    matched = Entry.model_validate(
        item(
            "Capacidad vial",
            ID,
            12,
            service_line="Consultoría vial",
            starts_on="2026-01-01",
            ends_on="2026-12-20",
        )
    )
    assert [(f.line, f.status) for f in fit_for(explicit, [matched], date(2026, 12, 20))] == [
        ("Consultoría vial", "respaldado"),
        ("Interventoría", "por_confirmar"),
    ]
    assert not fit_for(explicit, [matched], date(2026, 12, 21))[0].support


def test_private_plan_audits_edits_for_exact_comparison(catalog) -> None:
    client, _, settings, engine = catalog
    path = "/api/v1/opportunities/1/staffing"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=OUTSIDER).status_code == 403
    assert client.get(path, headers=ANALYST).json()["status"] == "comparacion_pendiente"
    evidence = client.post(EVIDENCE, headers=HEADERS, content=pdf("perfil QA")).json()["id"]
    entries = [
        item("Experiencia vial", evidence, 12, service_line="Consultoría vial"),
        item("Experiencia limitada", evidence, 12),
        availability(
            80,
            "2026-12-01",
            "2026-12-30",
            evidence=[{"document_id": evidence, "locator": "Página 2"}],
        ),
    ]
    assert (
        client.put(PATH, headers=ADMIN, json={"base_version": 0, "entries": entries}).status_code
        == 201
    )
    document = upload(client, 1, "Pliego QA", pdf("QA staffing")).json()
    root = f"{api(1)}/{document['id']}"
    assert client.post(f"{root}/review", headers=ANALYST).status_code == 200
    assert client.post(f"{root}/extraction", headers=ANALYST).status_code == 202
    assert run_one(
        create_session_factory(engine),
        settings,
        lambda *_: Result(
            status="listo",
            fragments=[
                Fragment(
                    text="\n".join(
                        (
                            "Objeto: Línea de servicio: Consultoría vial.",
                            FIRST,
                            SECOND,
                            UNCONFIRMED,
                            "Habilitante: Experiencia limitada: mínimo 24 meses.",
                        )
                    ),
                    locator=Locator(page=1),
                )
            ],
        ),
    )
    comparison = client.post(comparison_path(1), headers=ANALYST).json()
    response = client.get(path, headers=ANALYST)
    assert response.headers["cache-control"] == "private, no-store"
    snapshot = response.json()
    assert snapshot["profile_version"] == 1 and not snapshot["can_correct"]
    assert snapshot["document_versions"][0]["id"] == document["id"]
    assert snapshot["service_fit"][0]["status"] == "respaldado"
    assert (
        snapshot["qualifying_gaps"]
        and snapshot["qualifying_gaps"][0]["outcome"] == "revision_manual"
    )
    assert "no_cumple" in {gap["outcome"] for gap in snapshot["qualifying_gaps"]}
    assert len(snapshot["demands"]) == 3
    row = next(d for d in snapshot["demands"] if d["role"] == "Topógrafo")
    body = {
        "revision": comparison["revision"],
        "fingerprint": comparison["fingerprint"],
        "expected_event": 0,
        "row_id": row["row_id"],
        "role": "Topógrafo",
        "dedication": "30",
        "start": "2026-12-10",
        "end": "2026-12-20",
        "reason": "Periodo verificado en la fixture.",
    }
    assert client.post(f"{path}/corrections", headers=ANALYST, json=body).status_code == 403
    assert client.post(f"{path}/corrections", headers=OUTSIDER, json=body).status_code == 403
    response = client.post(f"{path}/corrections", headers=ADMIN, json=body)
    assert response.status_code == 200
    after = response.json()
    assert after["audit"][0]["previous"]["start"] is None
    assert after["audit"][0]["actor_id"] == str(UUID(int=1))
    assert "fixture" in after["audit"][0]["reason"]
    top = next(role for role in after["roles"] if role["role"] == "Topógrafo")
    assert top["periods"][0]["status"] == "por_confirmar"
    assert client.post(f"{path}/corrections", headers=ADMIN, json=body).status_code == 409
    alt = path.replace("/1/", "/2/")
    assert not client.get(alt, headers=ANALYST).json()["roles"]
    assert (
        client.put(PATH, headers=ADMIN, json={"base_version": 1, "entries": entries}).status_code
        == 201
    )
    assert client.get(path, headers=ANALYST).json()["status"] == "comparacion_pendiente"
    assert client.post(f"{path}/corrections", headers=ADMIN, json=body).status_code == 409
