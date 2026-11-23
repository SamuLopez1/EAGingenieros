"""Aplicación mínima para comprobar configuración y conectividad local."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.api.comparison_routes import router as comparison_router
from app.api.document_routes import DocumentServices
from app.api.document_routes import router as opportunity_documents_router
from app.api.extraction_routes import router as extraction_router
from app.api.filter_routes import router as opportunity_filters_router
from app.api.profile_routes import router as company_profile_router
from app.api.report_routes import router as report_router
from app.api.requirements_routes import router as requirements_router
from app.api.routes import require_eag_member
from app.api.routes import router as opportunities_router
from app.auth import (
    AuthServices,
    JwtValidator,
    Principal,
    Role,
    SupabaseMembershipResolver,
    UnconfiguredMembershipResolver,
    get_current_principal,
    require_roles,
)
from app.config import Settings
from app.contracts import (
    HealthResponse,
    InvitationCreateRequest,
    InvitationResponse,
    SessionResponse,
)
from app.db.session import create_engine_from_url, create_session_factory
from app.db.sync_service import create_sync_service
from app.documents.official import SecopDocumentDownloader, load_manifest
from app.documents.service import DocumentError
from app.documents.validation import ClamAvScanner
from app.invitations import (
    InvitationAuthorizationError,
    InvitationProviderUnavailable,
    InvitationResendUnsupported,
    InvitationService,
    SupabaseInvitationGateway,
    UnconfiguredInvitationGateway,
)

CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
AdministratorPrincipal = Annotated[Principal, Depends(require_roles(Role.ADMINISTRATOR))]


def create_app(
    settings: Settings | None = None,
    auth_services: AuthServices | None = None,
    invitation_service: InvitationService | None = None,
) -> FastAPI:
    """Construye la API y habilita persistencia con una URL de PostgreSQL."""

    active_settings = settings or Settings()
    engine = (
        create_engine_from_url(active_settings.require_database_url())
        if active_settings.database_is_configured
        else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    app = FastAPI(
        title=active_settings.app_name,
        version=active_settings.app_version,
        description="API de EAG para acceso y sincronización de oportunidades oficiales.",
        lifespan=lifespan,
    )

    if active_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=active_settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=[
                "Accept", "Authorization", "Content-Type",
                "X-Document-Name", "X-Document-Title", "X-Document-Ticket",
            ],
        )

    # Las implementaciones reales de membresías e invitaciones requieren una
    # instancia Supabase autorizada. Sin ella, las rutas protegidas fallan de
    # forma explícita y no degradan a aceptar claims o datos del navegador.
    memberships = (
        SupabaseMembershipResolver(active_settings)
        if active_settings.supabase_memberships_are_configured
        else UnconfiguredMembershipResolver()
    )
    app.state.auth_services = auth_services or AuthServices(
        validator=JwtValidator(active_settings), memberships=memberships
    )
    invitations = (
        SupabaseInvitationGateway(active_settings)
        if active_settings.supabase_invites_are_configured
        else UnconfiguredInvitationGateway()
    )
    app.state.invitation_service = invitation_service or InvitationService(gateway=invitations)

    if engine is not None:
        factory = create_session_factory(engine)
        app.state.opportunity_session_factory = factory
        app.state.sync_service_factory = lambda: create_sync_service(active_settings, factory)
    app.state.opportunity_settings = active_settings
    app.include_router(opportunities_router)
    app.include_router(opportunity_filters_router, dependencies=[Depends(require_eag_member)])
    clam_host = active_settings.document_clamav_host
    app.state.document_services = DocumentServices(
        scanner=ClamAvScanner(host=clam_host, port=active_settings.document_clamav_port)
        if clam_host else None,
        downloader=SecopDocumentDownloader(),
        manifest=load_manifest(active_settings.official_document_manifest),
    )
    app.include_router(opportunity_documents_router)
    app.include_router(extraction_router)
    app.include_router(requirements_router)
    app.include_router(comparison_router)
    app.include_router(report_router)
    app.include_router(company_profile_router)

    @app.exception_handler(DocumentError)
    async def document_error(_: Request, error: Exception) -> JSONResponse:
        assert isinstance(error, DocumentError)
        return JSONResponse(
            status_code=error.status, content={"detail": error.code},
            headers={"Cache-Control": "private, no-store"},
        )


    @app.exception_handler(SQLAlchemyError)
    async def persistence_unavailable(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "La persistencia no está disponible."},
        )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            version=active_settings.app_version,
            environment=active_settings.environment,
        )

    @app.get("/auth/session", response_model=SessionResponse, tags=["auth"])
    def session(principal: CurrentPrincipal) -> SessionResponse:
        return SessionResponse(
            subject_id=principal.subject_id,
            organization_id=principal.membership.organization_id,
            role=principal.membership.role.value,
        )

    @app.get(
        "/auth/organizations/{organization_id}/session",
        response_model=SessionResponse,
        tags=["auth"],
    )
    def organization_session(
        organization_id: UUID, principal: CurrentPrincipal
    ) -> SessionResponse:
        if organization_id != principal.membership.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
            )
        return SessionResponse(
            subject_id=principal.subject_id,
            organization_id=principal.membership.organization_id,
            role=principal.membership.role.value,
        )

    @app.post(
        "/auth/invitations",
        response_model=InvitationResponse,
        status_code=status.HTTP_202_ACCEPTED,
        tags=["auth"],
    )
    def create_invitation(
        invitation: InvitationCreateRequest,
        principal: AdministratorPrincipal,
    ) -> InvitationResponse:
        service: InvitationService = app.state.invitation_service
        try:
            invitation_id = service.create(email=invitation.email, principal=principal)
        except InvitationProviderUnavailable:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El proveedor de invitaciones no está configurado.",
            ) from None
        return InvitationResponse(invitation_id=invitation_id, status="sent")

    @app.post(
        "/auth/invitations/{invitation_id}/resend",
        response_model=InvitationResponse,
        tags=["auth"],
    )
    def resend_invitation(
        invitation_id: UUID,
        principal: AdministratorPrincipal,
    ) -> InvitationResponse:
        service: InvitationService = app.state.invitation_service
        try:
            service.resend(invitation_id=invitation_id, principal=principal)
        except InvitationResendUnsupported:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="El proveedor no admite reenvío seguro de invitaciones.",
            ) from None
        except InvitationProviderUnavailable:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El proveedor de invitaciones no está configurado.",
            ) from None
        except InvitationAuthorizationError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
            ) from None
        return InvitationResponse(invitation_id=invitation_id, status="resent")

    @app.delete(
        "/auth/invitations/{invitation_id}",
        response_model=InvitationResponse,
        tags=["auth"],
    )
    def revoke_invitation(
        invitation_id: UUID,
        principal: AdministratorPrincipal,
    ) -> InvitationResponse:
        service: InvitationService = app.state.invitation_service
        try:
            service.revoke(invitation_id=invitation_id, principal=principal)
        except InvitationProviderUnavailable:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El proveedor de invitaciones no está configurado.",
            ) from None
        except InvitationAuthorizationError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
            ) from None
        return InvitationResponse(invitation_id=invitation_id, status="revoked")

    return app


app = create_app()
