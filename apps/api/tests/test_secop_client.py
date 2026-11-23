"""Pruebas offline del cliente SECOP.

Usan un doble de HTTP con respuestas sintéticas. No realizan red y por tanto
no demuestran disponibilidad de SECOP II: eso solo lo prueba una ejecución
explícita contra el servicio real.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.secop.client import (
    CONFIRMED_FIELDS,
    InvalidFilterError,
    OpportunityRecord,
    QuotaExceededError,
    ResponseShapeError,
    SecopClient,
    UpstreamUnavailableError,
    deduplicate,
    normalise_record,
    parse_timestamp,
)


class FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeHttp:
    """Devuelve respuestas preparadas y registra las consultas recibidas."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: Mapping[str, Any], timeout: float) -> Any:
        self.calls.append({"url": url, "params": dict(params), "timeout": timeout})
        if not self._responses:
            raise AssertionError("el cliente hizo más consultas de las preparadas")
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def row(**overrides: Any) -> dict[str, Any]:
    base = {
        "id_del_proceso": "PROC-1",
        "referencia_del_proceso": "REF-1",
        "nombre_del_procedimiento": "Compra de equipos",
        "entidad": "EAG",
        "estado_del_procedimiento": "Publicado",
        "modalidad_de_contratacion": "Contratación directa",
        "fecha_de_publicacion_del": "2026-09-01T10:00:00.000",
        "fecha_de_ultima_publicaci": "2026-09-02T11:30:00.000",
        "urlproceso": "https://community.secop.gov.co/Public/Tendering/Process",
    }
    base.update(overrides)
    return base


def client_with(http: FakeHttp, **kwargs: Any) -> SecopClient:
    return SecopClient(http=http, **kwargs)


# --- Normalización ---------------------------------------------------------


def test_normalise_keeps_traceability_fields() -> None:
    fetched = datetime(2026, 9, 17, tzinfo=UTC)

    record = normalise_record(row(), fetched_at=fetched)

    assert record is not None
    assert record.source_id == "PROC-1"
    assert record.source_dataset == "p6dx-8zbt"
    assert record.official_url == "https://community.secop.gov.co/Public/Tendering/Process"
    assert record.fetched_at == fetched
    assert record.natural_key == "p6dx-8zbt:PROC-1"


def test_normalise_returns_none_without_identifier() -> None:
    """Sin identificador no hay sincronización idempotente posible."""

    record = normalise_record(
        row(id_del_proceso=None, referencia_del_proceso=None),
        fetched_at=datetime.now(UTC),
    )

    assert record is None


def test_reference_does_not_replace_missing_source_identifier() -> None:
    record = normalise_record(
        row(id_del_proceso=None, referencia_del_proceso="REF-1"),
        fetched_at=datetime.now(UTC),
    )

    assert record is None


def test_missing_date_is_unknown_not_zero() -> None:
    record = normalise_record(row(fecha_de_publicacion_del=None), fetched_at=datetime.now(UTC))

    assert record is not None
    assert record.published_at is None


def test_parse_timestamp_handles_zulu_and_invalid() -> None:
    assert parse_timestamp("2026-09-01T10:00:00Z") == datetime(2026, 9, 1, 10, 0, tzinfo=UTC)
    assert parse_timestamp("no es fecha") is None
    assert parse_timestamp(None) is None
    assert parse_timestamp("") is None


# --- Construcción de filtros ----------------------------------------------


def test_build_where_accepts_confirmed_field() -> None:
    client = client_with(FakeHttp([]))

    where = client.build_where({"modalidad_de_contratacion": "Contratación directa"})

    assert where == "modalidad_de_contratacion='Contratación directa'"


def test_build_where_rejects_unconfirmed_field() -> None:
    client = client_with(FakeHttp([]))

    with pytest.raises(InvalidFilterError):
        client.build_where({"campo_inventado": "x"})


def test_build_where_rejects_unsafe_field_name() -> None:
    """Un nombre de campo no puede inyectar sintaxis en $where."""

    client = client_with(FakeHttp([]))

    with pytest.raises(InvalidFilterError):
        client.build_where({"a=1 OR b": "x"})


