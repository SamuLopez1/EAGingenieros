"""Dos fichas, reglas conservadoras y transiciones con evidencia sintética."""

from datetime import date
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.comparison import evaluate_value, rows_for
from app.db.session import create_session_factory
from app.documents.extraction import Fragment, Locator, Result
from app.documents.extraction_worker import run_one
from app.documents.requirements import OfflineAdapter, build_analysis
from app.profile import Entry
from tests.test_dossier import ADMIN, ANALYST, OUTSIDER, api, pdf, upload
from tests.test_dossier import catalog as catalog
from tests.test_profile import EVIDENCE, HEADERS, PATH
from tests.test_requirements import source


def item(title: str, evidence: str, value: int, unit: str = "meses", **fields: object) -> dict:
    return {
        "category": "experiencia",
        "title": title,
        "status": "verificado",
        "amount": value,
        "unit": unit,
        "evidence": [{"document_id": evidence, "locator": "Página 4"}],
        **fields,
    }


@pytest.mark.parametrize(
    ("clause", "value", "unit", "expected"),
    [
        ("minimo 1 ano", 12, "meses", "cumple"),
        ("minimo 1 ano", 11, "meses", "no_cumple"),
        ("maximo 1 ano", 12, "meses", "cumple"),
        ("minimo 20 cop", 20, "usd", "revision_manual"),
        ("minimo 0 unidad", 0, "unidad", "cumple"),
        ("minimo 1.000 cop", 1000, "cop", "revision_manual"),
    ],
)
def test_numeric_limits_and_units(clause, value, unit, expected) -> None:
    entry = Entry.model_validate(item("Experiencia", str(UUID(int=1)), value, unit))
    assert evaluate_value(clause, entry, None)[0] == expected


def test_validity_missing_evidence_and_contradiction() -> None:
    entry = Entry.model_validate(
        item(
            "Experiencia",
            str(UUID(int=1)),
            12,
            starts_on="2026-01-01",
            ends_on="2026-12-31",
        )
    )
    assert evaluate_value("vigente al 2026-12-31", entry, None)[0] == "cumple"
    assert evaluate_value("vigente al 2027-01-01", entry, None)[0] == "no_cumple"
    assert evaluate_value("minimo 1 ano", entry, None)[0] == "revision_manual"
    assert evaluate_value("minimo 1 ano", entry, date(2026, 12, 31))[0] == "cumple"
    a = source("Habilitante: Experiencia: mínimo 12 meses.")
    b = source("Habilitante: Experiencia: mínimo 24 meses.", adenda=True)
    result = build_analysis(OfflineAdapter(), "sintético", [a, b], [])
    assert {row.outcome for row in rows_for(result, [entry], date(2026, 12, 31))} == {
        "revision_manual"
    }
    only_a = build_analysis(OfflineAdapter(), "sintético", [a], [])
    assert rows_for(only_a, [], None)[0].outcome == "revision_manual"


def comparison_path(opp: int) -> str:
    return f"/api/v1/opportunities/{opp}/comparison"


def version_fields(snapshot: dict) -> dict:
    return {"fingerprint": snapshot["fingerprint"], "revision": snapshot["revision"]}


def request_approval(client: TestClient, path: str, snapshot: dict, headers=ADMIN):
    return client.post(
        f"{path}/approve",
        headers=headers,
        json={
            **version_fields(snapshot),
            "reason": "Revisión humana sobre caso sintético.",
        },
    )


