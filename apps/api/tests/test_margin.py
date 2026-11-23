"""Escenarios sintéticos con Decimal, trazabilidad y permisos."""

from copy import deepcopy
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.models import Opportunity
from app.margin import ScenarioInputs, calculate, published_budget
from app.secop.client import PROCESSES_DATASET
from tests.test_dossier import ADMIN, ANALYST, OUTSIDER, pdf, upload
from tests.test_dossier import catalog as catalog

MARGIN = "/api/v1/opportunities/1/margin"


def assumed(value: str | None, source: str | None = "Fuente de prueba") -> dict:
    return {"amount": value, "source": source}


def scenario(income="100", hiring="10", **kwargs) -> dict:
    return {
        "name": "Base sintética",
        "currency": "COP",
        "base_version": 0,
        "income": assumed(income),
        "costs": {
            "direct": assumed("30"),
            "indirect": assumed("5"),
            "internal_staff": assumed("20"),
            "hiring": assumed(hiring),
            "contingency": assumed("5"),
        },
        **kwargs,
    }


@pytest.mark.parametrize(
    ("income", "hiring", "status", "cost", "profit", "margin"),
    [
        ("100", "10", "calculado", "70", "30", "30"),
        ("100", "51.01", "calculado", "111.01", "-11.01", "-11.01"),
        ("60", "0", "calculado", "60", "0", "0"),
        ("0", "0", "ingreso_cero", "60", "-60", None),
        ("100", None, "pendiente", None, None, None),
    ],
)
def test_calculation_with_hiring_and_unknowns(income, hiring, status, cost, profit, margin) -> None:
    raw = scenario(income, hiring)
    raw.pop("base_version")
    result = calculate(ScenarioInputs.model_validate(raw))
    assert result.status == status
    outputs = tuple(None if v is None else Decimal(v) for v in (cost, profit, margin))
    assert (result.total_cost, result.profit, result.margin_percent) == outputs
    if hiring is None:
        assert result.missing_amounts == ["hiring"]


def test_rounding_decimal_and_invalid_financial_inputs() -> None:
    raw = scenario("3")
    raw.pop("base_version")
    for cost in raw["costs"]:
        raw["costs"][cost] = assumed("0")
    raw["costs"]["direct"] = assumed("2")
    assert calculate(ScenarioInputs.model_validate(raw)).margin_percent == Decimal("33.33")
    raw["costs"]["direct"] = assumed("3.1")
    assert calculate(ScenarioInputs.model_validate(raw)).margin_percent == Decimal("-3.33")
    raw["income"] = assumed("32")
    raw["costs"]["direct"] = assumed("31.99")
    assert calculate(ScenarioInputs.model_validate(raw)).margin_percent == Decimal("0.03")
    raw["income"] = assumed("8")
    raw["costs"]["direct"] = assumed("7.99")
    assert calculate(ScenarioInputs.model_validate(raw)).margin_percent == Decimal("0.13")
    for value in ("-1", "0.001", "NaN", "Infinity", "10000000000000000"):
        raw["costs"]["direct"] = assumed(value)
        with pytest.raises(ValidationError):
            ScenarioInputs.model_validate(raw)


def test_published_budget_is_only_a_reference() -> None:
    assert published_budget(PROCESSES_DATASET, "1.20").amount == Decimal("1.20")
    assert published_budget(PROCESSES_DATASET, "0").amount == Decimal(0)
    for value in (None, "", "1,000.00", True, "-1", "NaN"):
        assert published_budget(PROCESSES_DATASET, value) is None
    assert published_budget("otra-fuente", "100") is None


def update_budget(engine, value):
    with Session(engine) as session:
        op = session.get(Opportunity, 1)
        op.source_dataset = PROCESSES_DATASET
        op.raw_payload = {**op.raw_payload, "precio_base": value}
        session.commit()


