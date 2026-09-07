"""Autenticación verificable y autorización de organización para la API.

Los claims de rol u organización nunca se aceptan desde el JWT: el backend
resuelve la pertenencia en un proveedor de datos independiente después de
validar criptográficamente el token.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Protocol
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError

from app.config import Settings


class Role(StrEnum):
    ADMINISTRATOR = "administrador"
    ANALYST = "analista"


@dataclass(frozen=True)
class Membership:
    organization_id: UUID
    role: Role


@dataclass(frozen=True)
class Principal:
    subject_id: UUID
    membership: Membership


class AuthenticationError(Exception):
    """El bearer token falta, no es válido o no satisface los claims requeridos."""


class AuthorizationError(Exception):
    """El sujeto autenticado no cuenta con una pertenencia o permiso suficiente."""


class AuthenticationConfigurationError(Exception):
    """Faltan valores externos para validar tokens o resolver pertenencias."""


class MembershipResolver(Protocol):
    def resolve(self, subject_id: UUID, access_token: str) -> Membership | None: ...


class SigningKeyLoader(Protocol):
    def __call__(self, encoded_token: str) -> Any: ...


class JwtValidator:
    """Verifica JWKS, firma, expiración, issuer y audience antes de usar `sub`."""

    def __init__(
        self, settings: Settings, signing_key_loader: SigningKeyLoader | None = None
    ) -> None:
        self._settings = settings
        self._signing_key_loader: SigningKeyLoader | None
        if signing_key_loader is not None:
            self._signing_key_loader = signing_key_loader
        elif settings.auth_jwks_url is not None:
            jwks_client = PyJWKClient(str(settings.auth_jwks_url))
            self._signing_key_loader = lambda token: jwks_client.get_signing_key_from_jwt(token).key
        else:
            self._signing_key_loader = None

    def subject_from_token(self, access_token: str) -> UUID:
        if not self._settings.jwt_validation_is_configured or self._signing_key_loader is None:
            raise AuthenticationConfigurationError
        try:
            signing_key = self._signing_key_loader(access_token)
            claims = jwt.decode(
                access_token,
                signing_key,
                # Los proyectos Supabase recientes pueden emitir RS256 o ES256.
                # La lista cerrada impide aceptar `none`, HS256 u otros algoritmos.
                algorithms=["RS256", "ES256"],
                audience=self._settings.auth_audience,
                issuer=self._settings.auth_issuer,
                options={"require": ["exp", "iss", "aud", "sub"]},
            )
            return UUID(str(claims["sub"]))
        except (InvalidTokenError, PyJWKClientError, KeyError, TypeError, ValueError) as error:
            raise AuthenticationError from error


class UnconfiguredMembershipResolver:
    """Evita aceptar un JWT válido cuando aún no existe fuente de pertenencias."""

    def resolve(self, subject_id: UUID, access_token: str) -> Membership | None:
        del subject_id, access_token
        raise AuthenticationConfigurationError


class SupabaseMembershipResolver:
    """Lee una pertenencia sometida a RLS usando el JWT ya validado del usuario."""

    def __init__(self, settings: Settings) -> None:
        if not settings.supabase_memberships_are_configured:
            raise AuthenticationConfigurationError
        assert settings.supabase_url is not None
        assert settings.supabase_publishable_key is not None
        self._url = f"{str(settings.supabase_url).rstrip('/')}/rest/v1/organization_memberships"
        self._publishable_key = settings.supabase_publishable_key.get_secret_value()

    def resolve(self, subject_id: UUID, access_token: str) -> Membership | None:
        try:
            response = httpx.get(
                self._url,
                params={
                    "user_id": f"eq.{subject_id}",
                    "select": "organization_id,role",
                },
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {access_token}",
                    "apikey": self._publishable_key,
                },
                follow_redirects=False,
                timeout=5.0,
            )
        except httpx.HTTPError as error:
            raise AuthenticationConfigurationError from error
        if response.status_code in (401, 403):
            return None
        if response.is_error:
            raise AuthenticationConfigurationError
        try:
            payload: object = response.json()
            if not isinstance(payload, list) or len(payload) != 1:
                return None
            record = payload[0]
            if not isinstance(record, dict):
                return None
            return Membership(
                organization_id=UUID(str(record["organization_id"])), role=Role(str(record["role"]))
            )
        except (KeyError, TypeError, ValueError):
            return None


@dataclass
class AuthServices:
    validator: JwtValidator
    memberships: MembershipResolver

    def authenticate(self, access_token: str) -> Principal:
        subject_id = self.validator.subject_from_token(access_token)
        membership = self.memberships.resolve(subject_id, access_token)
        if membership is None:
            raise AuthorizationError
        return Principal(subject_id=subject_id, membership=membership)


bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No fue posible autenticar la solicitud.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_principal(request: Request, credentials: BearerCredentials) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized()
    services: AuthServices = request.app.state.auth_services
    try:
        return services.authenticate(credentials.credentials)
    except AuthenticationError:
        raise unauthorized() from None
    except AuthenticationConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La autenticación no está configurada.",
        ) from None
    except AuthorizationError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
        ) from None


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    def dependency(principal: Annotated[Principal, Depends(get_current_principal)]) -> Principal:
        if principal.membership.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
            )
        return principal

    return dependency
