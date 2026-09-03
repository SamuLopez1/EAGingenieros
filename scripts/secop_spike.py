#!/usr/bin/env python3
"""Spike acotado para datos públicos de SECOP II en Socrata.

No construye una integración productiva. Solo consulta los recursos oficiales
indicados por la issue MVP-02, exporta metadatos públicos mínimos a output/ y,
si se solicita explícitamente, lee una muestra pequeña de documentos en memoria.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import socket
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


SOCRATA_HOST = "www.datos.gov.co"
SOCRATA_ROOT = f"https://{SOCRATA_HOST}"
PROCESSES_DATASET = "p6dx-8zbt"
DOCUMENTS_DATASET = "dmgg-8hin"
IDENTIFIER_CANDIDATES = (
    "id_del_proceso",
    "referencia_del_proceso",
    "codigo_del_proceso",
    "id_proceso",
)
MINIMUM_PROCESS_FIELDS = (
    "id_del_proceso",
    "referencia_del_proceso",
    "nombre_del_procedimiento",
    "entidad",
    "fecha_de_publicacion_del",
    "fecha_de_publicacion",
    "modalidad_de_contratacion",
)
SAFE_FIELD_NAME = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


class SpikeError(RuntimeError):
    """Base para fallos que deben presentarse de forma visible y segura."""


class UnsafeUrlError(SpikeError):
    """La URL o una redirección no cumple la política del spike."""


class ResponseSizeError(SpikeError):
    """La respuesta supera el límite configurado."""


class ResponseFormatError(SpikeError):
    """La respuesta no tiene el formato JSON esperado."""


@dataclass
class HttpStatusError(SpikeError):
    status: int
    retry_after: str | None = None

    def __str__(self) -> str:
        retry = f"; retry_after={self.retry_after}" if self.retry_after else ""
        return f"HTTP {self.status}{retry}"


@dataclass
class NetworkError(SpikeError):
    reason: str

    def __str__(self) -> str:
        return f"network error: {self.reason}"


class NoRedirect(HTTPRedirectHandler):
    """Expone redirecciones para validarlas antes de seguirlas."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _header(headers: Any, name: str) -> str | None:
    """Lee una cabecera de respuestas reales o dobles de prueba."""

    if headers is None:
        return None
    if hasattr(headers, "get"):
        return headers.get(name)
    return None


def validate_url(url: str, allowed_hosts: set[str]) -> None:
    """Permite solo HTTPS y hosts exactos aprobados para esta ejecución."""

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not host
        or host not in allowed_hosts
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise UnsafeUrlError("URL no permitida por esquema u host")


class HttpClient:
    """Cliente HTTP pequeño: timeout, redirección explícita y límite de bytes."""

    def __init__(self, timeout_seconds: float, app_token: str | None = None, opener: Any | None = None):
        self.timeout_seconds = timeout_seconds
        self.app_token = app_token
        self.opener = opener or build_opener(NoRedirect())

    def _request(self, url: str) -> Request:
        headers = {"Accept": "application/json, */*;q=0.1", "User-Agent": "eag-secop-spike/0.1"}
        if self.app_token:
            headers["X-App-Token"] = self.app_token
        return Request(url, headers=headers)

    def read_bytes(self, url: str, allowed_hosts: set[str], max_bytes: int) -> tuple[bytes, str | None]:
        """Lee una respuesta en memoria, sin guardar documentos en disco."""

        current_url = url
        for _ in range(4):
            validate_url(current_url, allowed_hosts)
            try:
                response = self.opener.open(self._request(current_url), timeout=self.timeout_seconds)
            except HTTPError as error:
                status = error.code
                headers = error.headers
                if 300 <= status < 400:
                    location = _header(headers, "Location")
                    if not location:
                        raise HttpStatusError(status, _header(headers, "Retry-After")) from error
                    current_url = urljoin(current_url, location)
                    continue
                raise HttpStatusError(status, _header(headers, "Retry-After")) from error
            except URLError as error:
                reason = error.reason
                if isinstance(reason, (TimeoutError, socket.timeout)):
                    raise NetworkError("timeout") from error
                raise NetworkError(type(reason).__name__) from error
            except (TimeoutError, socket.timeout) as error:
                raise NetworkError("timeout") from error

            try:
                status = getattr(response, "status", None)
                if status is None:
                    getcode = getattr(response, "getcode", None)
                    if not callable(getcode):
                        raise ResponseFormatError("respuesta HTTP sin código de estado")
                    status = getcode()
                if not isinstance(status, int):
                    raise ResponseFormatError("código de estado HTTP inválido")
                headers = getattr(response, "headers", None)
                if 300 <= status < 400:
                    location = _header(headers, "Location")
                    if not location:
                        raise HttpStatusError(status, _header(headers, "Retry-After"))
                    current_url = urljoin(current_url, location)
                    continue
                if status >= 400:
                    raise HttpStatusError(status, _header(headers, "Retry-After"))
                content_length = _header(headers, "Content-Length")
                if content_length:
                    try:
                        declared_size = int(content_length)
                    except (TypeError, ValueError) as error:
                        raise ResponseFormatError("Content-Length inválido") from error
                    if declared_size < 0:
                        raise ResponseFormatError("Content-Length inválido")
                    if declared_size > max_bytes:
                        raise ResponseSizeError("respuesta supera el límite configurado")
                body = response.read(max_bytes + 1)
                if len(body) > max_bytes:
                    raise ResponseSizeError("respuesta supera el límite configurado")
                return body, _header(headers, "Content-Type")
            finally:
                close = getattr(response, "close", None)
                if close:
                    close()
        raise UnsafeUrlError("demasiadas redirecciones")

    def get_json(self, url: str, allowed_hosts: set[str], max_bytes: int = 2_000_000) -> Any:
        body, _ = self.read_bytes(url, allowed_hosts, max_bytes)
        try:
            return json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ResponseFormatError("respuesta no es JSON UTF-8 válido") from error