def test_two_opportunities_audit_corrections_and_invalidation(catalog) -> None:
    client, _, settings, engine = catalog
    factory = create_session_factory(engine)
    evidence = [
        client.post(EVIDENCE, headers=HEADERS, content=pdf(marker)).json()["id"]
        for marker in ("perfil A", "perfil B")
    ]
    entries = [
        item("Experiencia vial", evidence[0], 12),
        item("Experiencia hídrica", evidence[1], 6),
    ]
    assert (
        client.put(PATH, headers=ADMIN, json={"base_version": 0, "entries": entries}).status_code
        == 201
    )

    def select(opp: int, doc: dict, text: str) -> None:
        root = f"{api(opp)}/{doc['id']}"
        assert client.post(f"{root}/review", headers=ANALYST).status_code == 200
        assert client.post(f"{root}/extraction", headers=ANALYST).status_code == 202
        run_one(
            factory,
            settings,
            lambda *_: Result(
                status="listo",
                fragments=[Fragment(locator=Locator(page=2), text=text)],
            ),
        )

    a = upload(client, 1, "Pliego A", pdf("pliego A 1")).json()
    b = upload(client, 2, "Pliego B", pdf("pliego B 1")).json()
    select(1, a, "Habilitante: Experiencia vial: mínimo 1 año.")
    select(2, b, "Habilitante: Experiencia hídrica: mínimo 12 meses.")
    pa, pb = comparison_path(1), comparison_path(2)
    assert client.get(pa).status_code == 401
    assert client.post(pa, headers=OUTSIDER).status_code == 403
    first_a = client.post(pa, headers=ANALYST).json()
    first_b_response = client.post(pb, headers=ANALYST)
    assert first_b_response.headers["cache-control"] == "private, no-store"
    first_b = first_b_response.json()
    assert [first_a["rows"][0]["outcome"], first_b["rows"][0]["outcome"]] == ["cumple", "no_cumple"]
    for snapshot, doc, ref in zip([first_a, first_b], [a, b], evidence, strict=True):
        row = snapshot["rows"][0]
        assert (
            row["citation"]["document_id"] == doc["id"] and row["citation"]["locator"]["page"] == 2
        )
        assert row["profile_sources"][0]["evidence"] == [
            {"document_id": ref, "locator": "Página 4"}
        ]
        assert client.get(f"{EVIDENCE}/{ref}", headers=ANALYST).status_code == 200
    assert request_approval(client, pa, first_a, ANALYST).status_code == 403
    assert (
        client.post(
            f"{pa}/corrections",
            headers=ANALYST,
            json={
                **version_fields(first_a),
                "row_id": first_a["rows"][0]["id"],
                "outcome": "cumple_parcialmente",
                "reason": "Evidencia insuficiente en esta prueba.",
            },
        ).status_code
        == 422
    )
    corrected = client.post(
        f"{pa}/corrections",
        headers=ANALYST,
        json={
            **version_fields(first_a),
            "row_id": first_a["rows"][0]["id"],
            "outcome": "cumple_parcialmente",
            "profile_entry": 0,
            "reason": "Justificación sintética.",
        },
    ).json()
    assert corrected["rows"][0]["outcome"] == "cumple_parcialmente"
    assert request_approval(client, pa, first_a).status_code == 409
    approved_a = request_approval(client, pa, corrected).json()
    approved_b = request_approval(client, pb, first_b).json()
    assert approved_a["status"] == approved_b["status"] == "aprobado"
    ix = approved_a["rows"][0]["id"]
    assert [event["action"] for event in approved_a["audit"]] == [
        "aprobado",
        "corregido",
        "generado",
    ]
    approved = approved_a["audit"][0]
    assert approved["actor_id"] == str(UUID(int=1)) and approved["profile_version"] == 1
    assert approved["outcomes"] == {ix: "cumple_parcialmente"}
    assert approved["document_versions"] == [{"id": a["id"], "version": 1, "sha256": a["sha256"]}]
    assert approved_a["audit"][1]["actor_id"] == str(UUID(int=2))
    assert approved_a["audit"][1]["before"] == "cumple"
    assert client.post(pa, headers=ANALYST).json()["revision"] == approved_a["revision"]
    assert client.post(f"{api(1)}/{a['id']}/review", headers=ANALYST).status_code == 200
    assert client.get(pa, headers=ANALYST).json()["status"] == "aprobado"

    # Un cambio posterior de decisión invalida la aprobación y conserva el evento original.
    after_edit = client.post(
        f"{pa}/corrections",
        headers=ANALYST,
        json={
            **version_fields(approved_a),
            "row_id": ix,
            "outcome": "revision_manual",
            "reason": "Reabrir para verificar el alcance.",
        },
    ).json()
    assert after_edit["status"] == "borrador" and after_edit["audit"][1]["action"] == "aprobado"
    reapproved_a = request_approval(client, pa, after_edit).json()

    replacement = upload(client, 1, "Pliego A", pdf("pliego A 2")).json()
    invalid_a = client.get(pa, headers=ANALYST).json()
    assert invalid_a["status"] == "invalidado" and invalid_a["invalidated_by"] == ["expediente"]
    assert request_approval(client, pa, reapproved_a).status_code == 409
    assert client.get(pb, headers=ANALYST).json()["status"] == "aprobado"
    select(1, replacement, "Habilitante: Experiencia vial: mínimo 18 meses.")
    updated_a = client.post(pa, headers=ANALYST).json()
    assert updated_a["rows"][0]["citation"]["version"] == 2
    assert request_approval(client, pa, updated_a).json()["status"] == "aprobado"

    upload(client, 2, "Adenda B", pdf("adenda B"), kind="adenda")
    assert client.get(pb, headers=ANALYST).json()["invalidated_by"] == ["expediente"]
    assert client.get(pa, headers=ANALYST).json()["status"] == "aprobado"
    assert (
        client.put(PATH, headers=ADMIN, json={"base_version": 1, "entries": entries}).status_code
        == 201
    )
    assert client.get(pa, headers=ANALYST).json()["invalidated_by"] == ["perfil"]
    invalid_b = client.get(pb, headers=ANALYST).json()
    assert set(invalid_b["invalidated_by"]) == {"expediente", "perfil"}
    assert invalid_b["audit"][0]["action"] == "aprobado"


def test_selection_change_then_reversion_never_revives_approval(catalog) -> None:
    client, _, settings, engine = catalog
    first = upload(client, 1, "Pliego", pdf("uno")).json()
    second = upload(client, 1, "Pliego", pdf("dos")).json()

    def mark(document: dict) -> None:
        root = f"{api(1)}/{document['id']}"
        assert client.post(f"{root}/review", headers=ANALYST).status_code == 200

    mark(second)
    assert client.post(f"{api(1)}/{second['id']}/extraction", headers=ANALYST).status_code == 202
    run_one(
        create_session_factory(engine),
        settings,
        lambda *_: Result(
            status="listo",
            fragments=[Fragment(locator=Locator(page=1), text="Habilitante: Experiencia.")],
        ),
    )
    assert (
        client.put(PATH, headers=ADMIN, json={"base_version": 0, "entries": []}).status_code == 201
    )
    resource = comparison_path(1)
    draft = client.post(resource, headers=ANALYST).json()
    assert request_approval(client, resource, draft).json()["status"] == "aprobado"
    mark(first)
    mark(second)
    assert client.get(resource, headers=ANALYST).json()["status"] == "invalidado"