def test_build_where_escapes_quotes_in_value() -> None:
    client = client_with(FakeHttp([]))

    where = client.build_where({"entidad": "O'Hara"})

    assert where == "entidad='O''Hara'"


def test_confirmed_fields_match_the_spike_schema() -> None:
    """Los campos permitidos deben ser los que el spike verificó realmente."""

    assert "modalidad_de_contratacion" in CONFIRMED_FIELDS
    assert "campo_inventado" not in CONFIRMED_FIELDS


# --- Paginación ------------------------------------------------------------


def test_fetch_page_requests_limit_offset_and_order() -> None:
    http = FakeHttp([FakeResponse([row()])])
    client = client_with(http, page_size=50)

    page = client.fetch_page(offset=100)

    assert page.records[0].source_id == "PROC-1"
    sent = http.calls[0]["params"]
    assert sent["$limit"] == 50
    assert sent["$offset"] == 100
    assert "$order" in sent
    assert "$where" not in sent


def test_fetch_page_includes_where_only_when_filtered() -> None:
    http = FakeHttp([FakeResponse([])])
    client = client_with(http)

    client.fetch_page(filters={"entidad": "EAG"})

    assert http.calls[0]["params"]["$where"] == "entidad='EAG'"


def test_fetch_page_uses_official_host_only() -> None:
    http = FakeHttp([FakeResponse([])])

    client_with(http).fetch_page()

    assert http.calls[0]["url"].startswith("https://www.datos.gov.co/")


def test_iter_records_stops_on_short_page() -> None:
    """Una página incompleta indica el final: no se pide otra."""

    http = FakeHttp([FakeResponse([row()])])
    client = client_with(http, page_size=2)

    records = list(client.iter_records())

    assert len(records) == 1
    assert len(http.calls) == 1


def test_iter_records_requests_next_page_when_page_is_full() -> None:
    """Una página llena obliga a continuar hasta agotar resultados."""

    http = FakeHttp(
        [FakeResponse([row(id_del_proceso="A"), row(id_del_proceso="B")]), FakeResponse([])]
    )
    client = client_with(http, page_size=2)

    records = list(client.iter_records())

    assert len(records) == 2
    assert len(http.calls) == 2
    assert http.calls[1]["params"]["$offset"] == 2


def test_a_discarded_row_does_not_end_pagination_early() -> None:
    """Una fila sin identificador no debe cortar la paginación."""

    page = [row(id_del_proceso=None, referencia_del_proceso=None), row(id_del_proceso="B")]
    http = FakeHttp([FakeResponse(page), FakeResponse([])])
    client = client_with(http, page_size=2)

    records = list(client.iter_records())

    assert [r.source_id for r in records] == ["B"]
    # La segunda consulta debe partir de las filas recibidas (2), no de los
    # registros normalizados (1).
    assert http.calls[1]["params"]["$offset"] == 2


def test_a_full_page_of_discarded_rows_does_not_end_pagination() -> None:
    invalid = row(id_del_proceso=None)
    http = FakeHttp([FakeResponse([invalid, invalid]), FakeResponse([row(id_del_proceso="B")])])
    client = client_with(http, page_size=2)

    records = list(client.iter_records())

    assert [record.source_id for record in records] == ["B"]
    assert http.calls[1]["params"]["$offset"] == 2
    assert client.next_offset == 3


def test_limit_keeps_offset_at_last_emitted_source_row() -> None:
    http = FakeHttp(
        [FakeResponse([row(id_del_proceso=None), row(id_del_proceso="B"), row(id_del_proceso="C")])]
    )
    client = client_with(http, page_size=3)

    assert [record.source_id for record in client.iter_records(limit=1)] == ["B"]
    assert client.next_offset == 2


def test_iter_records_respects_limit() -> None:
    rows = [row(id_del_proceso=f"P-{i}") for i in range(5)]
    http = FakeHttp([FakeResponse(rows)])
    client = client_with(http, page_size=5)

    records = list(client.iter_records(limit=3))

    assert len(records) == 3
    assert http.calls[0]["params"]["$limit"] == 3


