"""Cliente del conjunto de datos públicos de procesos de SECOP II.

Alcance deliberadamente acotado a lo que el spike MVP-02 verificó con datos
reales: el recurso `p6dx-8zbt` (procesos de contratación) responde, admite
paginación y acepta filtros sobre campos presentes en su esquema.

NO se implementa aquí la obtención automática de documentos desde `dmgg-8hin`:
el spike no confirmó la relación entre ambos conjuntos y su esquema apunta a
documentos de contratos, no a pliegos de oportunidades abiertas. La carga
manual de documentos complementarios es el camino previsto (issue MVP-07).

Este módulo no guarda nada por sí mismo: entrega registros normalizados y deja
la persistencia al repositorio correspondiente.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

import httpx

if TYPE_CHECKING:
    from app.secop.daily import DailyWindow

# Host oficial. Cualquier URL fuera de este host se rechaza.
SOCRATA_HOST = "www.datos.gov.co"
SOCRATA_ROOT = f"https://{SOCRATA_HOST}"
PROCESSES_DATASET = "p6dx-8zbt"
LAST_PUBLICATION_FIELD = "fecha_de_ultima_publicaci"
RECEPTION_FIELD = "fecha_de_recepcion_de"

# Un nombre de campo solo puede ser un identificador: nunca se interpola texto
# libre en el parámetro $where, para no construir consultas inyectables.
SAFE_FIELD_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Orden por defecto. Verificado con datos reales: ordenar por
# `fecha_de_publicacion_del DESC` hace que Socrata devuelva primero las filas
# con ese campo nulo, que en este conjunto son numerosas. Ordenar por el
# identificador evita ese sesgo y mantiene un recorrido paginado estable
# (un orden inestable puede repetir u omitir filas entre páginas).
DEFAULT_ORDER = "id_del_proceso DESC"

# Campos que el spike confirmó en el esquema real del conjunto de procesos.
CONFIRMED_FIELDS = frozenset(
    {
        "id_del_proceso",
        "referencia_del_proceso",
        "nombre_del_procedimiento",
        "entidad",
        "estado_del_procedimiento",
        "modalidad_de_contratacion",
        "fecha_de_publicacion_del",
        LAST_PUBLICATION_FIELD,
        RECEPTION_FIELD,
        "urlproceso",
    }
)


class SecopError(RuntimeError):
    """Base de los fallos del cliente, presentables sin filtrar detalles internos."""


class InvalidFilterError(SecopError):
    """El filtro pedido no cumple la política de campos permitidos."""


class QuotaExceededError(SecopError):
    """El proveedor respondió 429 o la cuota configurada se agotó."""


class UpstreamUnavailableError(SecopError):
    """El proveedor falló de forma transitoria (timeout, 5xx, red)."""


class ResponseShapeError(SecopError):
    """La respuesta no tiene la forma esperada."""


@dataclass(frozen=True)
class OpportunityRecord:
    """Registro normalizado de una oportunidad, con su trazabilidad de origen."""

    source_id: str
    source_dataset: str
    reference: str | None
    title: str | None
    entity: str | None
    status: str | None
    modality: str | None
    published_at: datetime | None
    last_updated_at: datetime | None
    official_url: str | None
    fetched_at: datetime
    raw: Mapping[str, Any] = field(repr=False)

    @property
    def natural_key(self) -> str:
        """Clave estable para sincronización idempotente."""

        return f"{self.source_dataset}:{self.source_id}"


def parse_timestamp(value: object) -> datetime | None:
    """Interpreta las marcas de tiempo del conjunto, o devuelve None.

    Un valor ausente o inválido se representa como desconocido, nunca como
    cero ni como la fecha actual: en este dominio, "no sé" y "cero" son cosas
    distintas y confundirlas produce comparaciones incorrectas.
    """

    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    # Socrata entrega habitualmente ISO 8601; se tolera el sufijo Z.
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _first_str(raw: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _url_from(value: object) -> str | None:
    """Extrae la URL de un campo que la fuente entrega de varias formas.

    Verificado contra datos reales: `urlproceso` es un objeto anidado
    (`{"url": "https://..."}`), no una cadena. Se toleran también cadena
    directa y listas de objetos, porque el conjunto ha cambiado de forma
    entre versiones del esquema.
    """

    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, Mapping):
        # Se prueban las claves habituales antes de rendirse.
        for key in ("url", "URL", "Url"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            found = _url_from(item)
            if found:
                return found
    return None


def normalise_record(raw: Mapping[str, Any], *, fetched_at: datetime) -> OpportunityRecord | None:
    """Convierte una fila cruda en un registro normalizado.

    Devuelve None cuando falta el identificador de origen: sin él no hay
    sincronización idempotente posible y el registro no debe persistirse
    como si fuera válido.
    """

    # La referencia es otro identificador y puede cambiar. Sustituir con ella
    # un id_del_proceso ausente rompería la clave natural entre ejecuciones.
    source_id = _first_str(raw, "id_del_proceso")
    if source_id is None:
        return None

    return OpportunityRecord(
        source_id=source_id,
        source_dataset=PROCESSES_DATASET,
        reference=_first_str(raw, "referencia_del_proceso"),
        title=_first_str(raw, "nombre_del_procedimiento"),
        entity=_first_str(raw, "entidad"),
        status=_first_str(raw, "estado_del_procedimiento"),
        modality=_first_str(raw, "modalidad_de_contratacion"),
        published_at=parse_timestamp(raw.get("fecha_de_publicacion_del")),
        last_updated_at=parse_timestamp(raw.get(LAST_PUBLICATION_FIELD)),
        official_url=_url_from(raw.get("urlproceso")),
        fetched_at=fetched_at,
        raw=dict(raw),
    )


@dataclass(frozen=True)
class SyncPage:
    """Una página de resultados junto con el estado de avance de la consulta."""

    records: tuple[OpportunityRecord, ...]
    offset: int
    page_size: int
    # Filas que devolvió la fuente antes de normalizar. Determina si hay más
    # páginas, porque una fila descartada no debe interpretarse como final.
    rows_received: int = 0
    # Posición posterior a cada registro válido dentro de la página cruda.
    record_offsets: tuple[int, ...] = ()

    @property
    def next_offset(self) -> int:
        return self.offset + self.rows_received

    @property
    def is_full_page(self) -> bool:
        return self.rows_received >= self.page_size


class HttpClient(Protocol):
    def get(self, url: str, *, params: Mapping[str, Any], timeout: float) -> httpx.Response: ...


class HttpxClient:
    """Cliente HTTP real. Se inyecta para poder probar sin red."""

    def __init__(self, *, app_token: str | None = None) -> None:
        headers = {"Accept": "application/json"}
        if app_token:
            # El token solo viaja en la cabecera; nunca se registra ni se
            # incluye en la URL, donde quedaría en logs de proxy.
            headers["X-App-Token"] = app_token
        self._client = httpx.Client(headers=headers, follow_redirects=False)

    def get(self, url: str, *, params: Mapping[str, Any], timeout: float) -> httpx.Response:
        return self._client.get(url, params=dict(params), timeout=timeout)

    def close(self) -> None:
        self._client.close()


class SecopClient:
    """Consulta paginada del conjunto de procesos, con cuota y reintentos."""

    def __init__(
        self,
        *,
        http: HttpClient,
        page_size: int = 100,
        timeout: float = 20.0,
        max_retries: int = 2,
        max_requests: int | None = None,
        dataset: str = PROCESSES_DATASET,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size debe ser al menos 1")
        if max_retries < 0:
            raise ValueError("max_retries no puede ser negativo")
        self._http = http
        self._page_size = page_size
        self._timeout = timeout
        self._max_retries = max_retries
        self._max_requests = max_requests
        self._dataset = dataset
        self._requests_made = 0
        self._next_offset = 0

    @property
    def requests_made(self) -> int:
        return self._requests_made

    @property
    def next_offset(self) -> int:
        """Primera fila de origen aún no procesada por esta iteración."""

        return self._next_offset

    def close(self) -> None:
        close_http = getattr(self._http, "close", None)
        if callable(close_http):
            close_http()

    def _endpoint(self) -> str:
        return f"{SOCRATA_ROOT}/resource/{self._dataset}.json"

    def build_where(
        self, filters: Mapping[str, str], *, updated_window: DailyWindow | None = None
    ) -> str | None:
        """Construye el parámetro $where validando cada nombre de campo.

        Solo se aceptan campos confirmados en el esquema y valores que se
        pueden citar sin ambigüedad. Un campo no confirmado se rechaza en vez
        de enviarse a ciegas, porque el conjunto responde con error opaco.
        """

        clauses: list[str] = []
        for name, value in filters.items():
            if not SAFE_FIELD_NAME.match(name):
                raise InvalidFilterError(f"nombre de campo inválido: {name!r}")
            if name not in CONFIRMED_FIELDS:
                raise InvalidFilterError(f"campo no confirmado en el esquema: {name!r}")
            escaped = value.replace("'", "''")
            clauses.append(f"{name}='{escaped}'")
        if updated_window is not None:
            # Se mantiene el supuesto UTC de parse_timestamp para la fecha
            # sin offset que la fuente admite en estas comparaciones.
            start, end = (
                bound.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="milliseconds")
                for bound in (updated_window.start, updated_window.end)
            )
            clauses.extend((
                f"{LAST_PUBLICATION_FIELD} >= '{start}'",
                f"{LAST_PUBLICATION_FIELD} < '{end}'",
            ))
        return " AND ".join(clauses) or None

    def fetch_page(
        self,
        *,
        offset: int = 0,
        filters: Mapping[str, str] | None = None,
        page_size: int | None = None,
        order: str | None = DEFAULT_ORDER,
        updated_window: DailyWindow | None = None,
    ) -> SyncPage:
        """Obtiene una página; el orden admite un campo permitido y ASC/DESC.

        Los reintentos solo cubren fallos transitorios.
        """

        size = page_size or self._page_size
        params: dict[str, Any] = {
            "$limit": size,
            "$offset": offset,
        }
        if order:
            parts = order.split()
            if (
                len(parts) not in (1, 2)
                or parts[0] not in CONFIRMED_FIELDS
                or (len(parts) == 2 and parts[1].upper() not in {"ASC", "DESC"})
            ):
                raise InvalidFilterError("orden no permitido: use un campo confirmado y ASC/DESC")
            params["$order"] = " ".join(parts)
        where = self.build_where(filters or {}, updated_window=updated_window)
        if where:
            params["$where"] = where

        last_error: Exception | None = None
        for _attempt in range(self._max_retries + 1):
            if self._max_requests is not None and self._requests_made >= self._max_requests:
                raise QuotaExceededError(
                    f"se alcanzó el límite de {self._max_requests} "
                    "consultas configurado"
                )
            try:
                self._requests_made += 1
                response = self._http.get(self._endpoint(), params=params, timeout=self._timeout)
            except httpx.TimeoutException as error:
                last_error = UpstreamUnavailableError(f"timeout tras {self._timeout}s")
                last_error.__cause__ = error
                continue
            except httpx.HTTPError as error:
                last_error = UpstreamUnavailableError("fallo de red al consultar SECOP")
                last_error.__cause__ = error
                continue

            if response.status_code == 429:
                # La cuota agotada no se reintenta en bucle: se informa para que
                # la sincronización quede reanudable desde este offset.
                raise QuotaExceededError("SECOP respondió 429 (cuota agotada)")
            if response.status_code >= 500:
                last_error = UpstreamUnavailableError(f"SECOP respondió {response.status_code}")
                continue
            if response.status_code >= 400:
                raise SecopError(f"SECOP rechazó la consulta con {response.status_code}")

            try:
                payload = response.json()
            except ValueError as error:
                raise ResponseShapeError("la respuesta no es JSON válido") from error
            if not isinstance(payload, list):
                raise ResponseShapeError("se esperaba una lista de registros")

            fetched_at = datetime.now(UTC)
            records = []
            record_offsets = []
            for index, row in enumerate(payload):
                if not isinstance(row, Mapping):
                    raise ResponseShapeError("se esperaba un objeto por registro")
                record = normalise_record(row, fetched_at=fetched_at)
                if record is not None:
                    records.append(record)
                    record_offsets.append(offset + index + 1)

            # El avance se calcula sobre las filas recibidas, no sobre los
            # registros normalizados: descartar una fila sin identificador no
            # debe hacer que la paginación retroceda ni que se corte antes.
            return SyncPage(
                records=tuple(records),
                offset=offset,
                page_size=size,
                rows_received=len(payload),
                record_offsets=tuple(record_offsets),
            )

        raise last_error or UpstreamUnavailableError("fallo desconocido al consultar SECOP")

    def iter_records(
        self,
        *,
        filters: Mapping[str, str] | None = None,
        limit: int | None = None,
        start_offset: int = 0,
        updated_window: DailyWindow | None = None,
    ) -> Iterator[OpportunityRecord]:
        """Itera páginas hasta agotar resultados, el límite o la cuota."""

        offset = start_offset
        self._next_offset = start_offset
        emitted = 0
        while True:
            remaining = None if limit is None else limit - emitted
            if remaining is not None and remaining <= 0:
                return
            size = self._page_size if remaining is None else min(self._page_size, remaining)
            page = self.fetch_page(
                offset=offset, filters=filters, page_size=size, updated_window=updated_window
            )
            for record, next_offset in zip(page.records, page.record_offsets, strict=True):
                # El límite se aplica al emitir, no solo al pedir: la página
                # puede traer más filas de las que faltan cuando la fuente
                # ignora $limit o devuelve un bloque mayor.
                if limit is not None and emitted >= limit:
                    return
                self._next_offset = next_offset
                yield record
                emitted += 1
            self._next_offset = page.next_offset
            # Una página incompleta significa que se agotaron los resultados.
            if not page.is_full_page:
                return
            offset = page.next_offset


def deduplicate(records: Sequence[OpportunityRecord]) -> list[OpportunityRecord]:
    """Elimina duplicados por clave natural conservando el último visto.

    La fuente puede devolver el mismo proceso en páginas consecutivas si se
    publica mientras se recorre; quedarse con el último evita retroceder a un
    estado anterior.
    """

    by_key: dict[str, OpportunityRecord] = {}
    for record in records:
        by_key[record.natural_key] = record
    return list(by_key.values())