def test_scenarios_api_versions_permissions_and_isolation(catalog) -> None:
    client, _, _, engine = catalog
    update_budget(engine, "1000")
    assert client.get(MARGIN).status_code == 401
    assert client.get(MARGIN, headers=OUTSIDER).status_code == 403
    response = client.get(MARGIN, headers=ANALYST)
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["basis"]["published_budget"]["amount"] == "1000.00"
    assert response.json()["scenarios"] == []

    pending = client.post(MARGIN, headers=ANALYST, json=scenario(None, None)).json()
    assert pending["inputs"]["income"]["amount"] is None
    assert pending["calculation"]["missing_amounts"] == ["income", "hiring"]
    base = client.post(MARGIN, headers=ANALYST, json=scenario()).json()
    downside = client.post(MARGIN, headers=ANALYST, json=scenario("100", "60")).json()
    assert [base["calculation"]["profit"], downside["calculation"]["profit"]] == ["30.00", "-20.00"]
    assert len(client.get(MARGIN, headers=ANALYST).json()["scenarios"]) == 3

    path = f"{MARGIN}/{base['id']}"
    other_path = path.replace("/1/", "/2/")
    assert client.get(f"{other_path}/versions", headers=ANALYST).status_code == 404
    assert client.put(other_path, headers=ADMIN, json=scenario(base_version=1)).status_code == 404
    review = {"base_version": 1, "reason": "Validación de entradas sintéticas."}
    assert client.post(f"{path}/review", headers=ANALYST, json=review).status_code == 403
    reviewed = client.post(f"{path}/review", headers=ADMIN, json=review).json()
    assert reviewed["review_status"] == "revisado" and reviewed["version"] == 2
    assert reviewed["event"] == "revision"
    assert client.put(path, headers=ANALYST, json=scenario(base_version=1)).status_code == 409
    changed = client.put(
        path,
        headers=ANALYST,
        json=scenario(
            "200",
            base_version=2,
            reason="Supuesto actualizado para ensayo.",
        ),
    ).json()
    assert changed["version"] == 3 and changed["review_status"] == "pendiente"
    history = client.get(f"{path}/versions", headers=ANALYST).json()
    assert [item["version"] for item in history] == [3, 2, 1]
    assert [item["actor_id"] for item in history] == [
        base["actor_id"],
        reviewed["actor_id"],
        base["actor_id"],
    ]
    assert (
        client.get(f"{path}/versions/1", headers=ANALYST).json()["calculation"]
        == base["calculation"]
    )
    assert client.get(f"{path}/versions?before=3", headers=ANALYST).json() == history[1:]


def test_explicit_reference_stale_sources_and_pending_assumptions(catalog) -> None:
    client, _, _, engine = catalog
    update_budget(engine, "800")
    raw = scenario(None, income_mode="presupuesto_publicado")
    assert client.post(MARGIN, headers=ANALYST, json=raw).status_code == 409
    raw.update(published_amount="800", income=assumed(None, None))
    assert client.post(MARGIN, headers=ANALYST, json=raw).status_code == 422
    raw["income"]["source"] = "Referencia del pliego en COP como supuesto sintético."
    base = client.post(MARGIN, headers=ANALYST, json=raw).json()
    assert base["inputs"]["income"]["amount"] == "800.00"
    assert base["calculation"]["profit"] == "730.00"
    path = f"{MARGIN}/{base['id']}"
    update_budget(engine, "850")
    version = client.get(f"{path}/versions/1", headers=ANALYST).json()
    assert version["review_status"] == "desactualizado"
    assert version["inputs"]["income"]["amount"] == "800.00"
    reason = "Revisión sintética de Finanzas."
    assert (
        client.post(
            f"{path}/review", headers=ADMIN, json={"base_version": 1, "reason": reason}
        ).status_code
        == 409
    )
    old_reference = {**raw, "base_version": 1}
    assert client.put(path, headers=ANALYST, json=old_reference).status_code == 409
    draft = deepcopy(raw)
    draft.update(base_version=1, published_amount="850")
    draft["costs"]["hiring"] = assumed("0", None)
    new = client.put(path, headers=ANALYST, json=draft).json()
    assert new["calculation"]["status"] == "calculado"
    assert new["calculation"]["missing_sources"] == ["hiring"]
    assert (
        client.post(
            f"{path}/review", headers=ADMIN, json={"base_version": 2, "reason": reason}
        ).status_code
        == 409
    )
    # Un cambio documental marca obsoleto el contexto sin sobrescribir sus montos.
    upload(client, 1, "Adenda nueva", pdf("escenario"), kind="adenda")
    assert (
        client.get(f"{path}/versions/2", headers=ANALYST).json()["review_status"]
        == "desactualizado"
    )
