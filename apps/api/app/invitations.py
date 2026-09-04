"""Contratos de invitación de backend; ningún cliente recibe una clave de servicio."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from app.auth import Principal


class InvitationProviderUnavailable(Exception):
    """La integración de Supabase no está configurada o no respondió de forma segura."""


class InvitationGateway(Protocol):
    def create(self, *, email: str, organization_id: UUID, actor_id: UUID) -> UUID: ...

    def resend(self, *, invitation_id: UUID, actor_id: UUID) -> None: ...

    def revoke(self, *, invitation_id: UUID, actor_id: UUID) -> None: ...


class UnconfiguredInvitationGateway:
    """Placeholder seguro hasta que EAG configure y pruebe el proveedor real."""

    def create(self, *, email: str, organization_id: UUID, actor_id: UUID) -> UUID:
        del email, organization_id, actor_id
        raise InvitationProviderUnavailable

    def resend(self, *, invitation_id: UUID, actor_id: UUID) -> None:
        del invitation_id, actor_id
        raise InvitationProviderUnavailable

    def revoke(self, *, invitation_id: UUID, actor_id: UUID) -> None:
        del invitation_id, actor_id
        raise InvitationProviderUnavailable


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
        self.gateway.resend(invitation_id=invitation_id, actor_id=principal.subject_id)

    def revoke(self, *, invitation_id: UUID, principal: Principal) -> None:
        self.gateway.revoke(invitation_id=invitation_id, actor_id=principal.subject_id)
