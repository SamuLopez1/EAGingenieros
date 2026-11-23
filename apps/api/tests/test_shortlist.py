"""Persistencia, aislamiento y proyección de fichas sintéticas."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import Opportunity
from app.db.repository import SqlOpportunityRepository
from app.db.session import create_session_factory
from app.documents.extraction import Fragment, Locator, Result
from app.documents.extraction_worker import run_one
from tests.test_comparison import comparison_path
from tests.test_dossier import ADMIN, ANALYST, OUTSIDER, api, pdf, upload
from tests.test_dossier import catalog as catalog
from tests.test_margin import assumed, scenario
from tests.test_profile import EVIDENCE, HEADERS, PATH
from tests.test_staffing import FIRST, SECOND, availability
from tests.test_sync_repository import make_record

ROOT = "/api/v1/opportunity-shortlist"


def save(client, revision: int, ids: list[int], headers=ANALYST):
    return client.put(ROOT, headers=headers, json={"revision": revision, "opportunity_ids": ids})


def add_opportunities(engine) -> None:
    with Session(engine) as session:
        SqlOpportunityRepository(session).upsert_many(
            [make_record("SYNTH-C"), make_record("SYNTH-D")]
        )
        session.commit()


def test_list_is_private_ordered_and_bounded(catalog) -> None:
    client, _, _, engine = catalog
    add_opportunities(engine)
    assert client.get(ROOT).status_code == 401
    assert client.get(ROOT, headers=OUTSIDER).status_code == 403
    assert client.get(f"{ROOT}/comparison", headers=ANALYST).status_code == 409
    assert save(client, 0, [1, 2, 3, 4]).status_code == 422
    assert save(client, 0, [1, 1]).status_code == 422
    assert save(client, 0, [1, 99]).status_code == 404
    response = save(client, 0, [2, 1])
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    assert [item["id"] for item in response.json()["items"]] == [2, 1]
    first = response.json()["revision"]
    assert client.get(ROOT, headers=ANALYST).json() == response.json()
    assert client.get(ROOT, headers=ADMIN).json()["items"] == []
    assert save(client, 0, [3], ADMIN).json()["items"][0]["id"] == 3
    assert save(client, 0, [2, 3]).status_code == 409
    assert save(client, first, [2, 1]).json()["revision"] == first
    second = save(client, first, [2, 1, 3]).json()
    assert second["revision"] == first + 1
    matrix = client.get(f"{ROOT}/comparison", headers=ANALYST).json()
    assert [col["opportunity"]["id"] for col in matrix["columns"]] == [2, 1, 3]
    with Session(engine) as session:
        session.delete(session.get(Opportunity, 3))
        session.commit()
    unavailable = client.get(f"{ROOT}/comparison", headers=ANALYST).json()["columns"][2]
    assert unavailable["opportunity"] == {
        "id": 3,
        "title": None,
        "reference": None,
        "available": False,
    }
    assert save(client, second["revision"], [2]).json()["items"][0]["id"] == 2
    assert client.get(f"{ROOT}/comparison", headers=ANALYST).status_code == 409
    assert client.get(ROOT, headers=ADMIN).json()["items"][0]["id"] == 3


def test_comparison_uses_current_ficha_results_and_keeps_pending(catalog) -> None:
    client, _, settings, engine = catalog
    add_opportunities(engine)
    with Session(engine) as session:
        first = session.get(Opportunity, 1)
        first.raw_payload = {**first.raw_payload, "precio_base": "800"}
        first.reception_at = datetime(2026, 12, 10, tzinfo=UTC)
        session.commit()
    evidence = client.post(EVIDENCE, headers=HEADERS, content=pdf("perfil QA")).json()["id"]
    entries = [
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
    doc = upload(client, 1, "Pliego QA", pdf("QA shortlist")).json()
    root = f"{api(1)}/{doc['id']}"
    assert client.post(f"{root}/review", headers=ANALYST).status_code == 200
    assert client.post(f"{root}/extraction", headers=ANALYST).status_code == 202
    assert run_one(
        create_session_factory(engine),
        settings,
        lambda *_: Result(
            status="listo",
            fragments=[
                Fragment(
                    text=chr(10).join(("Objeto: Consultoría.", "Plazo: 90 días.", FIRST, SECOND)),
                    locator=Locator(page=1),
                )
            ],
        ),
    )
    comparison = client.post(comparison_path(1), headers=ANALYST).json()
    margin_path = "/api/v1/opportunities/1/margin"
    assert client.post(margin_path, headers=ANALYST, json=scenario()).status_code == 201
    pending = scenario("100", None, name="Pendiente QA")
    pending["costs"]["hiring"] = assumed(None, None)
    assert client.post(margin_path, headers=ANALYST, json=pending).status_code == 201
    saved = save(client, 0, [1, 2]).json()
    response = client.get(f"{ROOT}/comparison", headers=ANALYST)
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    assert saved["revision"] == response.json()["revision"]
    a, b = response.json()["columns"]
    assert a["reception_at"].startswith("2026-12-10")
    assert a["published_budget"]["amount"] == "800.00"
    assert a["deadlines"][0]["document_id"] == doc["id"]
    assert a["gaps"]["revision"] == comparison["revision"] and a["gaps"]["items"]
    assert a["personnel"]["roles"][0]["gaps"] == [
        {
            "start": "2026-12-11",
            "end": "2026-12-20",
            "shortfall_percent": "30",
        }
    ]
    by_name = {margin["name"]: margin for margin in a["margins"]}
    assert by_name["Base sintética"]["margin_percent"] == "30.00"
    assert by_name["Pendiente QA"]["missing_amounts"] == ["hiring"]
    assert b["published_budget"] is None and b["gaps"]["status"] == "sin_generar"
    assert b["personnel"]["availability_pending"] and not b["margins"]
    assert client.get(comparison_path(2), headers=ANALYST).json()["status"] == "sin_generar"
    upload(client, 1, "Adenda QA", pdf("cambio shortlist"), kind="adenda")
    changed = client.get(f"{ROOT}/comparison", headers=ANALYST).json()["columns"][0]
    assert changed["gaps"]["status"] == "invalidado" and not changed["gaps"]["items"]
    assert all(
        m["status"] == "desactualizado" and m["margin_percent"] is None for m in changed["margins"]
    )
