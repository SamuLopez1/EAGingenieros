"""Contratos de invitación de backend; ningún cliente recibe una clave de servicio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

import httpx

from app.auth import Principal
from app.config import Settings


class InvitationProviderUnavailable(Exception):
    """La integración de Supabase no está configurada o no respondió de forma segura."""


class InvitationAuthorizationError(Exception):
    """La invitación no pertenece a la organización del administrador."""


class InvitationResendUnsupported(Exception):
    """El proveedor no expone un reenvío de invitaciones seguro y documentado."""


class InvitationGateway(Protocol):
    def create(self, *, email: str, organization_id: UUID, actor_id: UUID) -> UUID: ...

    def resend(self, *, invitation_id: UUID, organization_id: UUID, actor_id: UUID) -> None: ...

    def revoke(self, *, invitation_id: UUID, organization_id: UUID, actor_id: UUID) -> None: ...


class UnconfiguredInvitationGateway:
    """Placeholder seguro hasta que EAG configure y pruebe el proveedor real."""

    def create(self, *, email: str, organization_id: UUID, actor_id: UUID) -> UUID:
        del email, organization_id, actor_id
        raise InvitationProviderUnavailable

    def resend(self, *, invitation_id: UUID, organization_id: UUID, actor_id: UUID) -> None:
        del invitation_id, organization_id, actor_id
        raise InvitationProviderUnavailable

    def revoke(self, *, invitation_id: UUID, organization_id: UUID, actor_id: UUID) -> None:
        del invitation_id, organization_id, actor_id
        raise InvitationProviderUnavailable


class SupabaseInvitationGateway:
    """Invita y revoca desde el backend sin entregar la clave privilegiada al cliente.

    Las mutaciones de las tablas públicas se concentran en RPCs SQL para que el
    registro de perfil, membresía, invitación y auditoría sea atómico.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_invites_are_configured:
            raise InvitationProviderUnavailable
        assert settings.supabase_url is not None
        assert settings.supabase_service_role_key is not None
        assert settings.supabase_invite_redirect_url is not None
        self._url = str(settings.supabase_url).rstrip("/")
        self._redirect_url = str(settings.supabase_invite_redirect_url)
        self._service_key = settings.supabase_service_role_key.get_secret_value()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._service_key}",
            "apikey": self._service_key,
        }

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, object] | None = None,
    ) -> httpx.Response:
        try:
            response = httpx.request(
                method,
                f"{self._url}{path}",
                headers=self._headers,
                follow_redirects=False,
                timeout=5.0,
                params=params,
                json=json,
            )
        except httpx.HTTPError as error:
            raise InvitationProviderUnavailable from error
        if response.is_error:
            raise InvitationProviderUnavailable
        return response

    @staticmethod
    def _provider_user_id(response: httpx.Response) -> UUID:
        try:
            payload: object = response.json()
            if not isinstance(payload, dict):
                raise ValueError
            user = payload.get("user", payload)
            if not isinstance(user, dict):
                raise ValueError
            return UUID(str(user["id"]))
        except (KeyError, TypeError, ValueError) as error:
            raise InvitationProviderUnavailable from error

    def create(self, *, email: str, organization_id: UUID, actor_id: UUID) -> UUID:
        provider_response = self._request(
            "POST",
            "/auth/v1/invite",
            params={"redirect_to": self._redirect_url},
            json={"email": email, "data": {}},
        )
        provider_user_id = self._provider_user_id(provider_response)
        invitation_id = uuid4()
        try:
            self._request(
                "POST",
                "/rest/v1/rpc/record_eag_invitation",
                json={
                    "p_invitation_id": str(invitation_id),
                    "p_provider_user_id": str(provider_user_id),
                    "p_organization_id": str(organization_id),
                    "p_email": email,
                    "p_actor_id": str(actor_id),
                },
            )
        except InvitationProviderUnavailable:
            # Si la auditoría/membresía no se pudo guardar, el usuario recién
            # invitado no debe conservar una cuenta utilizable.
            try:
                self._request("DELETE", f"/auth/v1/admin/users/{provider_user_id}")
            except InvitationProviderUnavailable:
                pass
            raise
        return invitation_id

    def _find_invitation(self, invitation_id: UUID, organization_id: UUID) -> UUID:
        response = self._request(
            "GET",
            "/rest/v1/invitations",
            params={
                "id": f"eq.{invitation_id}",
                "organization_id": f"eq.{organization_id}",
                "select": "provider_user_id",
            },
        )
        try:
            payload: object = response.json()
            if (
                not isinstance(payload, list)
                or len(payload) != 1
                or not isinstance(payload[0], dict)
            ):
                raise InvitationAuthorizationError
            return UUID(str(payload[0]["provider_user_id"]))
        except (KeyError, TypeError, ValueError) as error:
            raise InvitationAuthorizationError from error

    def resend(self, *, invitation_id: UUID, organization_id: UUID, actor_id: UUID) -> None:
        del actor_id
        self._find_invitation(invitation_id, organization_id)
        # Supabase no documenta una operación de reenvío de invitación. No se
        # usa `/resend`, que solo cubre signup, sms y cambios de contacto.
        raise InvitationResendUnsupported

    def revoke(self, *, invitation_id: UUID, organization_id: UUID, actor_id: UUID) -> None:
        provider_user_id = self._find_invitation(invitation_id, organization_id)
        # Primero retirar la membresía mediante RPC. Así RLS y la API niegan
        # acceso incluso si la eliminación del usuario Auth falla después.
        self._request(
            "POST",
            "/rest/v1/rpc/revoke_eag_invitation",
            json={
                "p_invitation_id": str(invitation_id),
                "p_organization_id": str(organization_id),
                "p_actor_id": str(actor_id),
            },
        )
        self._request("DELETE", f"/auth/v1/admin/users/{provider_user_id}")


@dataclass
class InvitationService:
    gateway: InvitationGateway

    def create(self, *, email: str, principal: Principal) -> UUID:
        return self.gateway.create(
            email=email,
            organization_id=principal.membership.organization_id,
            actor_id=principal.subject_id,
        )

    def resend(self, *, invitation_id: UUID, principal: Principal) -> None:
        self.gateway.resend(
            invitation_id=invitation_id,
            organization_id=principal.membership.organization_id,
            actor_id=principal.subject_id,
        )

    def revoke(self, *, invitation_id: UUID, principal: Principal) -> None:
        self.gateway.revoke(
            invitation_id=invitation_id,
            organization_id=principal.membership.organization_id,
            actor_id=principal.subject_id,
        )
