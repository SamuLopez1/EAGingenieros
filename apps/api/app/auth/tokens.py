"""Emisión y validación de tokens de sesión.

Diseño de tokens:

- **Access token corto** (15 min por defecto). Es un JWT firmado que la API
  valida sin consultar la base de datos, lo que evita una consulta por petición.
- **Refresh token largo** (7 días), opaco y guardado hasheado en la base de
  datos. Es opaco a propósito: si fuera un JWT no se podría revocar antes de su
  expiración, y la revocación es un requisito del sistema.

**Rotación de refresh tokens.** Cada uso emite uno nuevo e invalida el anterior.
Si un refresh token ya usado se presenta otra vez, se asume robo: el atacante
pudo copiarlo y el legítimo usuario sigue teniendo el suyo. En ese caso se
revoca **toda la cadena** de esa sesión, no solo el token presentado. Sin esto,
un token robado seguiría renovándose indefinidamente.

El `jti` del access token permite revocaciones puntuales sin mantener una lista
de todos los tokens emitidos.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

import jwt
from jwt import InvalidTokenError

from app.auth.principal import AuthError, Role

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=7)

_ALGORITHM = "HS256"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: Literal["bearer"] = "bearer"


@dataclass(frozen=True)
class AccessTokenClaims:
    subject_id: UUID
    organization_id: UUID
    role: Role
    token_id: str
    expires_at: datetime


class TokenService:
    """Emite y valida tokens. No accede a la base de datos."""

    def __init__(
        self,
        *,
        secret: str,
        issuer: str = "eag-licitaciones",
        audience: str = "eag-api",
        access_ttl: timedelta = ACCESS_TOKEN_TTL,
    ) -> None:
        if len(secret) < 32:
            # Un secreto corto es adivinable por fuerza bruta, y con HS256 el
            # secreto es la única barrera: quien lo tenga puede emitir tokens
            # válidos para cualquier usuario.
            raise ValueError("el secreto de firma debe tener al menos 32 caracteres")
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._access_ttl = access_ttl

    def issue(
        self,
        *,
        subject_id: UUID,
        organization_id: UUID,
        role: Role,
    ) -> TokenPair:
        now = datetime.now(UTC)
        expires_at = now + self._access_ttl
        access = jwt.encode(
            {
                "sub": str(subject_id),
                "org": str(organization_id),
                "role": role.value,
                "iss": self._issuer,
                "aud": self._audience,
                "iat": int(now.timestamp()),
                "exp": int(expires_at.timestamp()),
                "jti": uuid4().hex,
                "typ": "access",
            },
            self._secret,
            algorithm=_ALGORITHM,
        )
        return TokenPair(
            access_token=access,
            refresh_token=generate_refresh_token(),
            expires_in=int(self._access_ttl.total_seconds()),
        )

    def decode(self, token: str) -> AccessTokenClaims:
        """Valida firma, expiración, issuer, audience y tipo.

        Se verifican los cuatro extremos: un token firmado por nosotros pero
        emitido para otra audiencia no debe servir aquí, y un refresh token no
        debe poder usarse como access token aunque comparta firma.
        """

        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except InvalidTokenError as error:
            raise AuthError(str(error)) from error

        if payload.get("typ") != "access":
            raise AuthError("el token no es de acceso")

        try:
            return AccessTokenClaims(
                subject_id=UUID(str(payload["sub"])),
                organization_id=UUID(str(payload["org"])),
                role=Role(str(payload["role"])),
                token_id=str(payload["jti"]),
                expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=UTC),
            )
        except (KeyError, ValueError, TypeError) as error:
            raise AuthError("claims incompletos o inválidos") from error


def generate_refresh_token() -> str:
    """Genera un refresh token opaco de alta entropía."""

    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Hash del refresh token para almacenarlo.

    Se usa SHA-256 y no Argon2 a propósito: el token ya tiene 384 bits de
    entropía aleatoria, así que no es adivinable por fuerza bruta y no necesita
    un coste lento. Aplicar Argon2 añadiría latencia en cada renovación sin
    aportar seguridad frente a un volcado de la base.
    """

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_expiry(now: datetime | None = None) -> datetime:
    return (now or datetime.now(UTC)) + REFRESH_TOKEN_TTL
