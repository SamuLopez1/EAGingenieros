"""Pruebas de la configuración por entorno.

El caso que originó estas pruebas: en el contenedor, `EAG_EMBEDDINGS_BASE_URL=`
—vacía, que es como Docker Compose y los archivos `.env` expresan «no
configurado»— hacía fallar el arranque con un error de validación de URL. La API
entraba en bucle de reinicio y el síntoma visible era un 502 en la web, muy lejos
de la causa real.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings

OPTIONAL_EMPTY_FIELDS = [
    "database_url",
    "socrata_app_token",
    "jwt_secret",
    "embeddings_base_url",
    "embeddings_api_key",
    "embeddings_model",
    "clamav_host",
]


@pytest.mark.parametrize("field", OPTIONAL_EMPTY_FIELDS)
def test_empty_optional_variable_means_unset(
    field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Una variable vacía es «no configurado», no un valor inválido."""

    monkeypatch.setenv(f"EAG_{field.upper()}", "")

    settings = Settings(environment="test")

    assert getattr(settings, field) is None


@pytest.mark.parametrize("field", OPTIONAL_EMPTY_FIELDS)
def test_whitespace_only_variable_means_unset(
    field: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Solo espacios tampoco configura nada.

    Un `.env` editado a mano deja espacios con facilidad, y un valor `"   "`
    pasaría la comprobación de cadena vacía sin ser un valor utilizable.
    """

    monkeypatch.setenv(f"EAG_{field.upper()}", "   ")

    settings = Settings(environment="test")

    assert getattr(settings, field) is None


def test_embeddings_declared_unconfigured_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El modo se declara: sin proveedor se usa el representador local."""

    monkeypatch.setenv("EAG_EMBEDDINGS_BASE_URL", "")
    monkeypatch.setenv("EAG_EMBEDDINGS_API_KEY", "")
    monkeypatch.setenv("EAG_EMBEDDINGS_MODEL", "")

    assert Settings(environment="test").embeddings_are_configured is False


def test_embeddings_configured_when_all_three_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EAG_EMBEDDINGS_BASE_URL", "https://embeddings.example/v1")
    monkeypatch.setenv("EAG_EMBEDDINGS_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("EAG_EMBEDDINGS_MODEL", "modelo-de-prueba")

    settings = Settings(environment="test")

    assert settings.embeddings_are_configured is True
    assert settings.require_embeddings_base_url() == "https://embeddings.example/v1"


def test_partial_embeddings_configuration_is_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Con la URL pero sin clave no hay proveedor utilizable."""

    monkeypatch.setenv("EAG_EMBEDDINGS_BASE_URL", "https://embeddings.example/v1")
    monkeypatch.setenv("EAG_EMBEDDINGS_API_KEY", "")
    monkeypatch.setenv("EAG_EMBEDDINGS_MODEL", "")

    assert Settings(environment="test").embeddings_are_configured is False


def test_invalid_url_is_still_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """La tolerancia es con el vacío, no con un valor mal formado.

    Aceptar `"no-es-una-url"` en silencio haría que el fallo apareciera más
    tarde y en otro lugar, al intentar usar el proveedor.
    """

    monkeypatch.setenv("EAG_EMBEDDINGS_BASE_URL", "no-es-una-url")

    # Se afirma el tipo concreto de pydantic y no `Exception` a secas: una
    # excepción cualquiera —un `AttributeError`, por ejemplo— también haría
    # pasar la prueba sin demostrar que la URL se validó.
    with pytest.raises(ValidationError):
        Settings(environment="test")


def test_missing_database_url_declares_no_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EAG_DATABASE_URL", "")

    settings = Settings(environment="test")

    assert settings.database_is_configured is False
    with pytest.raises(RuntimeError):
        settings.require_database_url()


def test_missing_jwt_secret_fails_with_a_clear_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El secreto se exige al autenticar, no al construir la aplicación.

    Exigirlo al arrancar impediría tareas que no usan autenticación —generar el
    cliente OpenAPI, aplicar una migración— y obligaría a definir un secreto
    donde no hace falta.
    """

    monkeypatch.setenv("EAG_JWT_SECRET", "")

    settings = Settings(environment="test")

    with pytest.raises(RuntimeError, match="EAG_JWT_SECRET"):
        settings.require_jwt_secret()


def test_cors_origins_split_and_ignore_empties(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "EAG_CORS_ALLOWED_ORIGINS",
        "http://localhost:5173, ,http://127.0.0.1:5173",
    )

    assert Settings(environment="test").cors_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
