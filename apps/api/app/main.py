"""Aplicación mínima para comprobar configuración y conectividad local."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings
from app.contracts import HealthResponse


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construye una API sin dependencias externas ni estado compartido."""

    active_settings = settings or Settings()
    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        description="Contrato inicial de EAG. No incluye módulos de negocio.",
    )

    if active_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=active_settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=["Accept", "Content-Type"],
        )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=active_settings.app_version,
            environment=active_settings.environment,
        )

    return app


app = create_app()
