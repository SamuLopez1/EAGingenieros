from __future__ import annotations

import json
import socket
import unittest
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from scripts.secop_spike import (
    HttpClient,
    HttpStatusError,
    NetworkError,
    ResponseSizeError,
    ResponseFormatError,
    UnsafeUrlError,
    build_where,
    candidate_document_urls,
    deduplicate_records,
    fetch_sample,
    parse_filters,
)


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200, headers: dict[str, str] | None = None):
        self._body = BytesIO(body)
        self.status = status
        self.headers = headers or {}

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        self._body.close()


class ScriptedOpener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    def open(self, request, timeout):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class StatusOnlyResponse:
    """Respuesta mínima que expone status, pero no getcode()."""

    def __init__(self, body: bytes, headers: dict[str, str] | None = None):
        self.status = 200
        self.headers = headers or {}
        self._body = BytesIO(body)

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def close(self) -> None:
        self._body.close()


class PagingClient:
    def __init__(self, pages):
        self.pages = pages
        self.urls = []

    def get_json(self, url, allowed_hosts):
        self.urls.append(url)
        offset = int(parse_qs(urlparse(url).query)["$offset"][0])
        return self.pages[offset]


class SecopSpikeTests(unittest.TestCase):
    def test_filters_accept_existing_fields_and_escape_values(self):
        filters = parse_filters(["estado=PUBLICADO", "entidad=O'Hara"])
        where = build_where(filters, {"estado", "entidad"})
        self.assertEqual(where, "entidad = 'O''Hara' AND estado = 'PUBLICADO'")
        with self.assertRaises(ValueError):
            build_where({"inexistente": "x"}, {"estado"})
        with self.assertRaises(ValueError):
            parse_filters(["estado"])

    def test_pagination_stops_at_limit_and_deduplicates(self):
        client = PagingClient(
            {
                0: [{"id": "a"}, {"id": "b"}],
                2: [{"id": "b"}, {"id": "c"}],
            }
        )
        sample = fetch_sample(client, "demo", {}, {"id"}, 2, 4, ["id"])
        self.assertEqual(sample, [{"id": "a"}, {"id": "b"}, {"id": "c"}])
        self.assertEqual(len(client.urls), 2)

    def test_empty_response_returns_empty_sample(self):
        client = PagingClient({0: []})
        self.assertEqual(fetch_sample(client, "demo", {}, {"id"}, 2, 3, ["id"]), [])

    def test_deduplication_uses_serialized_record_without_identity(self):
        records = [{"name": "x"}, {"name": "x"}, {"name": "y"}]
        self.assertEqual(deduplicate_records(records, []), [{"name": "x"}, {"name": "y"}])

    def test_timeout_is_visible(self):
        client = HttpClient(0.1, opener=ScriptedOpener([URLError(socket.timeout("late"))]))
        with self.assertRaisesRegex(NetworkError, "timeout"):
            client.get_json("https://www.datos.gov.co/resource/demo.json", {"www.datos.gov.co"})

    def test_429_and_5xx_are_visible(self):
        url = "https://www.datos.gov.co/resource/demo.json"
        for status in (429, 503):
            error = HTTPError(url, status, "failure", {"Retry-After": "30"}, None)
            client = HttpClient(0.1, opener=ScriptedOpener([error]))
            with self.assertRaises(HttpStatusError) as captured:
                client.get_json(url, {"www.datos.gov.co"})
            self.assertEqual(captured.exception.status, status)
            self.assertEqual(captured.exception.retry_after, "30")

    def test_rejects_unsafe_url_and_unsafe_redirect(self):
        client = HttpClient(0.1, opener=ScriptedOpener([]))
        with self.assertRaises(UnsafeUrlError):
            client.get_json("http://www.datos.gov.co/resource/demo.json", {"www.datos.gov.co"})

        redirect = HTTPError(
            "https://www.datos.gov.co/resource/demo.json",
            302,
            "redirect",
            {"Location": "https://not-allowed.example/file.pdf"},
            None,
        )
        client = HttpClient(0.1, opener=ScriptedOpener([redirect]))
        with self.assertRaises(UnsafeUrlError):
            client.get_json("https://www.datos.gov.co/resource/demo.json", {"www.datos.gov.co"})

    def test_download_size_limit_is_enforced(self):
        client = HttpClient(0.1, opener=ScriptedOpener([FakeResponse(b"12345", headers={"Content-Length": "5"})]))
        with self.assertRaises(ResponseSizeError):
            client.read_bytes("https://www.datos.gov.co/file.pdf", {"www.datos.gov.co"}, max_bytes=4)

    def test_status_only_response_and_invalid_content_length(self):
        client = HttpClient(0.1, opener=ScriptedOpener([StatusOnlyResponse(b"{}")]))
        self.assertEqual(client.get_json("https://www.datos.gov.co/resource/demo.json", {"www.datos.gov.co"}), {})

        client = HttpClient(0.1, opener=ScriptedOpener([FakeResponse(b"{}", headers={"Content-Length": "not-a-number"})]))
        with self.assertRaisesRegex(ResponseFormatError, "Content-Length"):
            client.get_json("https://www.datos.gov.co/resource/demo.json", {"www.datos.gov.co"})

    def test_json_response_is_decoded(self):
        client = HttpClient(0.1, opener=ScriptedOpener([FakeResponse(json.dumps([{"id": "a"}]).encode())]))
        self.assertEqual(client.get_json("https://www.datos.gov.co/resource/demo.json", {"www.datos.gov.co"}), [{"id": "a"}])

    def test_document_url_candidates_support_socrata_url_objects(self):
        records = [{"url_descarga_documento": {"url": "https://www.datos.gov.co/file.pdf"}}, {"another": "https://www.datos.gov.co/second.pdf"}]
        self.assertEqual(
            candidate_document_urls(records),
            ["https://www.datos.gov.co/file.pdf", "https://www.datos.gov.co/second.pdf"],
        )


if __name__ == "__main__":
    unittest.main()