def metadata_url(dataset_id: str) -> str:
    return f"{SOCRATA_ROOT}/api/views/{dataset_id}"


def resource_url(dataset_id: str, parameters: Mapping[str, str]) -> str:
    return f"{SOCRATA_ROOT}/resource/{dataset_id}.json?{urlencode(parameters)}"


def schema_columns(metadata: Mapping[str, Any]) -> list[dict[str, str]]:
    columns: list[dict[str, str]] = []
    for column in metadata.get("columns", []):
        field = column.get("fieldName")
        if isinstance(field, str) and SAFE_FIELD_NAME.fullmatch(field):
            columns.append(
                {
                    "field": field,
                    "name": str(column.get("name", "")),
                    "type": str(column.get("dataTypeName", "")),
                    "description": str(column.get("description", "")),
                }
            )
    return columns


def owner_summary(metadata: Mapping[str, Any]) -> dict[str, str | None]:
    owner = metadata.get("owner") if isinstance(metadata.get("owner"), Mapping) else {}
    return {
        "display_name": owner.get("displayName") if isinstance(owner.get("displayName"), str) else None,
        "id": owner.get("id") if isinstance(owner.get("id"), str) else None,
        "attribution": metadata.get("attribution") if isinstance(metadata.get("attribution"), str) else None,
    }


