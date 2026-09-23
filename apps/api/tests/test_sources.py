"""Pruebas offline del registro de fuentes y de la normalización multifuente.

Los nombres de campo que usan estas pruebas NO son inventados: se leyeron de los
metadatos reales de cada conjunto, publicados por Socrata en
``https://www.datos.gov.co/api/views/<dataset>.json``, y comprobados el
2026-09-23. SECOP I tiene 79 columnas y SECOP II 59, y no comparten los nombres
de los campos equivalentes.

No hay red: las respuestas son sintéticas. Que los conjuntos sigan existiendo y
respondan solo lo demuestra una ejecución explícita contra el servicio real.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from app.secop.client import (
    InvalidFilterError,
    SecopClient,
    coerce_amount,
    normalise_nit,
    normalise_record,
)
from app.secop.sources import (
    SECOP_I,
    SECOP_II,
    SOURCES,
    UnknownSourceError,
    coverage_summary,
    get_platform,
    get_source,
    grouping_key,
    normalise_reference,
)


class FakeHttp:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, *, params: Mapping[str, Any], timeout: float) -> Any:
        self.calls.append({"url": url, "params": dict(params)})

        class Response:
            status_code = 200

            @staticmethod
            def json() -> list[Any]:
                return []

        return Response()


# --- Registro ---------------------------------------------------------------


def test_registry_contains_both_platforms() -> None:
    assert {s.platform for s in SOURCES} == {"SECOP_I", "SECOP_II"}


def test_datasets_match_the_official_ones() -> None:
    assert SECOP_II.dataset == "p6dx-8zbt"
    assert SECOP_I.dataset == "f789-7hwg"


def test_unknown_dataset_fails_instead_of_defaulting() -> None:
    """Un conjunto desconocido no debe caer a la fuente por defecto.

    Sincronizarlo con el mapa de campos equivocado descartaría todas las filas
    sin producir ningún error, que es la peor forma de fallar.
    """

    with pytest.raises(UnknownSourceError):
        get_source("no-existe")


def test_source_is_reachable_by_platform_and_dataset() -> None:
    assert get_source("f789-7hwg") is SECOP_I
    assert get_platform("SECOP_I") is SECOP_I
    assert get_platform("SECOP_II") is SECOP_II


def test_coverage_is_declared_and_never_claims_completeness() -> None:
    summary = coverage_summary()
    by_platform = {row["platform"]: row for row in summary}

    assert by_platform["SECOP_II"]["coverage"] == "sincronizada"
    # SECOP I se declara parcial: el solapamiento con SECOP II no está
    # establecido, así que afirmar cobertura completa sería falso.
    assert by_platform["SECOP_I"]["coverage"] == "parcial"
    assert "solapamiento" in by_platform["SECOP_I"]["note"]


def test_amount_labels_differ_because_the_measures_differ() -> None:
    """`precio_base` y `cuantia_proceso` no miden lo mismo.

    Si compartieran etiqueta, la interfaz presentaría como equivalentes dos
    valores económicos que no lo son, y el analista compararía precios
    incomparables.
    """

    assert SECOP_II.amount_label != SECOP_I.amount_label
    assert SECOP_II.fields.amount == ("precio_base",)
    assert SECOP_I.fields.amount == ("cuantia_proceso",)


def test_orders_use_fields_that_exist_in_each_schema() -> None:
    assert SECOP_II.order.startswith("id_del_proceso")
    assert SECOP_I.order.startswith("uid")


# --- Normalización de SECOP II ---------------------------------------------


def row_secop_ii(**overrides: Any) -> dict[str, Any]:
    base = {
        "id_del_proceso": "PROC-1",
        "referencia_del_proceso": "SA-SI-04-2026",
        "nombre_del_procedimiento": "Compra de equipos",
        "entidad": "ALCALDIA DE TIMBIQUI",
        "nit_entidad": "891.500.498-1",
        "estado_del_procedimiento": "Publicado",
        "modalidad_de_contratacion": "Contratación directa",
        "fecha_de_publicacion_del": "2026-09-01T10:00:00.000",
        "fecha_de_ultima_publicaci": "2026-09-02T11:30:00.000",
        "precio_base": "1500000.50",
        "urlproceso": {"url": "https://community.secop.gov.co/x"},
    }
    base.update(overrides)
    return base


def row_secop_i(**overrides: Any) -> dict[str, Any]:
    base = {
        "uid": "UID-1",
        "numero_de_proceso": "SA 009-2026",
        "objeto_a_contratar": "Interventoría de obra",
        "nombre_entidad": "CAUCA - ALCALDÍA MUNICIPIO DE TIMBIQUI",
        "nit_de_la_entidad": "891500498",
        "estado_del_proceso": "Celebrado",
        "modalidad_de_contratacion": "Contratación Directa",
        "fecha_de_cargue_en_el_secop": "2026-08-15T00:00:00.000",
        "ultima_actualizacion": "2026-08-20T00:00:00.000",
        "cuantia_proceso": 98000000,
        "ruta_proceso_en_secop_i": "https://www.contratos.gov.co/detalle",
    }
    base.update(overrides)
    return base


def test_secop_ii_record_carries_platform_and_nit() -> None:
    record = normalise_record(row_secop_ii(), fetched_at=datetime.now(UTC))

    assert record is not None
    assert record.platform == "SECOP_II"
    assert record.source_dataset == "p6dx-8zbt"
    assert record.entity_nit == "8915004981"  # sin puntos ni guion
    assert record.amount == pytest.approx(1500000.50)
    assert record.reference == "SA-SI-04-2026"


# --- Normalización de SECOP I ----------------------------------------------


def test_secop_i_record_is_normalised_with_its_own_field_names() -> None:
    """Antes esta fila se descartaba en silencio.

    `normalise_record` buscaba `id_del_proceso`, que no existe en SECOP I, así
    que devolvía None y la fila se perdía sin error ni registro.
    """

    record = normalise_record(row_secop_i(), fetched_at=datetime.now(UTC), source=SECOP_I)

    assert record is not None
    assert record.source_id == "UID-1"
    assert record.source_dataset == "f789-7hwg"
    assert record.platform == "SECOP_I"
    assert record.title == "Interventoría de obra"
    assert record.entity == "CAUCA - ALCALDÍA MUNICIPIO DE TIMBIQUI"
    assert record.entity_nit == "891500498"
    assert record.status == "Celebrado"
    assert record.amount == pytest.approx(98000000.0)
    assert record.published_at == datetime(2026, 8, 15, tzinfo=UTC)
    assert record.official_url == "https://www.contratos.gov.co/detalle"


def test_secop_i_falls_back_to_the_process_number_without_uid() -> None:
    record = normalise_record(
        row_secop_i(uid=None), fetched_at=datetime.now(UTC), source=SECOP_I
    )

    assert record is not None
    assert record.source_id == "SA 009-2026"


def test_secop_ii_fields_are_not_read_from_a_secop_i_row() -> None:
    """Los esquemas no son equivalentes y no deben entremezclarse.

    Una fila de SECOP I normalizada con el mapa de SECOP II no encuentra
    identificador y se descarta, que es el comportamiento correcto: mejor
    descartar que inventar una correspondencia.
    """

    assert normalise_record(row_secop_i(), fetched_at=datetime.now(UTC)) is None


def test_the_same_process_in_both_platforms_keeps_separate_identities() -> None:
    """La identidad es (conjunto, id). El mismo proceso en dos plataformas son
    dos registros distintos, y el sistema no los colapsa por su cuenta."""

    fetched = datetime.now(UTC)
    one = normalise_record(row_secop_i(), fetched_at=fetched, source=SECOP_I)
    two = normalise_record(row_secop_ii(), fetched_at=fetched, source=SECOP_II)

    assert one is not None and two is not None
    assert one.natural_key != two.natural_key


# --- NIT y valores económicos ----------------------------------------------


def test_nit_is_reduced_to_digits() -> None:
    assert normalise_nit("891.500.498-1") == "8915004981"
    assert normalise_nit("891500498") == "891500498"
    assert normalise_nit(None) is None
    assert normalise_nit("") is None
    assert normalise_nit("sin-digitos") is None


def test_amount_absent_is_unknown_never_zero() -> None:
    """«No sé cuánto vale» y «vale cero» son cosas distintas."""

    assert coerce_amount(None) is None
    assert coerce_amount("") is None
    assert coerce_amount("no es un número") is None
    assert coerce_amount(0) == 0.0
    assert coerce_amount("0") == 0.0


def test_amount_accepts_numeric_and_formatted_values() -> None:
    assert coerce_amount(1500000) == pytest.approx(1500000.0)
    assert coerce_amount("1500000.50") == pytest.approx(1500000.50)
    # Formato colombiano: miles con punto y decimales con coma.
    assert coerce_amount("1.500.000,50") == pytest.approx(1500000.50)
    # Un booleano es un entero en Python y no debe colarse como importe.
    assert coerce_amount(True) is None


# --- Referencia y agrupación ------------------------------------------------


def test_reference_normalisation_ignores_case_and_separators() -> None:
    assert normalise_reference("SA-SI-04-2026") == "SASI042026"
    assert normalise_reference("sa si 04 2026") == "SASI042026"
    assert normalise_reference("SASIP No. 004 de 2026") == "SASIPNO004DE2026"
    assert normalise_reference(None) is None
    assert normalise_reference("---") is None


def test_grouping_requires_both_nit_and_reference() -> None:
    """Sin NIT, agrupar por referencia es peligroso.

    Medido: `referencia_del_proceso` no es única en SECOP II —`001-2026`
    aparece 1139 veces—, así que la referencia sola fusionaría procesos de
    entidades distintas.
    """

    assert grouping_key(None, "SA 009-2026") is None
    assert grouping_key("891500498", None) is None
    assert grouping_key("891500498", "---") is None


def test_grouping_uses_nit_and_normalised_reference() -> None:
    assert grouping_key("891500498", "SA-009-2026") == "891500498:SA0092026"
    assert grouping_key("891500498", "sa 009 2026") == grouping_key(
        "891500498", "SA-009-2026"
    )


def test_different_entities_with_the_same_reference_do_not_group() -> None:
    """El caso real que motivó exigir el NIT: `001-2026` lo usan muchas
    entidades para procesos distintos."""

    assert grouping_key("891500498", "001-2026") != grouping_key("800003253", "001-2026")


# --- Filtros por fuente -----------------------------------------------------


def test_filter_fields_are_validated_per_source() -> None:
    """`entidad` existe en SECOP II pero no en SECOP I."""

    ii = SecopClient(http=FakeHttp(), source=SECOP_II)
    i = SecopClient(http=FakeHttp(), source=SECOP_I)

    assert ii.build_where({"entidad": "EAG"}) == "entidad='EAG'"
    with pytest.raises(InvalidFilterError):
        i.build_where({"entidad": "EAG"})

    assert i.build_where({"nombre_entidad": "EAG"}) == "nombre_entidad='EAG'"
    with pytest.raises(InvalidFilterError):
        ii.build_where({"nombre_entidad": "EAG"})


def test_client_queries_the_dataset_of_its_source() -> None:
    http = FakeHttp()
    SecopClient(http=http, source=SECOP_I).fetch_page()

    assert "f789-7hwg" in http.calls[0]["url"]


def test_client_applies_the_order_of_its_source() -> None:
    http_i = FakeHttp()
    SecopClient(http=http_i, source=SECOP_I).fetch_page()
    assert http_i.calls[0]["params"]["$order"] == SECOP_I.order

    http_ii = FakeHttp()
    SecopClient(http=http_ii, source=SECOP_II).fetch_page()
    assert http_ii.calls[0]["params"]["$order"] == SECOP_II.order


def test_client_can_still_be_built_by_dataset_name() -> None:
    """Compatibilidad: pasar `dataset` resuelve la fuente en el registro."""

    client = SecopClient(http=FakeHttp(), dataset="f789-7hwg")

    assert client.source is SECOP_I


def test_client_rejects_an_unregistered_dataset() -> None:
    with pytest.raises(UnknownSourceError):
        SecopClient(http=FakeHttp(), dataset="no-existe")
