"""Autenticación y autorización del backend.

La API es la capa de autoridad. No acepta rol ni organización desde el
navegador: valida el token criptográficamente y después resuelve la pertenencia
en un origen independiente.

Por qué no se confía en RLS para los datos de negocio: RLS protege el acceso
directo a Postgres, pero la API se conecta con un rol privilegiado que la omite
por diseño. La autorización real tiene que vivir aquí. RLS se reserva para
Storage, donde el navegador sí habla directo con Supabase.

Este módulo no importa SDK de Supabase: define los contratos y deja la
implementación concreta en `supabase_gateway.py`, de modo que la lógica de
permisos se pueda probar sin red ni proveedor.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Protocol, cast
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class Role(StrEnum):
    ADMINISTRATOR = "administrador"
    ANALYST = "analista"


class AuthError(Exception):
    """El token falta, es inválido o no satisface los claims requeridos."""


class AuthNotConfiguredError(Exception):
    """Faltan valores para validar tokens. No debe degradar a acceso abierto."""


class PermissionError_(Exception):
    """El sujeto está autenticado pero carece de permiso."""


@dataclass(frozen=True)
class Principal:
    """Identidad autenticada con su pertenencia resuelta en el servidor.

    Lleva dos representaciones del sujeto a propósito:

    - `subject_id`: el UUID que viaja en el token y se expone hacia fuera.
    - `user_id`: la clave primaria entera, que es lo que usan las relaciones de
      la base de datos. Derivar el entero desde el UUID no es posible sin
      ambigüedad, y usar el entero del UUID como clave foránea apuntaría a un
      usuario que no existe.
    """

    subject_id: UUID
    organization_id: UUID
    role: Role
    user_id: int

    @property
    def is_administrator(self) -> bool:
        return self.role is Role.ADMINISTRATOR


class AuthServiceProtocol(Protocol):
    """Contrato mínimo del servicio de autenticación usado por las rutas.

    Se declara aquí y no se importa de `service` para evitar una dependencia
    circular: `service` ya importa `Principal` de este módulo.
    """

    def principal_from_token(self, token: str) -> Principal: ...


class TokenValidator(Protocol):
    def subject_from_token(self, token: str) -> UUID: ...


class MembershipResolver(Protocol):
    """Resuelve la pertenencia y devuelve también la clave primaria del usuario."""

    def resolve(self, subject_id: UUID, token: str) -> tuple[UUID, Role, int] | None: ...


@dataclass
class AuthServices:
    validator: TokenValidator
    memberships: MembershipResolver

    def authenticate(self, token: str) -> Principal:
        subject = self.validator.subject_from_token(token)
        found = self.memberships.resolve(subject, token)
        if found is None:
            raise PermissionError_
        organization_id, role, user_id = found
        return Principal(
            subject_id=subject,
            organization_id=organization_id,
            role=role,
            user_id=user_id,
        )


bearer_scheme = HTTPBearer(auto_error=False)
Credentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No fue posible autenticar la solicitud.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_principal(request: Request, credentials: Credentials) -> Principal:
    """Resuelve la identidad o falla con 401/403/503.

    Se distinguen tres casos porque exigen respuestas distintas:
    401 si el token falta o es inválido, 403 si es válido pero sin permiso, y
    503 si la autenticación no está configurada. Devolver 401 en el tercer caso
    haría creer que el problema es del usuario cuando es del despliegue.
    """

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise _unauthorized()

    # El servicio de autenticación valida el token y resuelve la pertenencia.
    # Se obtiene de la fábrica registrada por la aplicación en lugar de
    # construirse aquí, para que la sesión de base de datos tenga su propio
    # límite transaccional.
    factory = getattr(request.app.state, "auth_service_factory", None)
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La autenticación no está configurada.",
        )

    try:
        service: AuthServiceProtocol = cast(AuthServiceProtocol, factory())
        return service.principal_from_token(credentials.credentials)
    except AuthNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La autenticación no está configurada.",
        ) from None
    except AuthError:
        raise _unauthorized() from None
    except PermissionError_:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
        ) from None


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    """Dependencia que exige uno de los roles indicados."""

    def dependency(principal: CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Permiso insuficiente.",
            )
        return principal

    return dependency
