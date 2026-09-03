"""Configuración tipada y sin secretos expuestos por la API."""

from __future__ import annotations

from functools import cached_property
from typing import Literal
from urllib.parse import urlparse

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Variables de entorno permitidas para la estructura inicial."""

    model_config = SettingsConfigDict(env_prefix="EAG_", env_file=".env", extra="ignore")

    app_name: str = "EAG API"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"
    cors_allowed_origins: list[AnyHttpUrl] = Field(default_factory=list)

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
            port = f":{origin.port}" if origin.port else ""
            origins.append(f"{origin.scheme}://{origin.host}{port}")
        return origins