def test_iter_records_resumes_from_offset() -> None:
    http = FakeHttp([FakeResponse([])])
    client = client_with(http, page_size=10)

    list(client.iter_records(start_offset=250))

    assert http.calls[0]["params"]["$offset"] == 250


# --- Fallos y cuota --------------------------------------------------------


def test_quota_error_is_not_retried_in_a_loop() -> None:
    """Un 429 debe informarse, no reintentarse indefinidamente."""

    http = FakeHttp([FakeResponse({}, status_code=429)])
    client = client_with(http, max_retries=3)

    with pytest.raises(QuotaExceededError):
        client.fetch_page()

    assert len(http.calls) == 1


def test_server_error_is_retried_then_reported() -> None:
    http = FakeHttp(
        [
            FakeResponse({}, status_code=503),
            FakeResponse({}, status_code=503),
            FakeResponse({}, status_code=503),
        ]
    )
    client = client_with(http, max_retries=2)

    with pytest.raises(UpstreamUnavailableError):
        client.fetch_page()

    assert len(http.calls) == 3


def test_server_error_recovers_on_retry() -> None:
    http = FakeHttp([FakeResponse({}, status_code=503), FakeResponse([row()])])
    client = client_with(http, max_retries=2)

    page = client.fetch_page()

    assert len(page.records) == 1


def test_timeout_is_reported_as_unavailable() -> None:
    http = FakeHttp([httpx.TimeoutException("timeout")] * 3)
    client = client_with(http, max_retries=2)

    with pytest.raises(UpstreamUnavailableError):
        client.fetch_page()


def test_client_error_is_not_retried() -> None:
    http = FakeHttp([FakeResponse({}, status_code=400)])
    client = client_with(http, max_retries=3)

    with pytest.raises(Exception) as excinfo:
        client.fetch_page()

    assert "400" in str(excinfo.value)
    assert len(http.calls) == 1


def test_max_requests_enforces_the_configured_quota() -> None:
    http = FakeHttp([FakeResponse([row()]), FakeResponse([row()])])
    client = client_with(http, page_size=1, max_requests=2)

    with pytest.raises(QuotaExceededError):
        list(client.iter_records())

    assert client.requests_made == 2


def test_invalid_json_is_reported_as_shape_error() -> None:
    http = FakeHttp([FakeResponse(ValueError("no json"))])

    with pytest.raises(ResponseShapeError):
        client_with(http).fetch_page()


def test_non_list_payload_is_rejected() -> None:
    http = FakeHttp([FakeResponse({"message": "error"})])

    with pytest.raises(ResponseShapeError):
        client_with(http).fetch_page()


def test_expired_quota_reports_requests_made() -> None:
    http = FakeHttp([])
    client = client_with(http, max_requests=0)

    with pytest.raises(QuotaExceededError):
        client.fetch_page()

    assert client.requests_made == 0


# --- Deduplicación ---------------------------------------------------------


def test_deduplicate_keeps_last_version_of_a_record() -> None:
    fetched = datetime(2026, 9, 17, tzinfo=UTC)
    first = normalise_record(row(estado_del_procedimiento="Publicado"), fetched_at=fetched)
    second = normalise_record(row(estado_del_procedimiento="Adjudicado"), fetched_at=fetched)
    assert first is not None and second is not None

    result = deduplicate([first, second])

    assert len(result) == 1
    assert result[0].status == "Adjudicado"


def test_deduplicate_keeps_distinct_records() -> None:
    fetched = datetime(2026, 9, 17, tzinfo=UTC)
    records = [
        normalise_record(row(id_del_proceso="A"), fetched_at=fetched),
        normalise_record(row(id_del_proceso="B"), fetched_at=fetched),
    ]
    present = [r for r in records if isinstance(r, OpportunityRecord)]

    assert len(deduplicate(present)) == 2


# --- Formas reales del conjunto verificado contra la API -------------------


