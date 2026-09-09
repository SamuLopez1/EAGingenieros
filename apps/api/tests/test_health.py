from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


def test_health_returns_public_status_version_and_environment() -> None:
    client = TestClient(create_app(Settings(app_version="test-version", environment="test")))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "test-version", "environment": "test"}


def test_openapi_publishes_the_health_contract() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]


def test_public_contract_does_not_expose_or_accept_passwords() -> None:
    # El login ocurre directamente con Supabase; la API propia solo recibe JWT.
    client = TestClient(create_app(Settings(_env_file=None)))

    health = client.get("/health")
    contract = client.get("/openapi.json")

    assert "password" not in health.text.lower()
    assert "password" not in contract.text.lower()
    assert "requestBody" not in contract.json()["paths"]["/auth/session"]["get"]


def test_invalid_environment_is_rejected() -> None:
    try:
        Settings(environment="not-valid")  # type: ignore[arg-type]
    except ValidationError as error:
        assert "environment" in str(error)
    else:
        raise AssertionError("an invalid environment must fail validation")


def test_cors_allows_only_configured_origin() -> None:
    client = TestClient(create_app(Settings(cors_allowed_origins=["http://localhost:5173"])))

    allowed = client.options(
        "/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    rejected = client.options(
        "/health",
        headers={"Origin": "https://not-allowed.example", "Access-Control-Request-Method": "GET"},
    )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "authorization" in allowed.headers["access-control-allow-headers"].lower()
    assert rejected.status_code == 400
    assert "access-control-allow-origin" not in rejected.headers


def test_cors_is_not_enabled_by_default() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_use_the_documented_comma_separated_environment_value(monkeypatch) -> None:
    monkeypatch.setenv(
        "EAG_CORS_ALLOWED_ORIGINS", "http://localhost:5173,https://app.example.invalid"
    )

    settings = Settings()

    assert settings.cors_origins == ["http://localhost:5173", "https://app.example.invalid"]
