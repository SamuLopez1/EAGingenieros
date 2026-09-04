"""Aplicación mínima para comprobar configuración y conectividad local."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

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
from app.invitations import (
    InvitationProviderUnavailable,
    InvitationService,
    UnconfiguredInvitationGateway,
)

CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]
AdministratorPrincipal = Annotated[Principal, Depends(require_roles(Role.ADMINISTRATOR))]


def create_app(
    settings: Settings | None = None,
    auth_services: AuthServices | None = None,
    invitation_service: InvitationService | None = None,
) -> FastAPI:
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
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Accept", "Authorization", "Content-Type"],
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
    app.state.invitation_service = invitation_service or InvitationService(
        gateway=UnconfiguredInvitationGateway()
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
        except InvitationProviderUnavailable:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="El proveedor de invitaciones no está configurado.",
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
        return InvitationResponse(invitation_id=invitation_id, status="revoked")

    return app


app = create_app()