def test_official_url_is_extracted_from_nested_object() -> None:
    """Verificado con datos reales: urlproceso es {"url": "..."}, no un str."""

    record = normalise_record(
        row(urlproceso={"url": "https://community.secop.gov.co/Public/Tendering/X"}),
        fetched_at=datetime.now(UTC),
    )

    assert record is not None
    assert record.official_url == "https://community.secop.gov.co/Public/Tendering/X"


def test_official_url_tolerates_plain_string() -> None:
    """El esquema ha cambiado entre versiones: se acepta también cadena."""

    record = normalise_record(
        row(urlproceso="https://community.secop.gov.co/directa"),
        fetched_at=datetime.now(UTC),
    )

    assert record is not None
    assert record.official_url == "https://community.secop.gov.co/directa"


def test_official_url_is_none_when_object_has_no_url() -> None:
    record = normalise_record(row(urlproceso={"otro": "x"}), fetched_at=datetime.now(UTC))

    assert record is not None
    assert record.official_url is None


def test_official_url_rejects_non_string_values() -> None:
    record = normalise_record(row(urlproceso=12345), fetched_at=datetime.now(UTC))

    assert record is not None
    assert record.official_url is None


def test_published_at_does_not_use_manifestation_of_interest_date() -> None:
    record = normalise_record(
        row(fecha_de_publicacion_del=None, fecha_de_publicacion="2026-09-01T10:00:00.000"),
        fetched_at=datetime.now(UTC),
    )

    assert record is not None
    assert record.published_at is None


def test_published_at_prefers_the_full_field_name() -> None:
    record = normalise_record(
        row(
            fecha_de_publicacion_del="2026-09-01T10:00:00.000",
            fecha_de_publicacion="2020-01-01T00:00:00.000",
        ),
        fetched_at=datetime.now(UTC),
    )

    assert record is not None
    assert record.published_at == datetime(2026, 9, 1, 10, 0, tzinfo=UTC)


def test_default_order_does_not_sort_by_a_sparse_date_field() -> None:
    """Hallazgo real: ordenar por fecha_de_publicacion_del devuelve filas sin fecha.

    Socrata coloca primero los nulos en un orden DESC sobre ese campo, y en
    este conjunto son abundantes. El orden por defecto debe evitarlo y ser
    estable para que la paginación no repita ni omita filas.
    """

    from app.secop.client import DEFAULT_ORDER

    assert "fecha_de_publicacion_del" not in DEFAULT_ORDER
    assert DEFAULT_ORDER == "id_del_proceso DESC"


def test_order_can_be_disabled_explicitly() -> None:
    http = FakeHttp([FakeResponse([])])
    client = client_with(http)

    client.fetch_page(order=None)

    assert "$order" not in http.calls[0]["params"]


@pytest.mark.parametrize(
    "order",
    ["fecha_de_publicacion_del DESC", "entidad ASC", "id_del_proceso"],
)
def test_explicit_order_is_forwarded(order: str) -> None:
    http = FakeHttp([FakeResponse([])])
    client = client_with(http)

    client.fetch_page(order=order)

    assert http.calls[0]["params"]["$order"] == order


@pytest.mark.parametrize(
    "order",
    [
        "campo_inventado DESC",
        "lower(entidad) ASC",
        "id_del_proceso DESC, entidad ASC",
        "id_del_proceso DESC; SELECT *",
        "id_del_proceso DESC -- comentario",
        "id_del_proceso INVALID",
        "   ",
    ],
)
def test_invalid_order_is_rejected_before_http(order: str) -> None:
    http = FakeHttp([FakeResponse([])])
    client = client_with(http)

    with pytest.raises(InvalidFilterError):
        client.fetch_page(order=order)

    assert http.calls == []
    assert client.requests_made == 0


def test_default_order_is_applied_when_not_specified() -> None:
    from app.secop.client import DEFAULT_ORDER

    http = FakeHttp([FakeResponse([])])

    client_with(http).fetch_page()

    assert http.calls[0]["params"]["$order"] == DEFAULT_ORDER
