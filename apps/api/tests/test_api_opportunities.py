"""Pruebas offline de las rutas de oportunidades y sincronización.

Usan el repositorio en memoria y un servicio de sincronización con respuestas
sintéticas. No hay red ni base de datos.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings
from app.db.repository import InMemoryOpportunityRepository
from app.db.sync_service import SyncService
from app.main import create_app
from app.secop.client import PROCESSES_DATASET, QuotaExceededError
from tests.test_sync_repository import make_record


class FakeClient:
    def __init__(self, pages: list[list[Any]] | Exception) -> None:
        self._pages = pages
        self.requests_made = 0

    def iter_records(
        self,
        *,
        filters: Mapping[str, str] | None = None,
        limit: int | None = None,
        start_offset: int = 0,
    ):
        del filters, start_offset
        if isinstance(self._pages, Exception):
            self.requests_made += 1
            raise self._pages
        emitted = 0
        for page in self._pages:
            self.requests_made += 1
            for record in page:
                if limit is not None and emitted >= limit:
                    return
                yield record
                emitted += 1


def client_with(
    pages: list[list[Any]] | Exception,
    repository: InMemoryOpportunityRepository | None = None,
) -> tuple[TestClient, InMemoryOpportunityRepository]:
    """Construye la aplicación con persistencia y cliente sintéticos."""

    app = create_app(Settings(environment="test", app_version="test"))
    repo = repository or InMemoryOpportunityRepository()
    app.state.opportunity_repository = repo
    app.state.sync_service_factory = lambda: SyncService(
        client=FakeClient(pages),  # type: ignore[arg-type]
        repository=repo,
    )
    return TestClient(app), repo


# --- Autenticación pendiente ----------------------------------------------


def test_routes_are_reachable_without_authentication_for_now() -> None:
    """Deja constancia de que las rutas de negocio aún no están protegidas.

    La autenticación existe en el PR #19 y no se ha fusionado. Esta prueba fija
    el estado actual a propósito: cuando la protección se integre, debe fallar y
    obligar a actualizarla, en lugar de que la ausencia de autorización pase
    inadvertida.
    """

    client, _ = client_with([[make_record("A")]])

    assert client.get("/api/v1/opportunities").status_code == 200


# --- Listado ---------------------------------------------------------------


def test_list_returns_empty_page_initially() -> None:
    client, _ = client_with([])

    response = client.get("/api/v1/opportunities")

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_returns_synced_opportunities() -> None:
    client, _ = client_with([[make_record("A"), make_record("B")]])
    client.post("/api/v1/sync-runs")

    body = client.get("/api/v1/opportunities").json()

    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert {item["source_id"] for item in body["items"]} == {"A", "B"}


def test_list_omits_the_raw_payload() -> None:
    """El listado no debe arrastrar la carga completa de la fuente."""

    client, _ = client_with([[make_record("A", raw={"id_del_proceso": "A", "enorme": "x" * 500})]])
    client.post("/api/v1/sync-runs")

    item = client.get("/api/v1/opportunities").json()["items"][0]

    assert "raw_payload" not in item
    assert "raw" not in item


def test_list_orders_unknown_dates_last() -> None:
    client, _ = client_with(
        [
            [
                make_record("sin-fecha", published_at=None),
                make_record("antigua", published_at=datetime(2026, 1, 1, tzinfo=UTC)),
                make_record("reciente", published_at=datetime(2026, 9, 1, tzinfo=UTC)),
            ]
        ]
    )
    client.post("/api/v1/sync-runs")

    items = client.get("/api/v1/opportunities").json()["items"]

    assert [i["source_id"] for i in items] == ["reciente", "antigua", "sin-fecha"]


def test_list_paginates() -> None:
    client, _ = client_with([[make_record(f"P-{i}") for i in range(10)]])
    client.post("/api/v1/sync-runs")

    body = client.get("/api/v1/opportunities", params={"limit": 4, "offset": 4}).json()

    assert body["total"] == 10
    assert len(body["items"]) == 4
    assert body["limit"] == 4
    assert body["offset"] == 4


def test_list_rejects_invalid_pagination() -> None:
    client, _ = client_with([])

    assert client.get("/api/v1/opportunities", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/opportunities", params={"limit": 500}).status_code == 422
    assert client.get("/api/v1/opportunities", params={"offset": -1}).status_code == 422


def test_list_preserves_traceability_fields() -> None:
    client, _ = client_with([[make_record("A")]])
    client.post("/api/v1/sync-runs")

    item = client.get("/api/v1/opportunities").json()["items"][0]

    assert item["source_dataset"] == PROCESSES_DATASET
    assert item["official_url"].startswith("https://")
    assert item["first_seen_at"]
    assert item["last_synced_at"]


# --- Detalle ---------------------------------------------------------------


def test_detail_returns_the_opportunity() -> None:
    client, repo = client_with([[make_record("A")]])
    client.post("/api/v1/sync-runs")
    stored = repo.get_by_source(PROCESSES_DATASET, "A")
    assert stored is not None

    response = client.get(f"/api/v1/opportunities/{stored.id}")

    assert response.status_code == 200
    assert response.json()["source_id"] == "A"


def test_detail_returns_404_for_unknown_id() -> None:
    client, _ = client_with([])

    response = client.get("/api/v1/opportunities/999999")

    assert response.status_code == 404


# --- Sincronización --------------------------------------------------------


def test_sync_endpoint_reports_created_records() -> None:
    client, _ = client_with([[make_record("A"), make_record("B")]])

    body = client.post("/api/v1/sync-runs").json()

    assert body["outcome"] == "completed"
    assert body["records_created"] == 2


def test_sync_endpoint_is_idempotent() -> None:
    client, _ = client_with([[make_record("A")]])

    client.post("/api/v1/sync-runs")
    body = client.post("/api/v1/sync-runs").json()

    assert body["records_created"] == 0
    assert body["records_unchanged"] == 1
    assert client.get("/api/v1/opportunities").json()["total"] == 1


def test_sync_endpoint_reports_provider_failure_without_http_error() -> None:
    """Un fallo del proveedor se reporta en el cuerpo, no como error HTTP.

    Devolver un 500 haría perder el detalle de qué ocurrió y si quedó algo
    sincronizado.
    """

    client, _ = client_with(QuotaExceededError("429"))

    response = client.post("/api/v1/sync-runs")

    assert response.status_code == 200
    assert response.json()["outcome"] == "failed"
    assert response.json()["error_kind"] == "quota_exceeded"


def test_sync_endpoint_accepts_a_limit() -> None:
    client, _ = client_with([[make_record(f"P-{i}") for i in range(20)]])

    body = client.post("/api/v1/sync-runs", params={"limit": 5}).json()

    assert body["records_seen"] == 5


def test_sync_endpoint_rejects_invalid_limit() -> None:
    client, _ = client_with([])

    assert client.post("/api/v1/sync-runs", params={"limit": 0}).status_code == 422


# --- Disponibilidad de la persistencia ------------------------------------


def test_routes_report_503_when_persistence_is_missing() -> None:
    """Sin persistencia configurada debe responder 503, no fallar sin más."""

    app = create_app(Settings(environment="test"))
    app.state.opportunity_repository = None
    app.state.sync_service_factory = None

    with TestClient(app) as client:
        assert client.get("/api/v1/opportunities").status_code == 503
        assert client.post("/api/v1/sync-runs").status_code == 503


def test_health_declares_the_persistence_mode() -> None:
    """El modo se declara para no confundir memoria con persistencia real."""

    app = create_app(Settings(environment="test"))

    with TestClient(app) as client:
        assert client.get("/health").json()["persistence"] == "memory"


def test_openapi_publishes_the_new_routes() -> None:
    app = create_app(Settings(environment="test"))

    with TestClient(app) as client:
        paths = client.get("/openapi.json").json()["paths"]

    assert "/api/v1/opportunities" in paths
    assert "/api/v1/opportunities/{opportunity_id}" in paths
    assert "/api/v1/sync-runs" in paths
