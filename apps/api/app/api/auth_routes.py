"""Rutas de autenticación: inicio de sesión, renovación y cierre.

Decisiones que se reflejan aquí:

- **El error de credenciales no distingue la causa.** Correo inexistente,
  contraseña incorrecta y cuenta desactivada devuelven el mismo 401. Distinguir
  permitiría enumerar qué correos tienen cuenta.
- **La renovación devuelve también el usuario**, para que la interfaz no tenga
  que consultar el perfil por separado en cada renovación.
- **La reutilización de un refresh token devuelve 401 y revoca la sesión
  completa.** No es un caso especial a silenciar: es la señal de que alguien
  copió el token.
- **El cierre de sesión siempre responde 204**, incluso si el token era
  desconocido. El resultado que le importa al usuario —no poder seguir usándolo—
  ya se cumple, y distinguirlo revelaría si un token existe.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from app.auth.principal import CurrentPrincipal, Role
from app.auth.service import (
    AuthService,
    InvalidCredentialsError,
    SessionExpiredError,
    TokenReuseError,
)

router = APIRouter(prefix="/api/v1/auth", tags=["autenticación"])

MIN_PASSWORD_LENGTH = 12

# Validacion de correo propia, no `EmailStr`. `EmailStr` rechaza los dominios
# reservados por la RFC 2606 —`.local`, `.test`, `.invalid`—, que son
# precisamente los que se usan en desarrollo y en el script de administrador.
# Un tipo que rechaza lo que el propio sistema genera convierte la creación de
# usuarios en una trampa: se crea la cuenta y después no se puede iniciar sesión.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")


def validate_email(value: str) -> str:
    """Comprueba que el correo tiene forma válida y lo normaliza."""

    cleaned = value.strip().lower()
    if not _EMAIL.match(cleaned):
        raise ValueError("el correo no tiene un formato válido")
    if len(cleaned) > 320:
        raise ValueError("el correo es demasiado largo")
    return cleaned


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return validate_email(value)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class SessionUser(BaseModel):
    """Identidad devuelta tras autenticarse."""

    user_id: int
    email: str
    display_name: str | None
    role: Role


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: SessionUser


class SessionResponse(BaseModel):
    """Sesión actual, para que la interfaz sepa quién está conectado."""

    user_id: int
    email: str
    display_name: str | None
    role: Role
    organization_id: str


def get_auth_service(request: Request) -> AuthService:
    factory = cast(
        "Callable[[], AuthService] | None",
        getattr(request.app.state, "auth_service_factory", None),
    )
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La autenticación no está configurada.",
        )
    return factory()


AuthDep = Annotated[AuthService, Depends(get_auth_service)]


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales incorrectas.",
        headers={"WWW-Authenticate": "Bearer"},
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión con correo y contraseña",
    responses={401: {"description": "Credenciales incorrectas"}},
)
def login(
    payload: LoginRequest,
    auth: AuthDep,
    request: Request,
    user_agent: Annotated[str | None, Header()] = None,
) -> TokenResponse:
    """Autentica y devuelve un par de tokens.

    La contraseña nunca se registra ni se incluye en la respuesta de error.
    """

    try:
        user, pair = auth.login(
            email=payload.email,
            password=payload.password,
            user_agent=user_agent,
            ip_address=request.client.host if request.client else None,
        )
    except InvalidCredentialsError:
        auth.commit()
        raise _invalid_credentials() from None

    auth.commit()
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
        user=SessionUser(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=Role(user.role),
        ),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Renovar la sesión",
    responses={401: {"description": "Sesión no válida o token reutilizado"}},
)
def refresh(payload: RefreshRequest, auth: AuthDep) -> TokenResponse:
    """Rota el refresh token.

    Si el token presentado ya se usó, la sesión completa queda revocada: eso
    indica que alguien copió el token y hay dos partes usándolo.
    """

    try:
        user, pair = auth.refresh(payload.refresh_token)
    except TokenReuseError:
        auth.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión se cerró por seguridad. Vuelva a iniciar sesión.",
        ) from None
    except SessionExpiredError:
        auth.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión expiró. Vuelva a iniciar sesión.",
        ) from None

    auth.commit()
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
        user=SessionUser(
            user_id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=Role(user.role),
        ),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar sesión",
)
def logout(payload: RefreshRequest, auth: AuthDep) -> Response:
    """Revoca la sesión del refresh token indicado.

    Responde 204 aunque el token fuera desconocido: informar de que no existía
    revelaría qué tokens son válidos.
    """

    auth.logout(payload.refresh_token)
    auth.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/session",
    response_model=SessionResponse,
    summary="Consultar la sesión actual",
    responses={401: {"description": "No autenticado"}},
)
def current_session(
    principal: CurrentPrincipal,
    auth: AuthDep,
) -> SessionResponse:
    """Devuelve identidad y pertenencia del sujeto autenticado.

    Exige un access token válido, así que confirma de paso que la sesión sigue
    vigente: es lo que la interfaz consulta al cargar para saber si debe mostrar
    el inicio de sesión.
    """

    from app.db.models import User

    user = auth.get_user(principal.user_id)
    if user is None:
        # El token era válido pero el usuario ya no existe: la sesión no sirve.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión ya no es válida.",
        )
    _ = User  # importado para tipado explícito del retorno
    return SessionResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=Role(user.role),
        organization_id=str(principal.organization_id),
    )


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)


@router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cambiar la contraseña propia",
)
def change_password(
    payload: PasswordChangeRequest,
    principal: CurrentPrincipal,
    auth: AuthDep,
) -> Response:
    """Cambia la contraseña y cierra las demás sesiones.

    Exige la contraseña actual: sin eso, un access token robado bastaría para
    apropiarse de la cuenta cambiando la credencial.

    Las sesiones se revocan porque si la contraseña se cambia es porque se
    sospecha que estaba comprometida; dejar las sesiones abiertas anularía el
    propósito del cambio.
    """

    try:
        auth.change_password(
            principal.user_id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except InvalidCredentialsError:
        auth.commit()
        raise _invalid_credentials() from None
    except ValueError as error:
        auth.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)
        ) from None

    auth.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
    role: Role = Role.ANALYST
    display_name: str | None = Field(default=None, max_length=200)

    @field_validator("email")
    @classmethod
    def check_email(cls, value: str) -> str:
        return validate_email(value)


@router.post(
    "/users",
    response_model=SessionUser,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un usuario (solo administrador)",
)
def create_user(
    payload: CreateUserRequest,
    principal: CurrentPrincipal,
    auth: AuthDep,
) -> SessionUser:
    """Crea una cuenta. No hay registro público.

    Un analista no puede crear usuarios: permitirlo convertiría cualquier cuenta
    comprometida en una vía para crear accesos persistentes.
    """

    if not principal.is_administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
        )
    try:
        user = auth.create_user(
            email=payload.email,
            password=payload.password,
            role=payload.role,
            display_name=payload.display_name,
            actor_id=principal.user_id,
        )
        auth.commit()
    except Exception as error:  # noqa: BLE001 - el conflicto de correo es el caso esperado
        auth.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No fue posible crear el usuario ({type(error).__name__}).",
        ) from None

    return SessionUser(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=Role(user.role),
    )


class AuditEventResponse(BaseModel):
    id: int
    occurred_at: datetime
    action: str
    outcome: str
    actor_id: int | None
    target_user_id: int | None


@router.get(
    "/audit",
    response_model=list[AuditEventResponse],
    summary="Consultar el registro de actividad (solo administrador)",
)
def list_audit(
    principal: CurrentPrincipal,
    auth: AuthDep,
    limit: int = 100,
) -> list[AuditEventResponse]:
    """Historial de acciones relevantes, sin contenido sensible."""

    if not principal.is_administrator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Permiso insuficiente."
        )
    events = auth.recent_audit(limit=min(max(limit, 1), 500))
    return [
        AuditEventResponse(
            id=event.id,
            occurred_at=event.occurred_at,
            action=event.action,
            outcome=event.outcome,
            actor_id=event.actor_id,
            target_user_id=event.target_user_id,
        )
        for event in events
    ]
