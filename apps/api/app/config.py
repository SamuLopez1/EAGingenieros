"""Configuración tipada y sin secretos expuestos por la API."""

from __future__ import annotations

from functools import cached_property
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

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
    # Ninguno de estos valores se entrega mediante rutas de la API. Las claves
    # de servicio solo viven en el proceso del backend.
    supabase_url: AnyHttpUrl | None = None
    supabase_publishable_key: SecretStr | None = None
    supabase_service_role_key: SecretStr | None = None
    auth_jwks_url: AnyHttpUrl | None = None
    auth_issuer: str | None = None
    auth_audience: str | None = None
    initial_organization_id: UUID = UUID("00000000-0000-0000-0000-000000000001")

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

    @property
    def jwt_validation_is_configured(self) -> bool:
        """Indica si existen todos los valores para validar un JWT remoto."""

        return all((self.auth_jwks_url, self.auth_issuer, self.auth_audience))

    @property
    def supabase_invites_are_configured(self) -> bool:
        """Las invitaciones requieren URL y clave privilegiada solo en backend."""

        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def supabase_memberships_are_configured(self) -> bool:
        """Resolver pertenencias usa la clave publicable y el JWT del usuario."""

        return bool(self.supabase_url and self.supabase_publishable_key)
