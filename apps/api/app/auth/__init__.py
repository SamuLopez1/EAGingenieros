"""Autenticación propia: contraseñas, tokens, sesiones y permisos."""

from app.auth.accounts import AccountService, normalise_email
from app.auth.audit import AuditLog
from app.auth.identity import subject_for_user
from app.auth.passwords import (
    MIN_PASSWORD_LENGTH,
    WeakPasswordError,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.auth.principal import (
    AuthError,
    AuthNotConfiguredError,
    AuthServices,
    CurrentPrincipal,
    MembershipResolver,
    PermissionError_,
    Principal,
    Role,
    TokenValidator,
    get_current_principal,
    require_roles,
)
from app.auth.service import (
    AuthService,
    InvalidCredentialsError,
    SessionExpiredError,
    TokenReuseError,
)
from app.auth.sessions import SessionService
from app.auth.tokens import (
    ACCESS_TOKEN_TTL,
    REFRESH_TOKEN_TTL,
    AccessTokenClaims,
    TokenPair,
    TokenService,
    generate_refresh_token,
    hash_refresh_token,
    refresh_expiry,
)

__all__ = [
    "ACCESS_TOKEN_TTL",
    "AccountService",
    "AuditLog",
    "SessionService",
    "normalise_email",
    "subject_for_user",
    "MIN_PASSWORD_LENGTH",
    "REFRESH_TOKEN_TTL",
    "AccessTokenClaims",
    "AuthError",
    "AuthNotConfiguredError",
    "AuthService",
    "AuthServices",
    "CurrentPrincipal",
    "InvalidCredentialsError",
    "MembershipResolver",
    "PermissionError_",
    "Principal",
    "Role",
    "SessionExpiredError",
    "TokenPair",
    "TokenReuseError",
    "TokenService",
    "TokenValidator",
    "WeakPasswordError",
    "generate_refresh_token",
    "get_current_principal",
    "hash_password",
    "hash_refresh_token",
    "needs_rehash",
    "refresh_expiry",
    "require_roles",
    "verify_password",
]
