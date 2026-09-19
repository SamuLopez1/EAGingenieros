"""Fachada de autenticación.

Coordina tres servicios especializados sin asumir sus responsabilidades:

- `AccountService`: quién puede entrar y con qué credenciales.
- `SessionService`: emisión, rotación y revocación de sesiones.
- `AuditLog`: registro de eventos sin contenido sensible.

Se mantiene como única puerta de entrada para que las rutas tengan un solo punto
de contacto y no dependan de cómo está dividido por dentro: si cambia la división
interna, las rutas no se tocan.

El límite transaccional es explícito. Los servicios hacen `flush` para obtener
identificadores, pero **confirmar es decisión de quien llama**: un servicio que
confirmara por su cuenta impediría componer varias operaciones en una sola
transacción, y quien no confirme pierde el trabajo al cerrar la sesión.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session as DbSession

from app.auth.accounts import (
    AccountService,
    InvalidCredentialsError,
    normalise_email,
)
from app.auth.audit import AuditLog
from app.auth.identity import subject_for_user
from app.auth.principal import Principal, Role
from app.auth.sessions import (
    IssuedSession,
    SessionExpiredError,
    SessionService,
    TokenReuseError,
)
from app.auth.tokens import TokenPair, TokenService
from app.db.models import AuditEvent, User

__all__ = [
    "AuthService",
    "InvalidCredentialsError",
    "SessionExpiredError",
    "TokenReuseError",
    "normalise_email",
    "subject_for_user",
]


class AuthService:
    """Punto de entrada único para autenticación."""

    def __init__(
        self,
        session: DbSession,
        *,
        tokens: TokenService,
        organization_id: UUID | None = None,
    ) -> None:
        self._db = session
        self._tokens = tokens
        # UUID fijo de la única organización del MVP.
        self._organization_id = organization_id or UUID(int=1)

        audit = AuditLog(session)
        self.accounts = AccountService(session, audit=audit)
        self.sessions = SessionService(
            session,
            tokens=tokens,
            organization_id=self._organization_id,
            audit=audit,
        )
        self.audit = audit

    # --- Sesión ------------------------------------------------------------

    def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[User, TokenPair]:
        """Autentica y abre una sesión."""

        user = self.accounts.verify_credentials(email, password)
        pair = self.sessions.issue(
            user, user_agent=user_agent, ip_address=ip_address
        )
        self.audit.record("login_succeeded", target_user_id=user.id)
        return user, pair

    def refresh(self, refresh_token: str) -> tuple[User, TokenPair]:
        result: IssuedSession = self.sessions.rotate(refresh_token)
        return result.user, result.tokens

    def logout(self, refresh_token: str) -> bool:
        return self.sessions.close(refresh_token)

    def revoke_user_sessions(self, user_id: int, *, actor_id: int | None = None) -> int:
        return self.sessions.revoke_user_sessions(user_id, actor_id=actor_id)

    def principal_from_token(self, token: str) -> Principal:
        """Valida un access token y construye la identidad."""

        return self.accounts.principal_from_token(token, self._tokens)

    # --- Cuentas -----------------------------------------------------------

    def create_user(
        self,
        *,
        email: str,
        password: str,
        role: Role,
        display_name: str | None = None,
        actor_id: int | None = None,
    ) -> User:
        return self.accounts.create(
            email=email,
            password=password,
            role=role,
            display_name=display_name,
            actor_id=actor_id,
        )

    def change_password(
        self,
        user_id: int,
        *,
        current_password: str,
        new_password: str,
    ) -> None:
        """Cambia la contraseña y cierra las demás sesiones.

        Las sesiones se revocan porque un cambio de contraseña responde
        habitualmente a la sospecha de que estaba comprometida: dejarlas abiertas
        anularía el propósito del cambio.
        """

        self.accounts.change_password(
            user_id,
            current_password=current_password,
            new_password=new_password,
        )
        self.sessions.revoke_user_sessions(user_id, actor_id=user_id)

    def deactivate_user(self, user_id: int, *, actor_id: int | None = None) -> None:
        self.accounts.deactivate(user_id, actor_id=actor_id)
        self.sessions.revoke_user_sessions(user_id, actor_id=actor_id)

    def get_user(self, user_id: int) -> User | None:
        return self.accounts.get(user_id)

    def count_users(self) -> int:
        return self.accounts.count()

    # --- Auditoría ---------------------------------------------------------

    def recent_audit(self, *, limit: int = 100) -> list[AuditEvent]:
        return self.audit.recent(limit=limit)

    # --- Transacción -------------------------------------------------------

    def commit(self) -> None:
        """Confirma la transacción.

        Se expone explícitamente porque el servicio solo hace `flush` durante las
        operaciones: quien no confirme pierde el trabajo al cerrar la sesión.
        """

        self._db.commit()

    def rollback(self) -> None:
        """Descarta la transacción en curso."""

        self._db.rollback()


def session_ttl() -> timedelta:
    """Duración del refresh token, expuesta para documentación y pruebas."""

    from app.auth.tokens import REFRESH_TOKEN_TTL

    return REFRESH_TOKEN_TTL
