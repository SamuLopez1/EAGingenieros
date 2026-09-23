"""Pruebas offline del listado combinado de SECOP I y SECOP II.

Comprueban lo que el requisito multifuente exige de verdad: que el listado
diga de dónde viene cada fila, que los filtros funcionen sobre las dos
plataformas a la vez, que la cobertura se declare con datos y que un posible
duplicado se señale sin fusionarse.

Todo offline: repositorio en memoria y sin red.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.auth.principal import Principal, Role, get_current_principal
from app.config import Settings
from app.db.repository import InMemoryOpportunityRepository
from app.db.sync_service import SyncService
from app.main import create_app
from app.secop.sources import DEFAULT_SOURCE, SECOP_I, SECOP_II, get_source
from tests.test_sync_repository import make_record

ANALYST = Principal(
    subject_id=UUID("00000000-0000-0000-0000-000000000001"),
    organization_id=UUID("00000000-0000-0000-0000-000000000002"),
    role=Role.ANALYST,
    user_id=1,
)


class UnusedClient:
    """Cliente que no debe usarse: estas pruebas siembran el repositorio.

    Declara `source` como el cliente real, y la fábrica lo construye a partir
    del conjunto pedido, igual que la aplicación. Sin eso, la fábrica de prueba
    no podría fallar ante un conjunto desconocido y la ruta nunca ejercitaría
    su traducción a 400.
    """

    requests_made = 0

    def __init__(self, source=SECOP_II) -> None:
        self.source = source

    def iter_records(self, **_kwargs: object):
        return iter(())


def app_with_opportunities(*records) -> TestClient:
    app = create_app(Settings(environment="test", app_version="test"))
    repo = InMemoryOpportunityRepository()
    if records:
        repo.upsert_many(list(records))

    def sync_factory(dataset: str | None = None) -> SyncService:
        # Misma resolución que la aplicación: un conjunto no registrado falla
        # aquí, y la ruta lo traduce a 400.
        source = get_source(dataset) if dataset else DEFAULT_SOURCE
        return SyncService(client=UnusedClient(source), repository=repo)  # type: ignore[arg-type]

    app.state.opportunity_repository = repo
    app.state.sync_service_factory = sync_factory
    app.dependency_overrides[get_current_principal] = lambda: ANALYST
    return TestClient(app)


# --- Cobertura declarada ----------------------------------------------------


def test_sources_endpoint_declares_both_platforms() -> None:
    client = app_with_opportunities()

    body = client.get("/api/v1/sources").json()

    platforms = {source["platform"]: source for source in body["sources"]}
    assert set(platforms) == {"SECOP_I", "SECOP_II"}
    assert platforms["SECOP_II"]["coverage"] == "sincronizada"
    assert platforms["SECOP_I"]["coverage"] == "parcial"


def test_sources_endpoint_reports_real_counts_not_claims() -> None:
    client = app_with_opportunities(
        make_record("I-1", source=SECOP_I),
        make_record("I-2", source=SECOP_I),
        make_record("II-1", source=SECOP_II),
    )

    sources = client.get("/api/v1/sources").json()["sources"]
    counts = {s["platform"]: s["opportunity_count"] for s in sources}

    assert counts == {"SECOP_I": 2, "SECOP_II": 1}


def test_sources_endpoint_exposes_each_amount_label() -> None:
    """Los valores económicos no son comparables entre plataformas."""

    client = app_with_opportunities()

    sources = {s["platform"]: s for s in client.get("/api/v1/sources").json()["sources"]}

    assert sources["SECOP_I"]["amount_label"] == SECOP_I.amount_label
    assert sources["SECOP_II"]["amount_label"] == SECOP_II.amount_label
    assert sources["SECOP_I"]["amount_label"] != sources["SECOP_II"]["amount_label"]


# --- Listado combinado ------------------------------------------------------


def test_list_mixes_both_platforms_and_labels_each_row() -> None:
    """Cada fila declara su procedencia: es lo que permite mezclarlas."""

    client = app_with_opportunities(
        make_record("I-1", source=SECOP_I),
        make_record("II-1", source=SECOP_II),
    )

    items = client.get("/api/v1/opportunities").json()["items"]

    by_id = {item["source_id"]: item for item in items}
    assert by_id["I-1"]["platform"] == "SECOP_I"
    assert by_id["I-1"]["platform_label"] == "SECOP I"
    assert by_id["I-1"]["source_dataset"] == "f789-7hwg"
    assert by_id["II-1"]["platform"] == "SECOP_II"
    assert by_id["II-1"]["source_dataset"] == "p6dx-8zbt"


def test_list_exposes_the_amount_with_its_own_label() -> None:
    client = app_with_opportunities(
        make_record("I-1", source=SECOP_I, amount=98000000.0),
        make_record("II-1", source=SECOP_II, amount=1500000.5),
    )

    by_id = {i["source_id"]: i for i in client.get("/api/v1/opportunities").json()["items"]}

    assert by_id["I-1"]["amount"] == pytest.approx(98000000.0)
    assert by_id["I-1"]["amount_label"] == SECOP_I.amount_label
    assert by_id["II-1"]["amount"] == pytest.approx(1500000.5)
    assert by_id["II-1"]["amount_label"] == SECOP_II.amount_label


def test_missing_amount_stays_null_and_is_not_zero() -> None:
    """«No sé cuánto vale» no puede llegar a la interfaz como cero."""

    client = app_with_opportunities(make_record("I-1", source=SECOP_I, amount=None))

    item = client.get("/api/v1/opportunities").json()["items"][0]

    assert item["amount"] is None


# --- Filtros ----------------------------------------------------------------


def test_filter_by_platform() -> None:
    client = app_with_opportunities(
        make_record("I-1", source=SECOP_I),
        make_record("II-1", source=SECOP_II),
    )

    body = client.get("/api/v1/opportunities", params={"platform": "SECOP_I"}).json()

    assert body["total"] == 1
    assert body["items"][0]["source_id"] == "I-1"


def test_filter_by_source_dataset() -> None:
    client = app_with_opportunities(
        make_record("I-1", source=SECOP_I),
        make_record("II-1", source=SECOP_II),
    )

    body = client.get(
        "/api/v1/opportunities", params={"source": "f789-7hwg"}
    ).json()

    assert body["total"] == 1
    assert body["items"][0]["platform"] == "SECOP_I"


def test_filter_total_reflects_the_filter_not_the_whole_table() -> None:
    """`total` debe contar lo filtrado: si contara todo, la paginación mentiría."""

    client = app_with_opportunities(
        *[make_record(f"II-{i}", source=SECOP_II) for i in range(5)],
        *[make_record(f"I-{i}", source=SECOP_I) for i in range(3)],
    )

    body = client.get("/api/v1/opportunities", params={"platform": "SECOP_I"}).json()

    assert body["total"] == 3
    assert len(body["items"]) == 3


def test_filter_by_status() -> None:
    client = app_with_opportunities(
        make_record("A", status="Publicado"),
        make_record("B", status="Adjudicado"),
    )

    body = client.get("/api/v1/opportunities", params={"estado": "Adjudicado"}).json()

    assert [i["source_id"] for i in body["items"]] == ["B"]


def test_search_matches_reference_title_and_entity() -> None:
    client = app_with_opportunities(
        make_record("A", title="Interventoría de obra", reference="SA-009-2026"),
        make_record("B", title="Compra de equipos", entity="ALCALDIA DE TIMBIQUI"),
    )

    by_reference = client.get("/api/v1/opportunities", params={"q": "SA-009"}).json()
    by_title = client.get("/api/v1/opportunities", params={"q": "interventoría"}).json()
    by_entity = client.get("/api/v1/opportunities", params={"q": "timbiqui"}).json()

    assert [i["source_id"] for i in by_reference["items"]] == ["A"]
    assert [i["source_id"] for i in by_title["items"]] == ["A"]
    # La búsqueda no distingue mayúsculas: la caja que escriba el analista no
    # debe decidir si encuentra una entidad.
    assert [i["source_id"] for i in by_entity["items"]] == ["B"]


def test_filter_by_date_range() -> None:
    client = app_with_opportunities(
        make_record("vieja", published_at=datetime(2026, 1, 1, tzinfo=UTC)),
        make_record("nueva", published_at=datetime(2026, 9, 1, tzinfo=UTC)),
    )

    body = client.get(
        "/api/v1/opportunities", params={"desde": "2026-06-01T00:00:00Z"}
    ).json()

    assert [i["source_id"] for i in body["items"]] == ["nueva"]


def test_rows_without_a_date_are_excluded_by_a_date_filter() -> None:
    """Una fila sin fecha no puede satisfacer un filtro de fecha.

    Incluirla afirmaría que se publicó dentro del rango sin saberlo.
    """

    client = app_with_opportunities(
        make_record("sin-fecha", published_at=None),
        make_record("con-fecha", published_at=datetime(2026, 9, 1, tzinfo=UTC)),
    )

    body = client.get(
        "/api/v1/opportunities", params={"desde": "2026-01-01T00:00:00Z"}
    ).json()

    assert [i["source_id"] for i in body["items"]] == ["con-fecha"]


def test_inverted_date_range_is_rejected() -> None:
    client = app_with_opportunities()

    response = client.get(
        "/api/v1/opportunities",
        params={"desde": "2026-09-01T00:00:00Z", "hasta": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 400
    assert "invertido" in response.json()["detail"]


def test_unknown_source_filter_is_rejected_not_silently_empty() -> None:
    """«No hay resultados» y «pediste una fuente que no existe» son distintos."""

    client = app_with_opportunities(make_record("A"))

    response = client.get("/api/v1/opportunities", params={"source": "no-existe"})

    assert response.status_code == 400


def test_filters_combine() -> None:
    client = app_with_opportunities(
        make_record("I-1", source=SECOP_I, status="Publicado"),
        make_record("I-2", source=SECOP_I, status="Adjudicado"),
        make_record("II-1", source=SECOP_II, status="Publicado"),
    )

    body = client.get(
        "/api/v1/opportunities",
        params={"platform": "SECOP_I", "estado": "Publicado"},
    ).json()

    assert [i["source_id"] for i in body["items"]] == ["I-1"]


# --- Posibles duplicados ----------------------------------------------------


def test_possible_duplicate_is_flagged_but_rows_are_not_merged() -> None:
    """La señal se muestra; la decisión es humana.

    Medido: no existe una clave que garantice que el mismo proceso en SECOP I
    y en SECOP II es el mismo registro. Por eso el sistema señala y no fusiona.
    """

    client = app_with_opportunities(
        make_record(
            "I-1", source=SECOP_I, entity_nit="891500498", reference="SA-009-2026"
        ),
        make_record(
            "II-1", source=SECOP_II, entity_nit="891500498", reference="SA-009-2026"
        ),
    )

    items = client.get("/api/v1/opportunities").json()["items"]

    # Las dos filas siguen existiendo: no se colapsaron.
    assert len(items) == 2
    assert all(item["possible_duplicate"] for item in items)
    assert all(
        item["duplicate_platforms"] == ["SECOP_I", "SECOP_II"] for item in items
    )


def test_same_reference_in_different_entities_is_not_a_duplicate() -> None:
    """El caso real que obligó a exigir el NIT: `001-2026` lo reutilizan muchas
    entidades para procesos distintos."""

    client = app_with_opportunities(
        make_record("A", source=SECOP_I, entity_nit="891500498", reference="001-2026"),
        make_record("B", source=SECOP_II, entity_nit="800003253", reference="001-2026"),
    )

    items = client.get("/api/v1/opportunities").json()["items"]

    assert not any(item["possible_duplicate"] for item in items)


def test_row_without_nit_cannot_be_flagged_as_duplicate() -> None:
    """Sin NIT no hay agrupación posible; señalar sería una conjetura."""

    client = app_with_opportunities(
        make_record("A", source=SECOP_I, entity_nit=None, reference="SA-009-2026"),
        make_record("B", source=SECOP_II, entity_nit=None, reference="SA-009-2026"),
    )

    items = client.get("/api/v1/opportunities").json()["items"]

    assert not any(item["possible_duplicate"] for item in items)


def test_duplicate_flag_is_false_for_a_lone_row() -> None:
    client = app_with_opportunities(
        make_record("A", source=SECOP_II, entity_nit="891500498", reference="SA-1-2026")
    )

    item = client.get("/api/v1/opportunities").json()["items"][0]

    assert item["possible_duplicate"] is False
    assert item["duplicate_platforms"] == []


# --- Detalle ----------------------------------------------------------------


def test_detail_preserves_origin() -> None:
    client = app_with_opportunities(make_record("I-1", source=SECOP_I, amount=1000.0))
    repo = client.app.state.opportunity_repository  # type: ignore[attr-defined]
    stored = repo.get_by_source("f789-7hwg", "I-1")

    body = client.get(f"/api/v1/opportunities/{stored.id}").json()

    assert body["platform"] == "SECOP_I"
    assert body["source_dataset"] == "f789-7hwg"
    assert body["amount_label"] == SECOP_I.amount_label


# --- Sincronización por fuente ---------------------------------------------


def test_sync_rejects_an_unregistered_dataset() -> None:
    """Se rechaza en lugar de sincronizar con el mapa de campos equivocado."""

    client = app_with_opportunities()

    response = client.post("/api/v1/sync-runs", params={"dataset": "no-existe"})

    assert response.status_code == 400