def parse_filters(raw_filters: Sequence[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for raw_filter in raw_filters:
        if "=" not in raw_filter:
            raise ValueError("cada filtro debe tener el formato campo=valor")
        field, value = raw_filter.split("=", 1)
        if not SAFE_FIELD_NAME.fullmatch(field) or not value:
            raise ValueError("filtro inválido")
        if field in filters:
            raise ValueError(f"filtro repetido: {field}")
        filters[field] = value
    return filters


def build_where(filters: Mapping[str, str], available_fields: set[str]) -> str | None:
    if not filters:
        return None
    unknown = sorted(set(filters) - available_fields)
    if unknown:
        raise ValueError(f"campos de filtro inexistentes: {', '.join(unknown)}")
    clauses = [f"{field} = '{value.replace("'", "''")}'" for field, value in sorted(filters.items())]
    return " AND ".join(clauses)


def record_key(record: Mapping[str, Any], identity_fields: Sequence[str]) -> str:
    values = [(field, record[field]) for field in identity_fields if record.get(field) not in (None, "")]
    if values:
        return json.dumps(values, sort_keys=True, ensure_ascii=True, default=str)
    return json.dumps(record, sort_keys=True, ensure_ascii=True, default=str)


def deduplicate_records(records: Iterable[Mapping[str, Any]], identity_fields: Sequence[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        key = record_key(record, identity_fields)
        if key not in seen:
            seen.add(key)
            result.append(dict(record))
    return result


def fetch_sample(
    client: HttpClient,
    dataset_id: str,
    filters: Mapping[str, str],
    available_fields: set[str],
    page_size: int,
    sample_limit: int,
    identity_fields: Sequence[str],
) -> list[dict[str, Any]]:
    """Obtiene páginas Socrata hasta el límite, sin sincronización masiva."""

    where = build_where(filters, available_fields)
    records: list[Mapping[str, Any]] = []
    offset = 0
    while len(records) < sample_limit:
        parameters = {"$limit": str(min(page_size, sample_limit - len(records))), "$offset": str(offset)}
        if where:
            parameters["$where"] = where
        page = client.get_json(resource_url(dataset_id, parameters), {SOCRATA_HOST})
        if not isinstance(page, list):
            raise ResponseFormatError("la API de recursos no devolvió una lista")
        records.extend(item for item in page if isinstance(item, Mapping))
        if len(page) < int(parameters["$limit"]):
            break
        offset += len(page)
    return deduplicate_records(records[:sample_limit], identity_fields)


def choose_identity_fields(available_fields: set[str]) -> list[str]:
    return [field for field in IDENTIFIER_CANDIDATES if field in available_fields]


def minimal_metadata(records: Sequence[Mapping[str, Any]], available_fields: set[str]) -> tuple[list[dict[str, Any]], list[str]]:
    fields = [field for field in MINIMUM_PROCESS_FIELDS if field in available_fields]
    if not fields:
        fields = choose_identity_fields(available_fields)[:1]
    return [{field: record.get(field) for field in fields if field in record} for record in records], fields


def candidate_document_urls(records: Sequence[Mapping[str, Any]]) -> list[str]:
    """Extrae URLs de valores Socrata de texto o de objetos URL."""

    candidates: list[str] = []
    for record in records:
        for value in record.values():
            if isinstance(value, str) and value.startswith(("https://", "http://")):
                candidates.append(value)
            if isinstance(value, Mapping):
                nested_url = value.get("url")
                if isinstance(nested_url, str) and nested_url.startswith(("https://", "http://")):
                    candidates.append(nested_url)
    return list(dict.fromkeys(candidates))


def relationship_observation(
    processes: Sequence[Mapping[str, Any]], documents: Sequence[Mapping[str, Any]], process_fields: set[str], document_fields: set[str]
) -> dict[str, Any]:
    shared_fields = sorted(process_fields & document_fields)
    overlap: dict[str, int] = {}
    for field in shared_fields:
        process_values = {str(row[field]) for row in processes if row.get(field) not in (None, "")}
        document_values = {str(row[field]) for row in documents if row.get(field) not in (None, "")}
        if process_values and document_values:
            overlap[field] = len(process_values & document_values)
    return {"shared_field_names": shared_fields, "exact_value_overlap_in_sample": overlap}


def probe_relationships(
    client: HttpClient,
    processes: Sequence[Mapping[str, Any]],
    process_fields: set[str],
    document_fields: set[str],
    page_size: int,
    relationship_limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Prueba pares de campos candidatos sin declarar una relación universal."""

    pairs = [
        (process_field, "proceso")
        for process_field in ("referencia_del_proceso", "id_del_proceso")
        if process_field in process_fields and "proceso" in document_fields
    ]
    probes: list[dict[str, Any]] = []
    matched_records: list[dict[str, Any]] = []
    for process_field, document_field in pairs:
        attempted = 0
        matched = 0
        for process in processes:
            value = process.get(process_field)
            if value in (None, ""):
                continue
            attempted += 1
            rows = fetch_sample(
                client,
                DOCUMENTS_DATASET,
                {document_field: str(value)},
                document_fields,
                page_size,
                1,
                choose_identity_fields(document_fields),
            )
            if rows:
                matched += len(rows)
                matched_records.extend(rows)
            if attempted >= relationship_limit:
                break
        probes.append(
            {
                "process_field": process_field,
                "document_field": document_field,
                "attempted_process_values": attempted,
                "matched_document_rows": matched,
            }
        )
    return probes, deduplicate_records(matched_records, choose_identity_fields(document_fields))


def probe_documents_to_processes(
    client: HttpClient,
    documents: Sequence[Mapping[str, Any]],
    process_fields: set[str],
    document_fields: set[str],
    page_size: int,
    relationship_limit: int,
) -> list[dict[str, Any]]:
    """Prueba la relación candidata en sentido inverso desde los documentos."""

    if "proceso" not in document_fields:
        return []
    probes: list[dict[str, Any]] = []
    for process_field in ("referencia_del_proceso", "id_del_proceso"):
        if process_field not in process_fields:
            continue
        attempted = 0
        matched = 0
        for document in documents:
            value = document.get("proceso")
            if value in (None, ""):
                continue
            attempted += 1
            rows = fetch_sample(
                client,
                PROCESSES_DATASET,
                {process_field: str(value)},
                process_fields,
                page_size,
                1,
                choose_identity_fields(process_fields),
            )
            matched += len(rows)
            if attempted >= relationship_limit:
                break
        probes.append(
            {
                "document_field": "proceso",
                "process_field": process_field,
                "attempted_document_values": attempted,
                "matched_process_rows": matched,
            }
        )
    return probes


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, records: Sequence[Mapping[str, Any]], fields: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields))
        writer.writeheader()
        writer.writerows(records)


def run(args: argparse.Namespace) -> dict[str, Any]:
    allowed_download_hosts = {host.lower() for host in args.allow_download_host}
    client = HttpClient(args.timeout, app_token=os.getenv("SOCRATA_APP_TOKEN"))
    processes_metadata = client.get_json(metadata_url(PROCESSES_DATASET), {SOCRATA_HOST})
    documents_metadata = client.get_json(metadata_url(DOCUMENTS_DATASET), {SOCRATA_HOST})
    if not isinstance(processes_metadata, Mapping) or not isinstance(documents_metadata, Mapping):
        raise ResponseFormatError("metadatos de dataset inválidos")

    processes_schema = schema_columns(processes_metadata)
    documents_schema = schema_columns(documents_metadata)
    process_fields = {column["field"] for column in processes_schema}
    document_fields = {column["field"] for column in documents_schema}
    filters = parse_filters(args.filter)
    process_records = fetch_sample(
        client,
        PROCESSES_DATASET,
        filters,
        process_fields,
        args.page_size,
        args.process_limit,
        choose_identity_fields(process_fields),
    )
    document_records = fetch_sample(
        client,
        DOCUMENTS_DATASET,
        {},
        document_fields,
        args.page_size,
        args.document_limit,
        choose_identity_fields(document_fields),
    )
    relationship_probes, relationship_records = probe_relationships(
        client,
        process_records,
        process_fields,
        document_fields,
        args.page_size,
        args.relationship_limit,
    )
    reverse_relationship_probes = probe_documents_to_processes(
        client,
        document_records,
        process_fields,
        document_fields,
        args.page_size,
        args.relationship_limit,
    )
    process_export, export_fields = minimal_metadata(process_records, process_fields)
    output_dir = Path(args.output_dir)
    write_json(output_dir / "process_metadata.json", process_export)
    write_csv(output_dir / "process_metadata.csv", process_export, export_fields)

    downloads: list[dict[str, Any]] = []
    document_urls = candidate_document_urls([*document_records, *relationship_records])
    if args.download_documents:
        for url in document_urls[: args.download_limit]:
            try:
                body, content_type = client.read_bytes(url, allowed_download_hosts, args.max_download_bytes)
                downloads.append(
                    {
                        "host": urlparse(url).hostname,
                        "downloaded_bytes": len(body),
                        "content_type": content_type,
                        "sha256": hashlib.sha256(body).hexdigest(),
                    }
                )
            except SpikeError as error:
                downloads.append({"host": urlparse(url).hostname, "error": str(error)})

    result = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "datasets": {
            PROCESSES_DATASET: {"owner": owner_summary(processes_metadata), "schema": processes_schema},
            DOCUMENTS_DATASET: {"owner": owner_summary(documents_metadata), "schema": documents_schema},
        },
        "query": {"filters": filters, "page_size": args.page_size, "process_limit": args.process_limit, "document_limit": args.document_limit},
        "processes": {"sample_count": len(process_records), "export_fields": export_fields},
        "documents": {
            "sample_count": len(document_records),
            "candidate_url_count": len(document_urls),
            "relationship": {
                **relationship_observation(process_records, document_records, process_fields, document_fields),
                "targeted_probes": relationship_probes,
                "reverse_targeted_probes": reverse_relationship_probes,
            },
            "downloads": downloads,
        },
    }
    write_json(output_dir / "spike_result.json", result)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filter", action="append", default=[], help="Filtro exacto campo=valor; el campo debe existir en p6dx-8zbt.")
    parser.add_argument("--process-limit", type=int, default=5)
    parser.add_argument("--document-limit", type=int, default=5)
    parser.add_argument("--page-size", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output-dir", default="output/secop-spike")
    parser.add_argument("--download-documents", action="store_true", help="Lee una muestra de documentos en memoria; no los persiste.")
    parser.add_argument("--download-limit", type=int, default=2)
    parser.add_argument("--relationship-limit", type=int, default=3, help="Máximo de valores de proceso por par de campos candidato.")
    parser.add_argument("--max-download-bytes", type=int, default=1_048_576, help="Límite del spike (1 MiB por defecto), no un límite de producto.")
    parser.add_argument("--allow-download-host", action="append", default=[SOCRATA_HOST], help="Host HTTPS exacto permitido para documentos; se puede repetir.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if min(args.process_limit, args.document_limit, args.page_size, args.download_limit, args.relationship_limit, args.max_download_bytes) < 1 or args.timeout <= 0:
        print("error: los límites deben ser positivos", file=sys.stderr)
        return 2
    try:
        result = run(args)
    except (SpikeError, ValueError) as error:
        print(f"spike failed: {error}", file=sys.stderr)
        return 2
    print(
        "spike completed: "
        f"processes={result['processes']['sample_count']} "
        f"documents={result['documents']['sample_count']} "
        f"document_urls={result['documents']['candidate_url_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
