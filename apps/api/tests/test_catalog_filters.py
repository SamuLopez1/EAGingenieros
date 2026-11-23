"""Resultados conocidos sobre SQL persistente; autenticación sintética aislada."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.auth import AuthServices, Membership, Role
from app.config import Settings
from app.db.filter_models import SavedOpportunityFilter
from app.db.models import Base, Opportunity, SyncCursor, SyncRun
from app.db.repository import SqlOpportunityRepository
from app.main import create_app
from tests.test_sync_repository import make_record

EAG = UUID(int=1)


class Validator:
    def subject_from_token(self, access_token: str) -> UUID:
        assert access_token == "synthetic"
        return UUID(int=32)


class Memberships:
    def __init__(self, role: Role, organization: UUID) -> None:
        self.membership = Membership(organization, role)

    def resolve(self, subject_id: UUID, access_token: str) -> Membership:
        assert subject_id == UUID(int=32) and access_token == "synthetic"
        return self.membership


HEADERS = {"Authorization": "Bearer synthetic"}


@pytest.fixture
def database(tmp_path: Path) -> str:
    url = f"sqlite+pysqlite:///{(tmp_path / 'catalog.sqlite').as_posix()}"
    engine = create_engine(url)
    Base.metadata.create_all(
        engine,
        tables=[
            Opportunity.__table__,
            SyncRun.__table__,
            SyncCursor.__table__,
            SavedOpportunityFilter.__table__,
        ],
    )
    with Session(engine) as session:
        records = [
            replace(
                make_record(f"SYNTH-{index}", title=f"Puente {index}"),
                entity="Entidad Norte" if index < 4 else "Entidad Sur",
                reference=f"REF-{index}",
                modality="Concurso" if index != 3 else "Directa",
                status="Publicado" if index != 2 else "Adjudicado",
                published_at=stamp,
            )
            for index, stamp in enumerate(
                [
                    datetime(2026, 9, 1, tzinfo=UTC),
                    datetime(2026, 9, 2, 23, 59, 59, 999999, UTC),
                    datetime(2026, 9, 3, tzinfo=UTC),
                    datetime(2026, 9, 1, tzinfo=UTC),
                    None,
                ]
            )
        ]
        records.append(make_record("literal", title="100%_ puente"))
        SqlOpportunityRepository(session).upsert_many(records)
        session.add(
            SyncRun(
                dataset="p6dx-8zbt", trigger="manual", outcome="failed", error_kind="quota_exceeded"
            )
        )
        session.commit()
    engine.dispose()
    return url


def http(
    url: str, role: Role = Role.ANALYST, organization: UUID = EAG, *, stale_after_hours: int = 24
) -> TestClient:
    auth = AuthServices(
        validator=Validator(),  # type: ignore[arg-type]
        memberships=Memberships(role, organization),
    )
    return TestClient(
        create_app(
            Settings(
                _env_file=None,
                database_url=SecretStr(url),
                catalog_stale_after_hours=stale_after_hours,
            ),
            auth_services=auth,
        )
    )


def test_combined_filters_apply_before_count_and_pagination(database: str) -> None:
    with http(database) as client:
        params = dict(
            q="entidad norte",
            status="Publicado",
            modality="Concurso",
            published_from="2026-09-01",
            published_to="2026-09-02",
            sort="published_asc",
            limit=1,
        )
        first = client.get("/api/v1/opportunities", params=params, headers=HEADERS)
        assert first.status_code == 200
        body = first.json()
        assert body["catalog_stale_after_hours"] == 24
        assert body["total"] == 2
        assert [r["source_id"] for r in body["items"]] == ["SYNTH-0"]
        second = client.get(
            "/api/v1/opportunities", params={**params, "offset": 1}, headers=HEADERS
        ).json()
        assert second["total"] == 2
        assert [r["source_id"] for r in second["items"]] == ["SYNTH-1"]
        assert body["catalog_synced_at"] and body["latest_sync_outcome"] == "failed"
        detail = client.get(f"/api/v1/opportunities/{body['items'][0]['id']}", headers=HEADERS)
        assert detail.json()["source_id"] == "SYNTH-0"
        assert detail.json()["source_dataset"] == "p6dx-8zbt"
        assert detail.json()["official_url"].startswith("https://")


def test_freshness_configuration_and_execution_date_are_exposed_separately(database: str) -> None:
    engine = create_engine(database)
    with Session(engine) as session:
        session.add(
            SyncRun(
                dataset="p6dx-8zbt",
                outcome="completed",
                finished_at=datetime(2026, 10, 15, 2, 30, tzinfo=UTC),
            )
        )
        session.commit()
    engine.dispose()
    with http(database, stale_after_hours=48) as client:
        body = client.get("/api/v1/opportunities", headers=HEADERS).json()
        assert body["catalog_stale_after_hours"] == 48
        assert body["latest_sync_outcome"] == "completed"
        assert body["latest_sync_finished_at"].startswith("2026-10-15T02:30:00")
        assert body["catalog_synced_at"] != body["latest_sync_finished_at"]


@pytest.mark.parametrize("hours", [0, -1, 8761])
def test_invalid_freshness_configuration(hours: int) -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(_env_file=None, catalog_stale_after_hours=hours)


@pytest.mark.parametrize(
    ("q", "ids"),
    [
        ("REF-4", ["SYNTH-4"]),
        ("Puente 3", ["SYNTH-3"]),
        ("Entidad Sur", ["SYNTH-4"]),
        ("%_", ["literal"]),
        ("' OR 1=1 --", []),
    ],
)
def test_search_fields_and_literal_sql_characters(database: str, q: str, ids: list[str]) -> None:
    with http(database) as client:
        body = client.get("/api/v1/opportunities", params={"q": q}, headers=HEADERS).json()
        assert [r["source_id"] for r in body["items"]] == ids


def test_date_boundaries_unknown_dates_ties_and_global_options(database: str) -> None:
    with http(database) as client:
        params = {
            "published_from": "2026-09-01",
            "published_to": "2026-09-01",
            "sort": "published_asc",
            "limit": 1,
        }
        one = client.get("/api/v1/opportunities", params=params, headers=HEADERS).json()
        two = client.get(
            "/api/v1/opportunities", params={**params, "offset": 1}, headers=HEADERS
        ).json()
        # La fixture literal también se publicó este día: el total incluye las tres.
        assert one["total"] == two["total"] == 3
        third = client.get(
            "/api/v1/opportunities", params={**params, "offset": 2}, headers=HEADERS
        ).json()
        assert third["items"][0]["source_id"] == "literal"
        assert [one["items"][0]["source_id"], two["items"][0]["source_id"]] == [
            "SYNTH-0",
            "SYNTH-3",
        ]
        unknown = client.get(
            "/api/v1/opportunities", params={"sort": "published_asc"}, headers=HEADERS
        ).json()["items"][-1]
        assert unknown["source_id"] == "SYNTH-4" and unknown["published_at"] is None
        opts = client.get("/api/v1/opportunity-options", headers=HEADERS).json()
        assert opts["statuses"] == ["Adjudicado", "Publicado"]
        assert "Directa" in opts["modalities"]


@pytest.mark.parametrize(
    "params",
    [
        {"sort": "title; DROP TABLE opportunities"},
        {"limit": 0},
        {"limit": 201},
        {"offset": -1},
        {"published_from": "invalid"},
        {"published_to": "9999-12-31"},
        {"published_from": "2026-09-03", "published_to": "2026-09-01"},
        {"q": "x" * 201},
        {"where": "1=1"},
    ],
)
def test_invalid_queries_are_rejected(database: str, params: dict[str, object]) -> None:
    with http(database) as client:
        assert (
            client.get("/api/v1/opportunities", params=params, headers=HEADERS).status_code == 422
        )


def test_shared_filters_persist_and_enforce_role_and_organization(database: str) -> None:
    body = {"name": "Puentes publicados", "criteria": {"q": "puente", "status": "Publicado"}}
    with http(database, Role.ADMINISTRATOR) as admin:
        response = admin.post("/api/v1/opportunity-filters", json=body, headers=HEADERS)
        assert response.status_code == 201
        filter_id = response.json()["id"]
        assert (
            admin.post("/api/v1/opportunity-filters", json=body, headers=HEADERS).status_code == 409
        )
    with http(database) as analyst:
        assert (
            analyst.get("/api/v1/opportunity-filters", headers=HEADERS).json()[0]["id"] == filter_id
        )
        for method, path in (("POST", ""), ("PUT", f"/{filter_id}"), ("DELETE", f"/{filter_id}")):
            assert (
                analyst.request(
                    method, f"/api/v1/opportunity-filters{path}", json=body, headers=HEADERS
                ).status_code
                == 403
            )
        assert analyst.get("/api/v1/opportunity-filters").status_code == 401
    with http(database, Role.ADMINISTRATOR, UUID(int=3)) as outsider:
        assert outsider.get("/api/v1/opportunity-filters", headers=HEADERS).status_code == 403
        assert (
            outsider.put(
                f"/api/v1/opportunity-filters/{filter_id}", json=body, headers=HEADERS
            ).status_code
            == 403
        )
    with http(database, Role.ADMINISTRATOR) as admin:
        body["name"] = "Nombre editado"
        assert (
            admin.put(
                f"/api/v1/opportunity-filters/{filter_id}", json=body, headers=HEADERS
            ).status_code
            == 200
        )
        forged = {**body, "organization_id": str(UUID(int=3))}
        assert (
            admin.post("/api/v1/opportunity-filters", json=forged, headers=HEADERS).status_code
            == 422
        )
        engine = create_engine(database)
        with Session(engine) as session:
            foreign = SavedOpportunityFilter(organization_id=UUID(int=3), name="Ajeno", criteria={})
            session.add(foreign)
            session.commit()
            foreign_id = foreign.id
        engine.dispose()
        assert (
            admin.delete(f"/api/v1/opportunity-filters/{foreign_id}", headers=HEADERS).status_code
            == 404
        )
        assert (
            admin.delete(f"/api/v1/opportunity-filters/{filter_id}", headers=HEADERS).status_code
            == 204
        )
        assert admin.get("/api/v1/opportunity-filters", headers=HEADERS).json() == []


def test_closing_location_and_validity_are_consistent_after_paging(database: str) -> None:
    now = datetime.now(UTC)
    records = (
        ("OPEN", "Publicado", now + timedelta(days=3), "Presentación de oferta"),
        ("CLOSED", "Adjudicado", None, None),
        ("EXPIRED", "Publicado", now - timedelta(days=2), "Presentación de oferta"),
        ("UNKNOWN", "Publicado", None, "Presentación de oferta"),
        ("DRAFT", "Publicado", now + timedelta(days=3), "Fase de borrador"),
    )
    engine = create_engine(database)
    with Session(engine) as session:
        SqlOpportunityRepository(session).upsert_many(
            replace(
                make_record(source_id, status=status),
                entity="Entidad Ubicación",
                modality="Concurso",
                raw={
                    "departamento_entidad": "Antioquia",
                    "ciudad_entidad": "Medellín",
                    "fase": phase,
                    "fecha_de_recepcion_de": deadline.isoformat() if deadline else None,
                },
            )
            for source_id, status, deadline, phase in records
        )
        session.commit()
    engine.dispose()

    with http(database) as client:
        filters = dict(entity="Ubicación", location="Antioquia", modality="Concurso")
        expected = {
            "abierto": {"OPEN"},
            "cerrado": {"CLOSED"},
            "vencido": {"EXPIRED"},
            "desconocida": {"UNKNOWN", "DRAFT"},
        }
        for validity, ids in expected.items():
            response = client.get(
                "/api/v1/opportunities", params={**filters, "validity": validity}, headers=HEADERS
            )
            assert response.status_code == 200, response.json()
            rows = response.json()["items"]
            assert {row["source_id"] for row in rows} == ids
            assert all(row["validity"] == validity for row in rows)
        end = (now + timedelta(days=3)).date().isoformat()
        response = client.get(
            "/api/v1/opportunities",
            params={**filters, "location": "Medellín", "closing_from": end, "closing_to": end,
                    "validity": "abierto", "limit": 1},
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1
        row = response.json()["items"][0]
        assert row["source_id"] == "OPEN"
        detail = client.get(f"/api/v1/opportunities/{row['id']}", headers=HEADERS)
        assert detail.json()["validity"] == "abierto"
        assert detail.json()["department"] == "Antioquia"
        assert detail.json()["reception_at"].startswith(end)
        assert client.get(
            "/api/v1/opportunities",
            params={"closing_from": "2026-02-27", "closing_to": "2026-02-26"},
            headers=HEADERS,
        ).status_code == 422
