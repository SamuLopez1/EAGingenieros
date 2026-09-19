"""Aplicación FastAPI del MVP.

El cableado de dependencias ocurre aquí: según la configuración disponible, la
aplicación usa una base de datos real o el repositorio en memoria. Nunca
degrada en silencio —el modo memoria se declara en `/health`— para que nadie
confunda una demostración con un entorno con persistencia.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, sessionmaker

from app.api.auth_routes import router as auth_router
from app.api.knowledge_routes import MAX_UPLOAD_BYTES
from app.api.knowledge_routes import router as knowledge_router
from app.api.routes import router as opportunities_router
from app.config import Settings
from app.contracts import HealthResponse
from app.db.repository import (
    InMemoryOpportunityRepository,
    OpportunityRepository,
    SqlOpportunityRepository,
)
from app.db.session import create_engine_from_url, create_session_factory, session_scope
from app.db.sync_service import SyncService
from app.documents.validation import ClamAvScanner
from app.rag.embeddings import build_embedder
from app.rag.ingestion import IngestionService
from app.rag.retriever import Retriever
from app.secop.client import PROCESSES_DATASET, HttpxClient, SecopClient


def build_persistence(
    settings: Settings,
) -> tuple[OpportunityRepository, sessionmaker[Session] | None, Callable[[], None]]:
    """Devuelve el repositorio, la fábrica de sesiones y un cierre ordenado.

    Sin base de datos configurada se usa el repositorio en memoria: permite
    desarrollar y probar sin infraestructura. La memoria no persiste entre
    reinicios, y eso se declara en el health check en lugar de disimularse.
    """

    if not settings.database_is_configured:
        return InMemoryOpportunityRepository(), None, lambda: None

    engine = create_engine_from_url(settings.require_database_url())
    factory = create_session_factory(engine)

    class SessionBoundRepository:
        """Repositorio que abre una sesión por operación.

        Mantener una sesión viva durante toda la vida de la aplicación
        acumularía estado y dificultaría recuperarse de una conexión caída.
        """

        def _repo(self, session: Session) -> SqlOpportunityRepository:
            return SqlOpportunityRepository(session)

        def upsert_many(self, records):  # type: ignore[no-untyped-def]
            with session_scope(factory) as session:
                return self._repo(session).upsert_many(records)

        def count(self) -> int:
            with session_scope(factory) as session:
                return self._repo(session).count()

        def get_by_source(self, dataset: str, source_id: str):  # type: ignore[no-untyped-def]
            with session_scope(factory) as session:
                return self._repo(session).get_by_source(dataset, source_id)

        def get_by_id(self, opportunity_id: int):  # type: ignore[no-untyped-def]
            with session_scope(factory) as session:
                return self._repo(session).get_by_id(opportunity_id)

        def list_recent(self, *, limit: int, offset: int):  # type: ignore[no-untyped-def]
            with session_scope(factory) as session:
                return self._repo(session).list_recent(limit=limit, offset=offset)

    return SessionBoundRepository(), factory, engine.dispose


def create_app(settings: Settings | None = None) -> FastAPI:
    """Construye la aplicación con su persistencia y su cliente de SECOP."""

    active_settings = settings or Settings()
    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        description=(
            "API del MVP de preevaluación de licitaciones. "
            "Las rutas de negocio aún no están protegidas por autenticación."
        ),
    )

    if active_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=active_settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Accept", "Content-Type"],
        )

    repository, session_factory, dispose = build_persistence(active_settings)
    app.state.opportunity_repository = repository
    app.state.persistence_mode = "database" if session_factory else "memory"
    app.state.session_factory = session_factory
    app.state.dispose_persistence = dispose


    # El representador se construye una vez: es sin estado y crearlo por
    # petición añadiría trabajo sin motivo.
    embedder = build_embedder(active_settings)
    app.state.embedder_model = embedder.model_id

    # Antivirus. Se construye una vez: es sin estado y solo abre el socket
    # cuando se le pide un análisis.
    if active_settings.clamav_host:
        app.state.antivirus_scanner = ClamAvScanner(
            host=active_settings.clamav_host,
            port=active_settings.clamav_port,
        )
    else:
        app.state.antivirus_scanner = None
    app.state.require_antivirus = active_settings.require_antivirus

    def make_ingestion_service() -> IngestionService:
        """Servicio de ingesta con su propia sesión.

        Se abre una sesión por operación: la ingesta puede tardar —OCR de un
        pliego de decenas de páginas— y mantener una sesión viva durante todo
        ese tiempo retendría una conexión del pool sin necesidad.
        """

        if session_factory is None:
            raise RuntimeError(
                "la base de conocimiento requiere persistencia configurada"
            )
        return IngestionService(
            session_factory(),
            embedder=embedder,
            # El antivirus se pasa también aquí, no solo a la ruta: la ingesta
            # puede invocarse desde un script o una tarea programada, y su
            # validación debe disponer de las mismas herramientas.
            scanner=app.state.antivirus_scanner,
            require_antivirus=active_settings.require_antivirus,
            max_bytes=MAX_UPLOAD_BYTES,
        )

    def make_retriever() -> Retriever:
        if session_factory is None:
            raise RuntimeError("el recuperador requiere persistencia configurada")
        return Retriever(
            session_factory(),
            embedder=embedder,
            threshold=active_settings.rag_similarity_threshold,
            default_limit=active_settings.rag_max_chunks,
        )

    app.state.ingestion_service_factory = (
        make_ingestion_service if session_factory else None
    )
    app.state.retriever_factory = make_retriever if session_factory else None

    # Servicio de autenticación. Se construye por operación porque cada una
    # necesita su propia sesión y su propio límite transaccional.
    #
    # El secreto de firma se exige **al autenticar**, no al construir la
    # aplicación: exigirlo aquí impediría arrancar en tareas que no usan
    # autenticación —generar el cliente OpenAPI, ejecutar una migración— y
    # obligaría a definir un secreto en entornos donde no se necesita.
    from app.auth.service import AuthService
    from app.auth.tokens import TokenService

    def make_auth_service() -> AuthService:
        if session_factory is None:
            raise RuntimeError("la autenticación requiere persistencia configurada")
        return AuthService(
            session_factory(),
            tokens=TokenService(secret=active_settings.require_jwt_secret()),
        )

    app.state.auth_service_factory = make_auth_service if session_factory else None
    app.state.authentication_enabled = active_settings.jwt_secret is not None

    def make_sync_service() -> SyncService:
        """Crea un servicio de sincronización con recursos propios.

        El cliente HTTP se abre por ejecución y se cierra al terminar, para no
        mantener conexiones abiertas entre sincronizaciones.
        """

        token = (
            active_settings.socrata_app_token.get_secret_value()
            if active_settings.socrata_app_token
            else None
        )
        http = HttpxClient(app_token=token)
        client = SecopClient(
            http=http,
            page_size=active_settings.secop_page_size,
            timeout=active_settings.secop_timeout_seconds,
            max_retries=active_settings.secop_max_retries,
            max_requests=active_settings.secop_max_requests,
        )
        session = session_factory() if session_factory else None
        tracker = None
        if session is not None:
            from app.db.repository import SyncRunTracker

            tracker = SyncRunTracker(session, dataset=PROCESSES_DATASET, trigger="manual")
        return SyncService(
            client=client,
            repository=repository,
            tracker=tracker,
            session=session,
        )

    app.state.sync_service_factory = make_sync_service

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=active_settings.app_version,
            environment=active_settings.environment,
            persistence=app.state.persistence_mode,
            # Se declara el representador en uso: el local no entiende de
            # significado, y confundirlo con un modelo semántico llevaría a
            # conclusiones equivocadas sobre la calidad de la recuperación.
            embeddings=(
                "proveedor_externo"
                if active_settings.embeddings_are_configured
                else "local_sin_semantica"
            ),
        )

    app.include_router(auth_router)
    app.include_router(opportunities_router)
    app.include_router(knowledge_router)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """Libera el motor de base de datos al apagar la aplicación."""

        try:
            yield
        finally:
            app.state.dispose_persistence()

    # El lifespan se registra después de construir las rutas para que el
    # cableado ya exista cuando la aplicación empiece a servir.
    app.router.lifespan_context = lifespan

    return app


app = create_app()
