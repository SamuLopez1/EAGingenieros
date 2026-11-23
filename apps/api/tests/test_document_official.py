import pytest

from app.documents import official
from app.documents.official import (
    SecopDocumentDownloader,
    SourceError,
    official_url,
    pinned_address,
)


@pytest.mark.parametrize("url", [
    "http://community.secop.gov.co/x",
    "https://community.secop.gov.co.example.invalid/x",
    "https://community.secop.gov.co@127.0.0.1/x",
    "https://community.secop.gov.co:444/x",
    "https://community.secop.gov.co\\@127.0.0.1/x",
    "https://community.secop.gov.co/x#ignored",
])
def test_official_url_rejects_unsafe_targets(url: str) -> None:
    with pytest.raises(SourceError):
        official_url(url)


def test_dns_rejects_a_mixed_public_and_private_answer(monkeypatch) -> None:
    records = [(2, 1, 6, "", ("8.8.8.8", 443)),
               (2, 1, 6, "", ("169.254.169.254", 443))]
    monkeypatch.setattr(official.socket, "getaddrinfo", lambda *args, **kwargs: records)
    with pytest.raises(SourceError, match="dirección"):
        pinned_address("community.secop.gov.co")


def test_redirects_are_revalidated_before_any_new_connection(monkeypatch) -> None:
    connections = []

    class Redirect:
        status = 302

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def getheader(self, name):
            assert name == "Location"
            return "https://169.254.169.254/latest"

    class Connection:
        def __init__(self, host, address, timeout):
            connections.append((host, address))

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Redirect()

        def close(self):
            pass

    monkeypatch.setattr(official, "pinned_address", lambda _: "8.8.8.8")
    monkeypatch.setattr(official, "PinnedHTTPSConnection", Connection)
    with pytest.raises(SourceError):
        SecopDocumentDownloader().read("https://community.secop.gov.co/synthetic", 1024)
    assert connections == [("community.secop.gov.co", "8.8.8.8")]
