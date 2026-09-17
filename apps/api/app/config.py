"""Configuración tipada y sin secretos expuestos por la API."""

from __future__ import annotations

from functools import cached_property
from typing import Literal
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno permitidas para la estructura inicial."""

    # Los orígenes se documentan como una lista separada por comas. Desactivar
    # el JSON implícito permite que el validador los normalice antes de tiparlos.
    model_config = SettingsConfigDict(
        env_prefix="EAG_", env_file=".env", extra="ignore", enable_decoding=False
    )

    app_name: str = "EAG API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    cors_allowed_origins: list[AnyHttpUrl] = Field(default_factory=list)

    # --- Base de datos ---------------------------------------------------
    # Sin URL configurada la aplicación funciona en modo memoria: útil para
    # desarrollar y probar sin una base de datos disponible. En producción la
    # ausencia de URL debe impedir el arranque, no degradar en silencio.
    database_url: SecretStr | None = None

    # --- Sincronización de SECOP ----------------------------------------
    # Token opcional de Socrata. Solo viaja en una cabecera y nunca se registra.
    socrata_app_token: SecretStr | None = None
    secop_page_size: int = Field(default=100, ge=1, le=1000)
    secop_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    secop_max_retries: int = Field(default=2, ge=0, le=5)
    # Tope de peticiones por ejecución. Evita que una sincronización sin
    # supervisión consuma la cuota disponible.
    secop_max_requests: int = Field(default=50, ge=1)

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("cors_allowed_origins")
    @classmethod
    def require_origins_without_paths(cls, origins: list[AnyHttpUrl]) -> list[AnyHttpUrl]:
        for origin in origins:
            parsed = urlparse(str(origin))
            if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
                raise ValueError(
                    "cada origen CORS debe ser un origen, sin ruta, consulta ni fragmento"
                )
        return origins

    @property
    def database_is_configured(self) -> bool:
        """Indica si hay una base de datos configurada."""

        return self.database_url is not None and bool(self.database_url.get_secret_value())

    def require_database_url(self) -> str:
        """Devuelve la URL o falla.

        Se exige explícitamente en lugar de degradar a memoria: una aplicación
        en producción sin base de datos aparentaría funcionar y perdería los
        datos en el siguiente reinicio.
        """

        if not self.database_is_configured:
            raise RuntimeError(
                "EAG_DATABASE_URL no está configurada; se requiere para esta operación"
            )
        assert self.database_url is not None
        return self.database_url.get_secret_value()

    @cached_property
    def cors_origins(self) -> list[str]:
        """Normaliza URLs para compararlas con el encabezado Origin del navegador."""

        origins: list[str] = []
        for origin in self.cors_allowed_origins:
            default_port = (origin.scheme == "http" and origin.port == 80) or (
                origin.scheme == "https" and origin.port == 443
            )
            port = f":{origin.port}" if origin.port and not default_port else ""
            origins.append(f"{origin.scheme}://{origin.host}{port}")
        return origins
