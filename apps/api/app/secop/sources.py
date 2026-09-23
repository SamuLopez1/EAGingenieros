"""Registro de las fuentes de contratación pública que el sistema consulta.

Origen de los nombres de campo
------------------------------
Los mapas de este módulo NO se dedujeron de la documentación ni se copiaron de
un ejemplo: se leyeron de los metadatos reales de cada conjunto, que Socrata
publica en ``https://www.datos.gov.co/api/views/<dataset>.json``. Comprobado el
2026-09-23:

- SECOP II ``p6dx-8zbt`` — 59 columnas. Coincide con lo documentado.
- SECOP I  ``f789-7hwg`` — 79 columnas. El documento del repositorio decía 78.

Los esquemas NO son equivalentes, y esa es la razón de que este registro exista.
Nombres distintos para el mismo concepto (``entidad`` frente a
``nombre_entidad``), y conceptos que **no** son el mismo aunque lo parezcan:

``precio_base`` (SECOP II) y ``cuantia_proceso`` (SECOP I) no miden lo mismo.
Fusionarlos en una sola columna «valor» produciría comparaciones incorrectas
sobre el precio de una licitación, así que cada fuente conserva su etiqueta y
el sistema nunca los presenta como equivalentes.

Sin este registro, ``normalise_record`` tenía los nombres de SECOP II escritos
dentro y toda fila de SECOP I se habría descartado por falta de identificador,
en silencio y sin error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Platform = Literal["SECOP_I", "SECOP_II"]

# Estado de cobertura que el sistema puede DECLARAR. Es un contrato con la
# interfaz: lo que no está sincronizado se declara como no sincronizado, en
# lugar de dejar creer que el listado es completo.
CoverageState = Literal[
    "sincronizada",  # se ingiere de forma continua
    "parcial",  # se ingiere, pero con límites conocidos
    "historica",  # solo se usa como contexto, no produce oportunidades
    "no_sincronizada",  # declarada y NO ingerida
]


@dataclass(frozen=True)
class FieldMap:
    """Nombres candidatos por rol, en orden de preferencia.

    Cada rol es una tupla porque los conjuntos han cambiado de forma entre
    versiones del esquema —``urlproceso`` pasó de cadena a objeto anidado— y
    porque una fila puede traer el campo completo o su variante truncada.
    """

    source_id: tuple[str, ...]
    reference: tuple[str, ...]
    title: tuple[str, ...]
    entity: tuple[str, ...]
    entity_nit: tuple[str, ...]
    status: tuple[str, ...]
    modality: tuple[str, ...]
    published_at: tuple[str, ...]
    last_updated_at: tuple[str, ...]
    official_url: tuple[str, ...]
    amount: tuple[str, ...]


@dataclass(frozen=True)
class Source:
    """Una fuente de datos oficial, con todo lo que la distingue de las demás."""

    dataset: str
    platform: Platform
    label: str
    short_label: str
    # Campo y sentido del orden de paginación. Debe ser estable y no tener
    # nulos abundantes: ordenar por un campo disperso sesga la muestra y hace
    # que la paginación repita u omita filas.
    order: str
    fields: FieldMap
    # Campos admitidos en $where. Un campo fuera de esta lista se rechaza en
    # lugar de enviarse a ciegas, porque el conjunto responde con error opaco.
    confirmed_fields: frozenset[str]
    coverage: CoverageState
    coverage_note: str
    # Etiqueta del valor económico. Nunca se presenta como equivalente entre
    # fuentes, porque no lo es.
    amount_label: str
    official_base_url: str

    @property
    def natural_key_prefix(self) -> str:
        return self.dataset


# --- SECOP II: procesos de contratación ------------------------------------
# Es la plataforma transaccional vigente. Sus referencias pueden repetirse
# entre entidades ('001-2026' aparece cientos de veces), así que la identidad
# de un registro es `id_del_proceso`, nunca la referencia.
SECOP_II = Source(
    dataset="p6dx-8zbt",
    platform="SECOP_II",
    label="SECOP II · Procesos de contratación",
    short_label="SECOP II",
    order="id_del_proceso DESC",
    fields=FieldMap(
        source_id=("id_del_proceso", "referencia_del_proceso"),
        reference=("referencia_del_proceso",),
        title=("nombre_del_procedimiento", "descripci_n_del_procedimiento"),
        entity=("entidad",),
        entity_nit=("nit_entidad",),
        status=("estado_del_procedimiento", "estado_resumen", "fase"),
        modality=("modalidad_de_contratacion",),
        published_at=("fecha_de_publicacion_del", "fecha_de_publicacion"),
        last_updated_at=("fecha_de_ultima_publicaci",),
        official_url=("urlproceso",),
        amount=("precio_base",),
    ),
    confirmed_fields=frozenset(
        {
            "id_del_proceso",
            "referencia_del_proceso",
            "nombre_del_procedimiento",
            "entidad",
            "nit_entidad",
            "estado_del_procedimiento",
            "estado_resumen",
            "fase",
            "modalidad_de_contratacion",
            "tipo_de_contrato",
            "fecha_de_publicacion_del",
            "fecha_de_ultima_publicaci",
            "fecha_de_recepcion_de",
            "fecha_de_apertura_de_respuesta",
            "precio_base",
            "departamento_entidad",
            "ciudad_entidad",
            "codigo_entidad",
            "codigo_pci",
            "adjudicado",
            "urlproceso",
        }
    ),
    coverage="sincronizada",
    coverage_note="Plataforma vigente. Es la fuente principal del listado.",
    amount_label="Precio base",
    official_base_url="https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index",
)

# --- SECOP I: procesos de compra pública -----------------------------------
# Plataforma anterior, todavía con publicación reciente. `uid` es el
# identificador propio del conjunto; `numero_de_proceso` es la referencia de la
# entidad y también se repite entre entidades.
SECOP_I = Source(
    dataset="f789-7hwg",
    platform="SECOP_I",
    label="SECOP I · Procesos de compra pública",
    short_label="SECOP I",
    order="uid DESC",
    fields=FieldMap(
        source_id=("uid", "numero_de_proceso"),
        reference=("numero_de_proceso",),
        title=("objeto_a_contratar", "detalle_del_objeto_a_contratar"),
        entity=("nombre_entidad",),
        entity_nit=("nit_de_la_entidad",),
        status=("estado_del_proceso",),
        modality=("modalidad_de_contratacion",),
        published_at=("fecha_de_cargue_en_el_secop",),
        last_updated_at=("ultima_actualizacion", "fecha_de_cargue_en_el_secop"),
        official_url=("ruta_proceso_en_secop_i",),
        # NO es equivalente a `precio_base` de SECOP II. Ver la nota del módulo.
        amount=("cuantia_proceso",),
    ),
    confirmed_fields=frozenset(
        {
            "uid",
            "numero_de_proceso",
            "numero_de_contrato",
            "nombre_entidad",
            "nit_de_la_entidad",
            "estado_del_proceso",
            "modalidad_de_contratacion",
            "tipo_de_contrato",
            "fecha_de_cargue_en_el_secop",
            "ultima_actualizacion",
            "anno_cargue_secop",
            "cuantia_proceso",
            "objeto_a_contratar",
            "nivel_entidad",
            "departamento_entidad",
            "municipio_entidad",
            "codigo_bpin",
            "ruta_proceso_en_secop_i",
            "pliegos_tipo",
            "sector_pliegos_tipo",
        }
    ),
    coverage="parcial",
    coverage_note=(
        "Se ingiere, pero el solapamiento con SECOP II no está establecido. "
        "Un proceso puede aparecer en ambas plataformas con referencias "
        "distintas; el sistema lo señala y no lo fusiona por su cuenta."
    ),
    amount_label="Cuantía del proceso",
    official_base_url="https://www.contratos.gov.co/consultas/detalleProceso.do",
)

# Orden deliberado: SECOP II primero porque es la fuente principal del listado.
SOURCES: tuple[Source, ...] = (SECOP_II, SECOP_I)

BY_DATASET: dict[str, Source] = {source.dataset: source for source in SOURCES}

BY_PLATFORM: dict[str, Source] = {source.platform: source for source in SOURCES}

# Fuente por defecto. Se elige SECOP II para que cualquier llamada que no
# especifique fuente conserve el comportamiento anterior a este registro.
DEFAULT_SOURCE = SECOP_II


def get_source(dataset: str) -> Source:
    """Devuelve la fuente del conjunto indicado.

    Falla en lugar de degradar: sincronizar un conjunto desconocido con el mapa
    de campos equivocado descartaría todas las filas sin dar error.
    """

    try:
        return BY_DATASET[dataset]
    except KeyError:
        known = ", ".join(sorted(BY_DATASET))
        raise UnknownSourceError(
            f"conjunto no registrado: {dataset!r}; conocidos: {known}"
        ) from None


def get_platform(platform: str) -> Source:
    try:
        return BY_PLATFORM[platform]
    except KeyError:
        known = ", ".join(sorted(BY_PLATFORM))
        raise UnknownSourceError(
            f"plataforma no registrada: {platform!r}; conocidas: {known}"
        ) from None


class UnknownSourceError(LookupError):
    """Se pidió una fuente que el sistema no tiene registrada."""


def primary_sources() -> tuple[Source, ...]:
    """Fuentes que producen oportunidades en el listado.

    Excluye las que solo aportan contexto histórico: una fuente con cobertura
    `historica` no debe aparecer como si estuviera sincronizada.
    """

    return tuple(s for s in SOURCES if s.coverage != "historica")


def coverage_summary() -> list[dict[str, str]]:
    """Cobertura declarada, para que la interfaz no afirme de más."""

    return [
        {
            "dataset": s.dataset,
            "platform": s.platform,
            "label": s.label,
            "short_label": s.short_label,
            "coverage": s.coverage,
            "note": s.coverage_note,
        }
        for s in SOURCES
    ]


# --- Identidad entre fuentes ------------------------------------------------
# Cautela deliberada. Medido el 2026-09-23 contra los dos conjuntos:
#
#   * `referencia_del_proceso` NO es única en SECOP II. El valor `001-2026`
#     aparece 1139 veces, y `017-2026` 405. Son referencias genéricas que cada
#     entidad reutiliza. Agrupar por referencia sola fusionaría miles de
#     procesos sin relación.
#
#   * Al exigir además el NIT de la entidad, el solapamiento entre SECOP I y
#     SECOP II de una muestra de 370 pares cayó a 0. Con la referencia sola
#     daba un 22,6 %, pero ese número estaba inflado por las colisiones: al
#     añadir el NIT desaparecieron todos, es decir, eran falsos positivos.
#
# Conclusión: NO existe una clave que permita fusionar automáticamente el
# mismo proceso entre las dos plataformas. Por eso `grouping_key` solo agrupa
# cuando coinciden NIT y referencia normalizada, el sistema nunca fusiona por
# su cuenta, y la interfaz presenta el grupo como «posible duplicado» para que
# lo confirme una persona. Fusionar en silencio sería afirmar una equivalencia
# que la medición no respalda.

_NON_ALNUM = re.compile(r"[^0-9A-Za-z]+")


def normalise_reference(value: str | None) -> str | None:
    """Referencia sin separadores ni caja, para poder compararla.

    «SA-SI-04-2026» y «sa si 04 2026» producen la misma forma.
    """

    if not value:
        return None
    cleaned = _NON_ALNUM.sub("", value).upper()
    return cleaned or None


def grouping_key(entity_nit: str | None, reference: str | None) -> str | None:
    """Clave para señalar posibles duplicados entre plataformas.

    Devuelve None cuando falta el NIT o la referencia. Es intencionado: sin
    ambos, cualquier agrupación sería una conjetura, y una conjetura
    presentada como duplicado hace que el analista descarte una oportunidad
    que sí era distinta.
    """

    ref = normalise_reference(reference)
    if not entity_nit or not ref:
        return None
    return f"{entity_nit}:{ref}"
