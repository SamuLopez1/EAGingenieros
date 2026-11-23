"""Configuración tipada y sin secretos expuestos por la API."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import AnyHttpUrl, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.report_mail import normalize_address


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
    supabase_invite_redirect_url: AnyHttpUrl | None = None
    auth_jwks_url: AnyHttpUrl | None = None
    auth_issuer: str | None = None
    auth_audience: str | None = None
    initial_organization_id: UUID = UUID("00000000-0000-0000-0000-000000000001")

    database_url: SecretStr | None = None
    socrata_app_token: SecretStr | None = None
    secop_page_size: int = Field(default=100, ge=1, le=1000)
    secop_timeout_seconds: float = Field(default=20.0, gt=0, le=120)
    secop_max_retries: int = Field(default=2, ge=0, le=5)
    secop_max_requests: int = Field(default=50, ge=1)
    catalog_stale_after_hours: int = Field(default=24, ge=1, le=8760)

    document_max_bytes: int = Field(default=50 * 1024**2, ge=1, le=100 * 1024**2)
    dossier_max_bytes: int = Field(default=300 * 1024**2, ge=1, le=1024**3)
    document_retention_days: int = Field(default=30, ge=1, le=365)
    document_download_secret: SecretStr | None = Field(default=None, min_length=32)
    document_clamav_host: str | None = None
    document_clamav_port: int = Field(default=3310, ge=1, le=65535)
    official_document_manifest: Path | None = None
    extraction_timeout_seconds: int = Field(default=90, ge=5, le=300)
    extraction_ocr_max_pages: int = Field(default=12, ge=0, le=50)
    extraction_ocr_language: str = Field(default="spa+eng", pattern=r"^[a-z]{3}([+][a-z]{3}){0,3}$")

    report_resend_api_key: SecretStr | None = None
    report_mail_sender: str | None = None
    report_mail_recipients: list[str] = Field(default_factory=list, max_length=20)
    report_portal_url: AnyHttpUrl | None = None

    @field_validator("report_mail_sender")
    @classmethod
    def validate_report_sender(cls, value: str | None) -> str | None:
        return normalize_address(value) if value else None

    @field_validator("report_mail_recipients", mode="before")
    @classmethod
    def validate_report_recipients(cls, value: object) -> object:
        addresses = value.split(",") if isinstance(value, str) else value
        if isinstance(addresses, list):
            return list(dict.fromkeys(normalize_address(str(address))
                                      for address in addresses if str(address).strip()))
        return addresses

    @field_validator("report_portal_url")
    @classmethod
    def validate_report_portal(cls, value: AnyHttpUrl | None) -> AnyHttpUrl | None:
        if value and (
            value.scheme != "https" or value.username or value.password
            or value.query or value.fragment
        ):
            raise ValueError("El portal de informes requiere HTTPS y una URL fija.")
        return value

    @property
    def database_is_configured(self) -> bool:
        return bool(self.database_url and self.database_url.get_secret_value().strip())

    def require_database_url(self) -> str:
        if self.database_url is None or not self.database_is_configured:
            raise RuntimeError("EAG_DATABASE_URL se requiere para la sincronización")
        return self.database_url.get_secret_value()

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

        return bool(
            self.supabase_url
            and self.supabase_service_role_key
            and self.supabase_invite_redirect_url
        )

    @property
    def supabase_memberships_are_configured(self) -> bool:
        """Resolver pertenencias usa la clave publicable y el JWT del usuario."""

        return bool(self.supabase_url and self.supabase_publishable_key)
